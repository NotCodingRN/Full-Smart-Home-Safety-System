#!/usr/bin/env python3
"""
Local-first Raspberry Pi controller.

The daemon owns realtime PIC UART access and automation.  MQTT callbacks never
touch UART directly; they only enqueue commands.  This keeps local automation
alive when AWS is slow, disconnected, or reconnecting.
"""

import argparse
import json
import logging
import os
import sys
import time

from mqtt_bridge import DualMqttBridge
from smarthome_config import (
    COMMAND_DEDUP_SECONDS,
    DOOR_HOLD_SECONDS,
    LCD_BOOT_LINE1,
    LCD_BOOT_LINE2,
    LCD_READY_LINE2,
    LCD_STATUS_INTERVAL,
    LOG_DIR,
    PUBLISH_INTERVAL,
    RELAY_FAN1,
    RELAY_FAN2,
    RELAY_PUMP,
    SENSOR_POLL_INTERVAL,
    STATUS_PUBLISH_INTERVAL,
    TOPIC_ALERTS,
    TOPIC_CMD_ALL,
    TOPIC_CMD_DOOR,
    TOPIC_CMD_FAN1,
    TOPIC_CMD_FAN2,
    TOPIC_CMD_PUMP,
    TOPIC_SENSORS,
    TOPIC_STATUS,
)
from smarthome_logic import DoorMonitor, RelayController, interpret_sensors
from smarthome_weather import WeatherGuard


def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(LOG_DIR, "smarthome.log")),
        ],
    )


_setup_logging()
log = logging.getLogger("smarthome")


COMMAND_TOPICS = (
    TOPIC_CMD_FAN1,
    TOPIC_CMD_FAN2,
    TOPIC_CMD_PUMP,
    TOPIC_CMD_DOOR,
    TOPIC_CMD_ALL,
)


def _fake_sensors():
    return {
        "mq2": 65,
        "soil1": 450,
        "soil2": 45,
        "temp_c": 24,
        "humidity": 55,
        "dht_ok": 1,
        "ir1": 0,
        "ir2": 0,
        "relays": [0, 0, 0],
    }


