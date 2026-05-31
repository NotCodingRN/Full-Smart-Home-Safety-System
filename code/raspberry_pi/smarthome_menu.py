#!/usr/bin/env python3
# =============================================================================
# smarthome_menu.py
# Local interactive debug menu: same feel as the old pic_menu.py
# Works without MQTT / AWS.  Great for bench testing.
#
# Usage:
#   sudo python3 smarthome_menu.py
#   sudo python3 smarthome_menu.py --dry-run   (no serial port)
# =============================================================================

import argparse
import json
import time

from smarthome_config import (
    RELAY_FAN1, RELAY_FAN2, RELAY_PUMP,
    MQ2_ALERT_THRESHOLD, LEAK_ALERT_THRESHOLD, GARDEN_DRY_THRESHOLD,
)
from smarthome_logic import interpret_sensors, DoorMonitor, RelayController
from smarthome_weather import WeatherGuard

# ---- colour helpers (works on Linux terminal) ----
RED    = "\033[91m"
GRN    = "\033[92m"
YLW    = "\033[93m"
CYN    = "\033[96m"
RST    = "\033[0m"

def col(text, colour): return f"{colour}{text}{RST}"


# ---------------------------------------------------------------------------
# Fake board for --dry-run
# ---------------------------------------------------------------------------

class FakeBoard:
    def identify(self):    return "FAKE_PIC_DRY_RUN"
    def ping(self):        return "PONG"
    def get_sensors(self): return {
        "mq2": 65, "soil1": 10, "soil2": 45,
        "temp_c": 24, "humidity": 85, "dht_ok": 1,
        "ir1": 0, "ir2": 0, "relays": [0, 0, 0],
    }
    def set_relay(self, n, s): return f"FAKE OK R{n}={'1' if s else '0'}"
    def set_all_relays(self, s): return f"FAKE OK RALL={'1' if s else '0'}"
    def lcd_line(self, r, t):  return f"FAKE LCD{r}={t}"
    def lcd_clear(self):       return "FAKE LCDCLR"
    def door_open(self):       return "FAKE DOOR=OPEN"
    def door_close(self):      return "FAKE DOOR=CLOSE"
    def access_granted(self):  return "FAKE ACCESS=GRANTED"
    def access_denied(self):   return "FAKE ACCESS=DENIED"
    def raw(self, t):          return f"FAKE RAW={t}"
    def close(self):           pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pause():
    input("\nPress Enter to continue...")

def header(title):
    print(f"\n{'='*52}")
    print(f"  {title}")
    print('='*52)

def _flag(val, bad_val, bad_label, ok_label):
    """Print a coloured status flag."""
    if val:
        return col(bad_label, RED)
    return col(ok_label, GRN)


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------

def show_sensor_frame(frame):
    interp = interpret_sensors(frame)
    print(f"\n  {'Sensor':<28} {'Raw':>6}  {'Status'}")
    print(f"  {'-'*50}")
    print(f"  {'MQ-2 Gas (kitchen)':<28} {frame['mq2']:>6}  "
          f"{_flag(interp['gas_alert'],   True, 'GAS ALERT !!', 'OK')}  "
          f"(threshold >{MQ2_ALERT_THRESHOLD})")
    print(f"  {'Garden moisture (soil1)':<28} {frame['soil1']:>6}  "
          f"{_flag(interp['garden_needs_water'], True, 'DRY-PUMP ON ', 'WET OK')}  "
          f"(threshold <={GARDEN_DRY_THRESHOLD})")
    print(f"  {'Bathroom leak (soil2)':<28} {frame['soil2']:>6}  "
          f"{_flag(interp['leak_alert'],  True, 'LEAK ALERT!!', 'OK')}  "
          f"(threshold >{LEAK_ALERT_THRESHOLD})")
    print(f"  {'Temperature':<28} {frame['temp_c']:>5}C  "
          f"{'DHT OK' if frame['dht_ok'] else col('DHT ERR', RED)}")
    print(f"  {'Humidity':<28} {frame['humidity']:>5}%")
    print(f"  {'IR1 (Entry door)':<28} {frame['ir1']:>6}  "
          f"{col('CROSSED', YLW) if frame['ir1'] else col('CLEAR', GRN)}")
    print(f"  {'IR2 (Window)':<28} {frame['ir2']:>6}  "
          f"{col('CROSSED', YLW) if frame['ir2'] else col('CLEAR', GRN)}")
    relays = frame.get('relays', [0,0,0])
    print(f"\n  {'Relay 1 - Kitchen Fan':<28} {'ON' if relays[0] else 'OFF':>6}")
    print(f"  {'Relay 2 - Room Fan':<28} {'ON' if relays[1] else 'OFF':>6}")
    print(f"  {'Relay 3 - Water Pump':<28} {'ON' if relays[2] else 'OFF':>6}")
    print(f"\n  Raw JSON: {json.dumps(frame, sort_keys=True)}")


