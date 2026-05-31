import json
import logging
import threading
import time

import serial

from smarthome_config import (
    PIC_COMMAND_RETRIES,
    PIC_SERIAL_BAUD,
    PIC_SERIAL_PORT,
    PIC_SERIAL_TIMEOUT,
)


log = logging.getLogger("pic_io")


class PicIoBoard:
    """
    Thread-safe ASCII command wrapper for the PIC16F877A firmware.

    Only one command is allowed on the UART at a time.  This matters because
    the daemon, MQTT commands, and service shutdown can otherwise interleave
    bytes and make valid PIC responses look like garbage.
    """

    def __init__(self, port=PIC_SERIAL_PORT, baud=PIC_SERIAL_BAUD, timeout=PIC_SERIAL_TIMEOUT):
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._lock = threading.Lock()

        try:
            self.ser = serial.Serial(
                port,
                baud,
                timeout=timeout,
                write_timeout=timeout,
                inter_byte_timeout=timeout,
                exclusive=True,
            )
        except TypeError:
            self.ser = serial.Serial(
                port,
                baud,
                timeout=timeout,
                write_timeout=timeout,
                inter_byte_timeout=timeout,
            )

        time.sleep(0.35)
        self.drain()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            log.exception("Failed to close PIC serial port")

    def drain(self):
        try:
            self.ser.reset_input_buffer()
        except Exception:
            while self.ser.in_waiting:
                self.ser.readline()

    def command(self, text, expect_json=False):
        if not text or "\n" in text or "\r" in text:
            raise ValueError("PIC command must be one non-empty line")

        with self._lock:
            last_seen = None
            last_error = None

            for attempt in range(PIC_COMMAND_RETRIES + 1):
                try:
                    result = self._command_once(text, expect_json=expect_json)
                    return result
                except Exception as exc:
                    last_error = exc
                    log.warning("PIC command attempt %d failed for %s: %s", attempt + 1, text, exc)
                    time.sleep(0.08)

                if isinstance(last_error, _PicResponseTimeout):
                    last_seen = last_error.last_seen

            detail = f" Last line: {last_seen!r}" if last_seen else ""
            raise TimeoutError(f"No valid response for command: {text}.{detail}") from last_error

    def _command_once(self, text, expect_json=False):
        deadline = time.monotonic() + self.timeout
        last_seen = None

        self.ser.reset_input_buffer()
        time.sleep(0.015)
        self.ser.write((text + "\n").encode("ascii"))
        self.ser.flush()

        while time.monotonic() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue

            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue

            last_seen = line
            if not self._is_usable_line(line):
                continue

            if line.startswith("READY") or line.startswith("PIC IO READY"):
                continue

            if expect_json:
                if not line.startswith("{"):
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError as exc:
                    last_seen = line
                    log.warning("Bad JSON from PIC: %s", exc)
                    continue

            return line

        raise _PicResponseTimeout(last_seen)

    @staticmethod
    def _is_usable_line(line):
        if "\ufffd" in line:
            return False
        return all(ch == "\t" or ch == " " or 32 <= ord(ch) <= 126 for ch in line)

    def identify(self):
        return self.command("ID")

    def ping(self):
        return self.command("PING")

    def get_sensors(self):
        return self.command("GET", expect_json=True)

    def set_relay(self, number, state):
        number = int(number)
        if number not in (1, 2, 3):
            raise ValueError("Relay number must be 1, 2, or 3")
        return self.command(f"R{number}={'1' if state else '0'}")

    def set_all_relays(self, state):
        return self.command(f"RALL={'1' if state else '0'}")

    def lcd_line(self, row, text):
        clean = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in str(text))[:16]
        return self.command(f"{'LCD1' if int(row) == 1 else 'LCD2'}={clean}")

    def lcd_clear(self):
        return self.command("LCDCLR")

    def door_open(self):
        return self.command("DOOR=OPEN")

    def door_close(self):
        return self.command("DOOR=CLOSE")

    def access_granted(self):
        return self.command("ACCESS=GRANTED")

    def access_denied(self):
        return self.command("ACCESS=DENIED")

    def raw(self, text):
        return self.command(str(text).strip())


class _PicResponseTimeout(Exception):
    def __init__(self, last_seen):
        super().__init__("PIC response timeout")
        self.last_seen = last_seen