def _json_or_text(payload):
    text = str(payload).strip()
    if not text:
        return "", {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            value = data.get("state", data.get("value", data.get("command", "")))
            return str(value).strip(), data
    except json.JSONDecodeError:
        pass
    return text, {}


def _state_from_payload(payload):
    text, _ = _json_or_text(payload)
    upper = text.strip().upper()
    if upper in ("ON", "1", "TRUE", "YES", "OPEN", "UNLOCK", "GRANTED", "ACCESS_GRANTED"):
        return True
    if upper in ("OFF", "0", "FALSE", "NO", "CLOSE", "LOCK", "DENIED", "ACCESS_DENIED"):
        return False
    if upper in ("AUTO", "CLEAR", "RESET"):
        return None
    raise ValueError(f"unknown state payload: {payload!r}")


class SmartHomeDaemon:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.pic = None
        self.mqtt = DualMqttBridge("daemon", subscribe_topics=COMMAND_TOPICS)
        self.door_monitor = DoorMonitor()
        self.relay_ctrl = RelayController()
        self.weather = WeatherGuard()

        self._relay_state = {1: False, 2: False, 3: False}
        self._last_sensor_publish = 0.0
        self._last_status_publish = 0.0
        self._last_lcd_status = 0.0
        self._lcd_hold_until = 0.0
        self._recent_commands = {}
        self._alert_last_sent = {}
        self._cycle = 0

    def _init_pic(self):
        if self.dry_run:
            log.info("DRY-RUN mode: no serial port opened")
            return

        from pic_io import PicIoBoard

        log.info("Connecting to PIC over UART")
        self.pic = PicIoBoard()
        log.info("PIC ID: %s", self.pic.identify())
        log.info("PIC PING: %s", self.pic.ping())
        self.pic.set_all_relays(False)
        self.pic.lcd_line(1, LCD_BOOT_LINE1)
        self.pic.lcd_line(2, LCD_BOOT_LINE2)
        self._hold_lcd(2.0)

    def _get_sensors(self):
        if self.dry_run:
            return _fake_sensors()
        return self.pic.get_sensors()

    def _apply_relays(self, desired):
        for relay, want in desired.items():
            want = bool(want)
            if self._relay_state.get(relay) == want:
                continue

            if self.dry_run:
                log.info("DRY-RUN relay %d -> %s", relay, "ON" if want else "OFF")
            else:
                self.pic.set_relay(relay, want)

            self._relay_state[relay] = want
            log.info("Relay %d set to %s", relay, "ON" if want else "OFF")
            self._publish(
                TOPIC_STATUS,
                {
                    "type": "relay_state",
                    "relay": relay,
                    "state": want,
                    "timestamp": int(time.time()),
                },
            )

    def _lcd(self, line1, line2, force=False):
        if self.dry_run or self.pic is None:
            return

        now = time.monotonic()
        if not force:
            if now < self._lcd_hold_until:
                return
            if now - self._last_lcd_status < LCD_STATUS_INTERVAL:
                return

        self.pic.lcd_line(1, str(line1)[:16])
        self.pic.lcd_line(2, str(line2)[:16])
        self._last_lcd_status = now

    def _hold_lcd(self, seconds=DOOR_HOLD_SECONDS):
        self._lcd_hold_until = time.monotonic() + seconds

    def _publish(self, topic, payload, qos=1, retain=False):
        self.mqtt.publish(topic, payload, qos=qos, retain=retain)

    def _publish_alert(self, alert_type, payload, min_interval=20.0):
        now = time.monotonic()
        if now - self._alert_last_sent.get(alert_type, 0.0) < min_interval:
            return
        self._alert_last_sent[alert_type] = now
        self._publish(TOPIC_ALERTS, {"type": alert_type, "timestamp": int(time.time()), **payload})

    def _process_pending_commands(self):
        while True:
            cmd = self.mqtt.get_command(timeout=0.0)
            if cmd is None:
                return

            payload_text, payload_json = _json_or_text(cmd.payload)
            dedupe_key = (cmd.topic, payload_text.upper())
            now = time.monotonic()
            if now - self._recent_commands.get(dedupe_key, 0.0) < COMMAND_DEDUP_SECONDS:
                continue
            self._recent_commands[dedupe_key] = now

            log.info("CMD <- %s %s : %s", cmd.source.upper(), cmd.topic, cmd.payload)
            try:
                self._handle_command(cmd.topic, payload_text, payload_json, cmd.source)
            except Exception as exc:
                log.error("Command failed topic=%s payload=%s: %s", cmd.topic, cmd.payload, exc, exc_info=True)
                self._publish_alert(
                    "command_error",
                    {"topic": cmd.topic, "payload": cmd.payload, "error": str(exc), "source": cmd.source},
                    min_interval=3.0,
                )

    def _handle_command(self, topic, payload_text, payload_json, source):
        if topic == TOPIC_CMD_FAN1:
            self.relay_ctrl.set_override(RELAY_FAN1, _state_from_payload(payload_text))
        elif topic == TOPIC_CMD_FAN2:
            self.relay_ctrl.set_override(RELAY_FAN2, _state_from_payload(payload_text))
        elif topic == TOPIC_CMD_PUMP:
            self.relay_ctrl.set_override(RELAY_PUMP, _state_from_payload(payload_text))
        elif topic == TOPIC_CMD_ALL:
            upper = str(payload_text).strip().upper()
            if upper in ("AUTO", "CLEAR", "RESET"):
                self.relay_ctrl.clear_all_overrides()
            else:
                self.relay_ctrl.set_override(RELAY_FAN1, False)
                self.relay_ctrl.set_override(RELAY_FAN2, False)
                self.relay_ctrl.set_override(RELAY_PUMP, False)
                log.info("All-off command accepted")
        elif topic == TOPIC_CMD_DOOR:
            self._handle_door_command(payload_text, source)
        else:
            log.warning("Unknown command topic ignored: %s", topic)

    def _handle_door_command(self, payload_text, source):
        action = str(payload_text).strip().upper()
        if self.dry_run:
            log.info("DRY-RUN door command: %s", action)
        elif self.pic is None:
            raise RuntimeError("PIC is not connected")
        elif action in ("OPEN", "UNLOCK"):
            self.pic.door_open()
            self._hold_lcd()
        elif action in ("CLOSE", "LOCK"):
            self.pic.door_close()
        elif action in ("GRANTED", "ACCESS_GRANTED", "ALLOW"):
            self.pic.access_granted()
            self._hold_lcd()
        elif action in ("DENIED", "ACCESS_DENIED", "DENY"):
            self.pic.access_denied()
            try:
                self.pic.door_close()
            except Exception:
                log.exception("Door close after denied access failed")
            self._hold_lcd()
        else:
            raise ValueError(f"unknown door command: {payload_text!r}")

        self._publish_alert(
            "door_command",
            {"source": source, "payload": action},
            min_interval=1.0,
        )

    def run(self):
        self._init_pic()
        self.mqtt.start()
        self._lcd(LCD_BOOT_LINE1, LCD_READY_LINE2, force=True)

        log.info("Starting local-first sensor loop; poll interval %.2fs", SENSOR_POLL_INTERVAL)
        while True:
            try:
                self._cycle += 1
                self._process_pending_commands()

                raw = self._get_sensors()
                interpreted = interpret_sensors(raw)
                interpreted.update(self.weather.check())
                override_info = self.relay_ctrl.override_summary()
                desired = self.relay_ctrl.desired_states(interpreted)
                self._apply_relays(desired)

                for ev in self.door_monitor.check(raw.get("ir1", 0), raw.get("ir2", 0)):
                    log.info("Security event: %s", ev)
                    self._publish_alert("security_intrusion", ev, min_interval=2.0)

                if interpreted["gas_alert"]:
                    log.warning("GAS ALERT mq2=%s", interpreted["mq2"])
                    self._publish_alert("gas_alert", {"mq2": interpreted["mq2"]}, min_interval=10.0)
                if interpreted["leak_alert"]:
                    log.warning("WATER LEAK soil2=%s", interpreted["bathroom_leak_raw"])
                    self._publish_alert(
                        "bathroom_water_leak",
                        {"sensor_raw": interpreted["bathroom_leak_raw"]},
                        min_interval=10.0,
                    )

                self._publish_periodic(interpreted, override_info)
                self._lcd(
                    f"G:{interpreted['gas_status']} B:{interpreted['leak_status']}",
                    f"GDN:{interpreted['garden_status']} R:{'Y' if interpreted.get('rain_block_watering') else 'N'}",
                )

                time.sleep(SENSOR_POLL_INTERVAL)

            except KeyboardInterrupt:
                log.info("Interrupted by user")
                break
            except Exception as exc:
                log.error("Loop error: %s", exc, exc_info=True)
                time.sleep(1.0)

        self.shutdown()

    def _publish_periodic(self, interpreted, override_info):
        now = time.monotonic()
        mqtt_status = self.mqtt.status()

        if now - self._last_sensor_publish >= PUBLISH_INTERVAL:
            self._publish(
                TOPIC_SENSORS,
                {
                    **interpreted,
                    **override_info,
                    "relay_fan1_on": self._relay_state[RELAY_FAN1],
                    "relay_fan2_on": self._relay_state[RELAY_FAN2],
                    "relay_pump_on": self._relay_state[RELAY_PUMP],
                    "cycle": self._cycle,
                    "timestamp": int(time.time()),
                },
            )
            self._last_sensor_publish = now

        if now - self._last_status_publish >= STATUS_PUBLISH_INTERVAL:
            self._publish(
                TOPIC_STATUS,
                {
                    "fan1": self._relay_state[RELAY_FAN1],
                    "fan2": self._relay_state[RELAY_FAN2],
                    "pump": self._relay_state[RELAY_PUMP],
                    "pic_connected": self.dry_run or self.pic is not None,
                    "cycle": self._cycle,
                    "timestamp": int(time.time()),
                    **mqtt_status,
                },
            )
            self._last_status_publish = now

    def shutdown(self):
        log.info("Shutting down")
        try:
            if self.pic is not None:
                self.pic.set_all_relays(False)
                self.pic.lcd_line(1, "SHUTDOWN")
                self.pic.lcd_line(2, "RELAYS OFF")
                self.pic.close()
        finally:
            self.mqtt.stop()


def main():
    parser = argparse.ArgumentParser(description="Smart Home Daemon")
    parser.add_argument("--dry-run", action="store_true", help="Run without serial port")
    args = parser.parse_args()

    daemon = SmartHomeDaemon(dry_run=args.dry_run)
    daemon.run()


if __name__ == "__main__":
    main()
