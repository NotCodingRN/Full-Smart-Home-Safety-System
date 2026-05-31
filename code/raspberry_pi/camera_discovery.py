#!/usr/bin/env python3
import argparse
import re
import socket


DISCOVERY_PORT = 4210
ANNOUNCE_RE = re.compile(r"ESP32CAM_HERE,(\d+\.\d+\.\d+\.\d+),(\d+)")


def discover_esp32(timeout=10, port=DISCOVERY_PORT):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", port))
        sock.settimeout(timeout)

        while True:
            data, addr = sock.recvfrom(256)
            text = data.decode("utf-8", errors="replace").strip()
            match = ANNOUNCE_RE.match(text)
            if match:
                ip = match.group(1)
                camera_port = match.group(2)
                return f"http://{ip}:{camera_port}/stream"
    except socket.timeout as exc:
        raise TimeoutError(f"No ESP32-CAM announcement received on UDP {port}") from exc
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(description="Discover ESP32-CAM UDP announcement")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()
    print(discover_esp32(timeout=args.timeout))


if __name__ == "__main__":
    main()
