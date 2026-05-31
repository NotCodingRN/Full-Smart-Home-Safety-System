#!/usr/bin/env python3
import argparse

import cv2

from camera_discovery import discover_esp32
from smarthome_config import ESP32_CAM_STREAM_URL


def main():
    parser = argparse.ArgumentParser(description="Open ESP32-CAM stream in an OpenCV window.")
    parser.add_argument("--url", help="Known MJPEG stream URL")
    parser.add_argument("--discover", action="store_true", help="Use UDP discovery first")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()

    if args.url:
        url = args.url
    elif args.discover:
        url = discover_esp32(timeout=args.timeout)
    else:
        url = ESP32_CAM_STREAM_URL

    print("Opening:", url)
    cap = cv2.VideoCapture(url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera stream: {url}")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        cv2.imshow("ESP32-CAM", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
