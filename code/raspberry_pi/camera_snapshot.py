#!/usr/bin/env python3
import argparse
import time
import urllib.request

from camera_discovery import discover_esp32
from smarthome_config import ESP32_CAM_STREAM_URL


def read_one_jpeg(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as stream:
        data = bytearray()
        start_time = time.time()

        while time.time() - start_time < timeout:
            chunk = stream.read(4096)
            if not chunk:
                break

            data.extend(chunk)
            start = data.find(b"\xff\xd8")
            end = data.find(b"\xff\xd9", start + 2)

            if start != -1 and end != -1:
                return bytes(data[start:end + 2])

    raise TimeoutError("No complete JPEG frame received from camera stream")


def main():
    parser = argparse.ArgumentParser(description="Save one JPEG from ESP32-CAM MJPEG stream.")
    parser.add_argument("--url", help="Use a known stream URL")
    parser.add_argument("--discover", action="store_true", help="Use UDP discovery first")
    parser.add_argument("--output", default="esp32_frame.jpg", help="Output JPEG path")
    parser.add_argument("--timeout", type=int, default=15, help="Discovery/read timeout seconds")
    args = parser.parse_args()

    if args.url:
        url = args.url
    elif args.discover:
        url = discover_esp32(timeout=args.timeout)
    else:
        url = ESP32_CAM_STREAM_URL

    print("Camera URL:", url)
    frame = read_one_jpeg(url, timeout=args.timeout)
    with open(args.output, "wb") as out:
        out.write(frame)
    print(f"Saved {len(frame)} bytes to {args.output}")


if __name__ == "__main__":
    main()