def menu_read_once(pic):
    header("Read All Sensors Once")
    show_sensor_frame(pic.get_sensors())
    pause()


def menu_live_monitor(pic):
    header("Live Sensor Monitor  (Ctrl+C to stop)")
    door = DoorMonitor()
    ctrl = RelayController()
    weather = WeatherGuard()
    print(f"  {'Time':<10} {'MQ2':>5} {'Gdn':>5} {'Leak':>5} {'T':>4} {'H':>4}  "
          f"{'IR1':>4} {'IR2':>4}  {'F1':>3} {'F2':>3} {'Pump':>4} {'Rain':>4}  Alerts")
    print(f"  {'-'*80}")
    try:
        while True:
            frame  = pic.get_sensors()
            interp = interpret_sensors(frame)
            interp.update(weather.check())
            desired = ctrl.desired_states(interp)
            relays = frame.get("relays", [0,0,0])
            door_events = door.check(frame["ir1"], frame["ir2"])

            alert_txt = ""
            if interp["gas_alert"]:   alert_txt += col(" GAS!", RED)
            if interp["leak_alert"]:  alert_txt += col(" LEAK!", RED)
            if interp["garden_needs_water"]: alert_txt += col(" DRY", YLW)
            if interp.get("rain_block_watering"): alert_txt += col(" RAIN-BLOCK", CYN)
            for ev in door_events:    alert_txt += col(f" DOOR:{ev['door']}", CYN)

            print(
                f"  {time.strftime('%H:%M:%S'):<10}"
                f" {frame['mq2']:>5}"
                f" {frame['soil1']:>5}"
                f" {frame['soil2']:>5}"
                f" {frame['temp_c']:>3}C"
                f" {frame['humidity']:>3}%"
                f"  {'1' if frame['ir1'] else '0':>4}"
                f" {'1' if frame['ir2'] else '0':>4}"
                f"  {'ON' if desired[1] else 'OFF':>3}"
                f" {'ON' if desired[2] else 'OFF':>3}"
                f" {'ON' if desired[3] else 'OFF':>4}"
                f"  {'YES' if interp.get('rain_block_watering') else 'NO':>4}"
                f"  {alert_txt}"
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    pause()


def menu_relay_control(pic):
    header("Manual Relay Control")
    print(f"  Relay {RELAY_FAN1} = Kitchen Fan")
    print(f"  Relay {RELAY_FAN2} = Room Fan")
    print(f"  Relay {RELAY_PUMP} = Water Pump (Garden)")
    r = input("\n  Which relay? [1/2/3]: ").strip()
    if r not in ("1", "2", "3"):
        print("  Invalid relay.")
        pause()
        return
    s = input("  State [on/off]: ").strip().lower()
    if s not in ("on", "off"):
        print("  Use on or off.")
        pause()
        return
    print("  " + pic.set_relay(int(r), s == "on"))
    pause()


def menu_all_relays(pic):
    header("All Relays")
    s = input("  Turn all [on/off]: ").strip().lower()
    if s not in ("on", "off"):
        print("  Use on or off.")
        pause()
        return
    print("  " + pic.set_all_relays(s == "on"))
    pause()


def menu_simulate_logic():
    """Simulate the auto-relay logic without needing hardware."""
    header("Simulate Smart-Home Logic (no hardware)")
    print("  Enter fake sensor values to see what the logic would decide.\n")
    try:
        mq2   = int(input(f"  MQ2 gas value  (alert >{MQ2_ALERT_THRESHOLD}): ").strip() or "65")
        soil1 = int(input(f"  Soil1 garden   (dry   <={GARDEN_DRY_THRESHOLD}): ").strip() or "10")
        soil2 = int(input(f"  Soil2 bathroom (leak  >{LEAK_ALERT_THRESHOLD}): ").strip() or "45")
        rain  = input("  Rain expected in next 5h? [y/N]: ").strip().lower() == "y"
    except ValueError:
        print("  Numbers only.")
        pause()
        return

    fake = {
        "mq2": mq2, "soil1": soil1, "soil2": soil2,
        "temp_c": 24, "humidity": 80, "dht_ok": 1,
        "ir1": 0, "ir2": 0, "relays": [0, 0, 0],
    }
    interp = interpret_sensors(fake)
    interp["rain_block_watering"] = rain
    ctrl   = RelayController()
    desired = ctrl.desired_states(interp)

    print(f"\n  Gas status:    {interp['gas_status']}")
    print(f"  Leak status:   {interp['leak_status']}")
    print(f"  Garden status: {interp['garden_status']}")
    print(f"  Rain block:    {'YES' if rain else 'NO'}")
    print(f"\n  Fan 1 would be: {'ON' if desired[1] else 'OFF'}")
    print(f"  Fan 2 would be: {'ON' if desired[2] else 'OFF'}")
    print(f"  Pump  would be: {'ON' if desired[3] else 'OFF'}")
    pause()


def menu_simulate_door():
    header("Simulate Door Crossing")
    door = DoorMonitor()
    print("  Type IR values (0 or 1) for each reading to watch door events.")
    print("  Press Ctrl+C or type q to stop.\n")
    try:
        while True:
            line = input("  ir1 ir2 (e.g.  0 1): ").strip()
            if line.lower() == "q":
                break
            parts = line.split()
            if len(parts) != 2:
                print("  Enter two values: 0 or 1")
                continue
            try:
                ir1, ir2 = int(parts[0]), int(parts[1])
            except ValueError:
                print("  Use 0 or 1")
                continue
            events = door.check(ir1, ir2)
            if events:
                for ev in events:
                    print(col(f"  EVENT: {ev['door']} crossed!", CYN))
            else:
                print("  No event.")
    except KeyboardInterrupt:
        pass
    pause()


def menu_lcd(pic):
    header("Write to LCD")
    r = input("  Row [1/2]: ").strip()
    if r not in ("1", "2"):
        print("  Row must be 1 or 2.")
        pause()
        return
    t = input("  Text (max 16 chars): ")
    print("  " + pic.lcd_line(int(r), t))
    pause()


def menu_lcd_clear(pic):
    header("Clear LCD")
    print("  " + pic.lcd_clear())
    pause()


def menu_door(pic):
    header("Door Servo / Access Test")
    print("  1. Open door servo")
    print("  2. Close door servo")
    print("  3. Access granted (LCD + open)")
    print("  4. Access denied (LCD only)")
    choice = input("\n  Choose: ").strip()
    if choice == "1":
        print("  " + pic.door_open())
    elif choice == "2":
        print("  " + pic.door_close())
    elif choice == "3":
        print("  " + pic.access_granted())
    elif choice == "4":
        print("  " + pic.access_denied())
    else:
        print("  Unknown choice.")
    pause()


def menu_weather():
    header("Weather Rain Guard")
    print("  Checking WeatherAPI for the next 5 hours...")
    info = WeatherGuard().check()
    print(json.dumps(info, indent=2, sort_keys=True))
    pause()


def menu_raw(pic):
    header("Raw PIC Command")
    print("  Examples: GET  R1=1  R2=0  R3=1  RALL=0  LCD1=HELLO  PING  ID")
    print("            DOOR=OPEN  DOOR=CLOSE  ACCESS=GRANTED  ACCESS=DENIED")
    cmd = input("  Command: ").strip()
    if not cmd:
        pause()
        return
    if cmd == "GET":
        show_sensor_frame(pic.get_sensors())
    else:
        print("  " + pic.raw(cmd))
    pause()


def menu_ping(pic):
    header("Ping PIC")
    print("  " + pic.ping())
    pause()


def menu_id(pic):
    header("PIC ID")
    print("  " + pic.identify())
    pause()


def menu_thresholds():
    header("Current Thresholds (from smarthome_config.py)")
    print(f"  MQ2 gas alert threshold    : {MQ2_ALERT_THRESHOLD}  (your idle is ~60-65)")
    print(f"  Bathroom leak threshold     : {LEAK_ALERT_THRESHOLD}  (your idle is ~7-15)")
    print(f"  Garden dry threshold       : {GARDEN_DRY_THRESHOLD}  (dry is <= this)")
    print(f"\n  Edit smarthome_config.py to change these values.")
    pause()


# ---------------------------------------------------------------------------
# Main menu loop
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Smart Home Debug Menu")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without real PIC hardware (fake sensor data)")
    args = parser.parse_args()

    if args.dry_run:
        print(col("\n  *** DRY-RUN MODE - no serial port ***\n", YLW))
        pic = FakeBoard()
    else:
        from pic_io import PicIoBoard
        print("  Connecting to PIC...")
        pic = PicIoBoard()
        print(f"  ID:   {pic.identify()}")
        print(f"  PING: {pic.ping()}")
        pic.set_all_relays(False)
        pic.lcd_line(1, "SMARTHOME DEBUG")
        pic.lcd_line(2, "MENU READY")

    try:
        while True:
            header("Smart Home Debug Menu" + (" [DRY-RUN]" if args.dry_run else ""))
            print("  --- Sensors ---")
            print("  1.  Read all sensors once")
            print("  2.  Live monitor (logic + door detection)")
            print("  --- Relays ---")
            print("  3.  Manual relay control  (Fan1 / Fan2 / Pump)")
            print("  4.  All relays ON / OFF")
            print("  --- Logic simulation (no hardware needed) ---")
            print("  5.  Simulate auto-relay logic with custom values")
            print("  6.  Simulate door crossing with custom IR values")
            print("  --- PIC direct ---")
            print("  7.  Write LCD text")
            print("  8.  Clear LCD")
            print("  9.  Ping PIC")
            print("  10. Show PIC ID")
            print("  11. Send raw command")
            print("  12. Door servo / access test")
            print("  --- Info ---")
            print("  13. Show current thresholds")
            print("  14. Check WeatherAPI rain guard")
            print("  0.  Exit")

            choice = input("\n  Choose: ").strip()

            if   choice == "1":  menu_read_once(pic)
            elif choice == "2":  menu_live_monitor(pic)
            elif choice == "3":  menu_relay_control(pic)
            elif choice == "4":  menu_all_relays(pic)
            elif choice == "5":  menu_simulate_logic()
            elif choice == "6":  menu_simulate_door()
            elif choice == "7":  menu_lcd(pic)
            elif choice == "8":  menu_lcd_clear(pic)
            elif choice == "9":  menu_ping(pic)
            elif choice == "10": menu_id(pic)
            elif choice == "11": menu_raw(pic)
            elif choice == "12": menu_door(pic)
            elif choice == "13": menu_thresholds()
            elif choice == "14": menu_weather()
            elif choice == "0":
                pic.set_all_relays(False)
                pic.lcd_line(1, "DEBUG EXIT")
                pic.lcd_line(2, "RELAYS OFF")
                break
            else:
                print("  Unknown choice.")
    finally:
        pic.close()


if __name__ == "__main__":
    main()
