# =============================================================================
# smarthome_logic.py
# Pure logic layer: no hardware, no MQTT. Easy to unit-test.
# =============================================================================

from smarthome_config import (
    MQ2_ALERT_THRESHOLD,
    LEAK_ALERT_THRESHOLD,
    GARDEN_DRY_THRESHOLD,
    IR_DOOR_LABEL,
)


# ---------------------------------------------------------------------------
# Sensor interpretation
# ---------------------------------------------------------------------------

def interpret_sensors(frame: dict) -> dict:
    """
    Takes a raw GET frame from PicIoBoard and returns a clean, labelled dict.

    Input keys (from pic_io.py get_sensors()):
        mq2, soil1, soil2, temp_c, humidity, dht_ok, ir1, ir2, relays

    Output adds human-readable interpretation on top.
    """
    mq2    = frame.get("mq2", 0)
    soil1  = frame.get("soil1", 0)   # garden moisture sensor
    soil2  = frame.get("soil2", 0)   # bathroom leak sensor
    temp   = frame.get("temp_c", 0)
    hum    = frame.get("humidity", 0)
    dht_ok = frame.get("dht_ok", 0)
    ir1    = frame.get("ir1", 0)
    ir2    = frame.get("ir2", 0)
    relays = frame.get("relays", [0, 0, 0])

    gas_alert    = mq2   >= MQ2_ALERT_THRESHOLD
    garden_dry   = soil1 <= GARDEN_DRY_THRESHOLD
    leak_alert   = soil2 >= LEAK_ALERT_THRESHOLD

    return {
        # --- raw values ---
        "mq2":          mq2,
        "garden_moisture_raw": soil1,
        "bathroom_leak_raw": soil2,
        "temp_c":       temp,
        "humidity_pct": hum,
        "dht_ok":       bool(dht_ok),
        "ir1":          ir1,
        "ir2":          ir2,
        "relay_kitchen_fan": bool(relays[0]) if len(relays) > 0 else False,
        "relay_room_fan":    bool(relays[1]) if len(relays) > 1 else False,
        "relay_pump":   bool(relays[2]) if len(relays) > 2 else False,
        "relay_fan1":   bool(relays[0]) if len(relays) > 0 else False,
        "relay_fan2":   bool(relays[1]) if len(relays) > 1 else False,

        # --- interpreted flags ---
        "gas_alert":    gas_alert,
        "leak_alert":   leak_alert,
        "garden_needs_water": garden_dry,

        # --- labels for display ---
        "gas_status":    "ALERT" if gas_alert  else "OK",
        "leak_status":   "LEAK"  if leak_alert else "OK",
        "garden_status": "DRY"   if garden_dry else "OK",
    }


# ---------------------------------------------------------------------------
# Door crossing detection
# ---------------------------------------------------------------------------

class DoorMonitor:
    """Remembers previous IR state and fires events on rising edge."""

    def __init__(self):
        self._last = {0: 0, 1: 0}    # sensor index to last value

    def check(self, ir1: int, ir2: int) -> list[dict]:
        """
        Returns a (possibly empty) list of door-event dicts.
        Each dict: { "door": "Entry door", "sensor": 0, "event": "crossed" }
        """
        events = []
        for idx, val in enumerate([ir1, ir2]):
            if val == 1 and self._last[idx] == 0:
                events.append({
                    "door":   IR_DOOR_LABEL.get(idx, f"Door {idx+1}"),
                    "sensor": idx + 1,
                    "event":  "crossed",
                })
            self._last[idx] = val
        return events


# ---------------------------------------------------------------------------
# Automatic relay decisions
#
# Manual overrides (from AWS commands) take priority over auto-logic.
# Override is remembered until explicitly cleared or all_off is sent.
# ---------------------------------------------------------------------------

class RelayController:
    """
    Tracks manual overrides and produces the desired relay state
    based on sensor data + overrides.

    Relay assignment:
        relay 1 = Kitchen fan
        relay 2 = Room fan
        relay 3 = Water pump (garden)
    """

    def __init__(self):
        # None = no override (auto-logic decides)
        # True/False = manual override
        self._override = {1: None, 2: None, 3: None}

    def set_override(self, relay: int, state: bool | None):
        """Called when a command arrives from AWS."""
        if relay in self._override:
            self._override[relay] = state

    def clear_all_overrides(self):
        self._override = {1: None, 2: None, 3: None}

    def desired_states(self, interpreted: dict) -> dict:
        """
        Returns {1: bool, 2: bool, 3: bool}: the desired on/off state
        for each relay.

        Safety logic:
          Kitchen fan ON when gas alert
          Room fan ON    when gas alert
          Pump OFF       when rain is expected soon

        Auto-logic when safe:
          Pump ON        when garden is dry

        Note: water leak only triggers an MQTT warning, never affects relays.
        """
        gas   = interpreted["gas_alert"]
        dry   = interpreted["garden_needs_water"]
        rain_block = interpreted.get("rain_block_watering", False)

        result = {1: False, 2: False, 3: False}

        for relay in (1, 2):
            override = self._override[relay]
            result[relay] = True if gas else (False if override is None else override)

        pump_override = self._override[3]
        if rain_block:
            result[3] = False
        else:
            result[3] = dry if pump_override is None else pump_override

        return result

    def override_summary(self) -> dict:
        return {
            f"relay{r}_override": (
                "manual_on"  if v is True  else
                "manual_off" if v is False else
                "auto"
            )
            for r, v in self._override.items()
        }
