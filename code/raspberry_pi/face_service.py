#!/usr/bin/env python3
"""
Local face recognition and camera API service.

Camera video remains LAN-only.  MQTT publishes only events and local endpoint
URLs so the app can load http://PI_IP:5000/video when it is on the same WiFi.
"""

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request

from face_recognition_engine import FaceDB, FaceEngine
from mqtt_bridge import DualMqttBridge
from smarthome_config import (
    CAMERA_BACKEND_PUBLISH_INTERVAL,
    CAMERA_RECONNECT_SECONDS,
    ESP32_CAM_STREAM_URL,
    FACE_COOLDOWN_SECONDS,
    FACE_DB_PATH,
    FACE_JPEG_QUALITY,
    FACE_MATCH_THRESHOLD,
    FACE_MJPEG_FPS,
    FACE_MODEL_DIR,
    FACE_PUBLIC_HOST,
    FACE_RECOGNITION_ENABLED,
    FACE_RECOGNITION_INTERVAL,
    FACE_SERVICE_HOST,
    FACE_SERVICE_PORT,
    FACE_UNKNOWN_COOLDOWN_SECONDS,
    LOG_DIR,
    TOPIC_CAMERA_BACKEND,
    TOPIC_CMD_CAMERA,
    TOPIC_CMD_DOOR,
    TOPIC_FACE_EVENTS,
)


def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(LOG_DIR, "face_service.log")),
        ],
    )


_setup_logging()
log = logging.getLogger("face_service")
app = Flask(__name__)


class FrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.raw = None
        self.annotated = None
        self.encoded_jpeg = None
        self.seq = 0
        self.annotated_seq = 0
        self.camera_connected = False
        self.camera_url = ""
        self.last_frame_time = 0.0
        self.last_error = ""

    def set_camera_state(self, connected, url="", error=""):
        with self._lock:
            self.camera_connected = bool(connected)
            if url:
                self.camera_url = url
            self.last_error = str(error or "")

    def update_raw(self, frame):
        with self._lock:
            self.raw = frame
            self.seq += 1
            self.last_frame_time = time.time()

    def raw_copy(self):
        with self._lock:
            if self.raw is None:
                return self.seq, None
            return self.seq, self.raw.copy()

    def update_annotated(self, frame):
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, FACE_JPEG_QUALITY])
        with self._lock:
            self.annotated = frame
            self.annotated_seq = self.seq
            if ok:
                self.encoded_jpeg = buf.tobytes()

    def latest_jpeg(self):
        with self._lock:
            return self.encoded_jpeg

    def latest_image_copy(self):
        with self._lock:
            frame = self.annotated if self.annotated is not None else self.raw
            if frame is None:
                return None
            return frame.copy()

    def status(self):
        with self._lock:
            return {
                "camera_connected": self.camera_connected,
                "camera_url": self.camera_url,
                "last_frame_time": int(self.last_frame_time) if self.last_frame_time else None,
                "last_error": self.last_error or None,
                "frame_seq": self.seq,
                "annotated_seq": self.annotated_seq,
            }


frames = FrameStore()
engine = None
face_db = None
mqtt_bridge = DualMqttBridge("face", subscribe_topics=(TOPIC_CMD_CAMERA,))
last_recognition = {}
service_started = time.time()
service_port = FACE_SERVICE_PORT
offline_jpeg = None
CAMERA_CACHE_PATH = os.path.join(LOG_DIR, "esp32_cam_url.json")


def _load_cached_camera_url():
    try:
        with open(CAMERA_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        url = str(data.get("url", "")).strip()
        return url
    except Exception:
        return ""


def _save_cached_camera_url(url):
    url = str(url or "").strip()
    if not url:
        return
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        tmp = CAMERA_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"url": url, "ts": int(time.time())}, f, separators=(",", ":"))
        os.replace(tmp, CAMERA_CACHE_PATH)
    except Exception:
        log.exception("Failed to save camera URL cache: %s", url)


def _discover_camera_url(timeout=8):
    from camera_discovery import discover_esp32
    return discover_esp32(timeout=timeout)


def _get_lan_ip():
    if FACE_PUBLIC_HOST:
        return FACE_PUBLIC_HOST

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()

    try:
        host = socket.gethostname()
        ip = socket.gethostbyname(host)
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    return "127.0.0.1"


def _backend_payload():
    pi_ip = _get_lan_ip()
    base = f"http://{pi_ip}:{service_port}"
    return {
        "pi_ip": pi_ip,
        "video_url": f"{base}/video",
        "stream_url": f"{base}/stream",
        "snapshot_url": f"{base}/snapshot",
        "enroll_url": f"{base}/enroll",
        "faces_url": f"{base}/faces",
        "status_url": f"{base}/status",
        "local_only": True,
        "timestamp": int(time.time()),
        **frames.status(),
        **mqtt_bridge.status(),
    }


def _publish(topic, payload, qos=1, retain=False):
    mqtt_bridge.publish(topic, payload, qos=qos, retain=retain)


def _publish_camera_backend_once():
    payload = _backend_payload()
    _publish(TOPIC_CAMERA_BACKEND, payload, qos=1, retain=True)
    log.info("Camera backend published: %s", payload["video_url"])


def _camera_command_loop():
    while True:
        cmd = mqtt_bridge.get_command(timeout=0.5)
        if cmd is None:
            continue
        payload = cmd.payload.strip().upper()
        if cmd.topic != TOPIC_CMD_CAMERA:
            continue
        if payload in ("", "GET", "URL", "STATUS", "BACKEND", "OPEN"):
            log.info("Camera backend requested by %s MQTT", cmd.source.upper())
            _publish_camera_backend_once()
        else:
            log.info("Ignoring camera command payload: %s", cmd.payload)


def _camera_backend_loop():
    while True:
        _publish_camera_backend_once()
        time.sleep(CAMERA_BACKEND_PUBLISH_INTERVAL)


def _open_capture(stream_url):
    import urllib.request
    return urllib.request.urlopen(stream_url, timeout=15)


def _camera_loop(stream_url):
    import urllib.request

    log.info("Camera thread starting")

    current_url = _load_cached_camera_url() or stream_url
    data = bytearray()

    while True:
        try:
            # Always try discovery first on every reconnect.
            try:
                discovered_url = _discover_camera_url(timeout=8)
                if discovered_url:
                    discovered_url = discovered_url.strip()
                    if discovered_url != current_url:
                        log.info("Using discovered ESP32-CAM URL: %s", discovered_url)
                    current_url = discovered_url
                    _save_cached_camera_url(current_url)
            except Exception as exc:
                log.warning("Camera discovery failed; using last known URL: %s", exc)

            stream = urllib.request.urlopen(current_url, timeout=15)
            frames.set_camera_state(True, current_url)
            log.info("Camera stream connected: %s", current_url)

            data.clear()

            while True:
                chunk = stream.read(4096)
                if not chunk:
                    raise RuntimeError("camera stream closed")

                data.extend(chunk)

                start_idx = data.find(b"\xff\xd8")
                if start_idx == -1:
                    if len(data) > 2_000_000:
                        data = data[-1024:]
                    continue

                end_idx = data.find(b"\xff\xd9", start_idx + 2)
                if end_idx == -1:
                    if start_idx > 0:
                        data = data[start_idx:]
                    continue

                jpg = bytes(data[start_idx:end_idx + 2])
                data = data[end_idx + 2:]

                arr = np.frombuffer(jpg, dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    frames.update_raw(frame)

        except Exception as exc:
            frames.set_camera_state(False, current_url, str(exc))
            log.warning("Camera stream failed: %s", exc)

        time.sleep(CAMERA_RECONNECT_SECONDS)

def _recognition_loop():
    global last_recognition

    log.info("Recognition thread starting")
    last_seq = -1
    cooldowns = {}
    unknown_cooldown_until = 0.0
    last_process = 0.0

    while True:
        seq, frame = frames.raw_copy()
        if frame is None or seq == last_seq:
            time.sleep(0.02)
            continue

        now = time.monotonic()
        if now - last_process < FACE_RECOGNITION_INTERVAL:
            time.sleep(0.01)
            continue

        last_seq = seq
        last_process = now
        display = frame.copy()

        if engine is None or face_db is None:
            frames.update_annotated(display)
            continue

        try:
            detected = engine.process_frame(frame)
        except Exception as exc:
            log.error("Face processing error: %s", exc, exc_info=True)
            frames.update_annotated(display)
            time.sleep(0.5)
            continue

        event_now = time.monotonic()
        for face in detected:
            bbox = face["bbox"]
            x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
            result = face_db.identify(face["embedding"], FACE_MATCH_THRESHOLD)

            if result is not None:
                name, score = result
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(
                    display,
                    f"ACCESS GRANTED: {name}",
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                )

                if cooldowns.get(name, 0.0) < event_now:
                    cooldowns[name] = event_now + FACE_COOLDOWN_SECONDS
                    event = {
                        "type": "face_recognized",
                        "name": name,
                        "confidence": round(score, 3),
                        "timestamp": int(time.time()),
                    }
                    log.info("ACCESS GRANTED: %s score=%.3f", name, score)
                    _publish(TOPIC_CMD_DOOR, "GRANTED", qos=1)
                    _publish(TOPIC_FACE_EVENTS, event, qos=1)
                    last_recognition = event
            else:
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(
                    display,
                    "ACCESS DENIED",
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )

                if unknown_cooldown_until < event_now:
                    unknown_cooldown_until = event_now + FACE_UNKNOWN_COOLDOWN_SECONDS
                    event = {"type": "unknown_face", "timestamp": int(time.time())}
                    log.info("ACCESS DENIED: unknown face")
                    _publish(TOPIC_CMD_DOOR, "DENIED", qos=1)
                    _publish(TOPIC_FACE_EVENTS, event, qos=1)
                    last_recognition = event

        frames.update_annotated(display)


def _generate_mjpeg():
    delay = 1.0 / max(1.0, FACE_MJPEG_FPS)
    while True:
        jpg = frames.latest_jpeg() or _offline_jpeg()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Cache-Control: no-cache\r\n"
            b"Content-Length: " + str(len(jpg)).encode("ascii") + b"\r\n\r\n" +
            jpg +
            b"\r\n"
        )
        time.sleep(delay)


def _offline_jpeg():
    global offline_jpeg
    if offline_jpeg is not None:
        return offline_jpeg

    img = np.zeros((360, 640, 3), dtype=np.uint8)
    img[:] = (22, 22, 22)
    cv2.putText(img, "CAMERA OFFLINE", (120, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.25, (0, 180, 255), 3)
    cv2.putText(img, "Check ESP32-CAM IP / WiFi", (115, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 220, 220), 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    offline_jpeg = buf.tobytes() if ok else b""
    return offline_jpeg


@app.route("/")
def index():
    return jsonify({
        "service": "smart_home_face_service",
        "video": "/video",
        "stream": "/stream",
        "snapshot": "/snapshot",
        "status": "/status",
        "faces": "/faces",
        "enroll": "/enroll",
    })


@app.route("/video")
@app.route("/stream")
def video_feed():
    return Response(_generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/snapshot")
def snapshot():
    frame = frames.latest_image_copy()
    if frame is None:
        return Response(_offline_jpeg(), mimetype="image/jpeg")

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return jsonify({"error": "encode failed"}), 500
    return Response(buf.tobytes(), mimetype="image/jpeg")


def _request_name():
    body = request.get_json(silent=True) or {}
    name = request.form.get("name") or request.args.get("name") or body.get("name")
    if not name:
        raise ValueError("name is required")
    return name


@app.route("/enroll", methods=["POST"])
def enroll():
    if engine is None or face_db is None:
        return jsonify({"error": "face engine is not ready"}), 503

    try:
        name = _request_name()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    photo = request.files.get("photo")
    if photo is not None:
        arr = np.frombuffer(photo.read(), dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "could not decode image"}), 400
    else:
        _, frame = frames.raw_copy()
        if frame is None:
            return jsonify({"error": "no camera frame available"}), 503

    faces = engine.process_frame(frame)
    if not faces:
        return jsonify({"error": "no face detected in image"}), 400
    if len(faces) > 1:
        return jsonify({"error": f"multiple faces detected ({len(faces)}); use one face"}), 400

    try:
        total = face_db.enroll(name, faces[0]["embedding"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    _publish(
        TOPIC_FACE_EVENTS,
        {"type": "face_enrolled", "name": name, "embeddings": total, "timestamp": int(time.time())},
        qos=1,
    )
    return jsonify({"status": "ok", "name": name, "total_embeddings": total})


@app.route("/faces", methods=["GET"])
def list_faces():
    stats = face_db.stats() if face_db else {}
    return jsonify({"faces": list(stats.keys()), "count": len(stats), "embeddings": stats})


@app.route("/faces/<name>", methods=["DELETE"])
def delete_face(name):
    if face_db is None:
        return jsonify({"error": "face DB is not ready"}), 503
    if face_db.remove(name):
        _publish(TOPIC_FACE_EVENTS, {"type": "face_deleted", "name": name, "timestamp": int(time.time())})
        return jsonify({"status": "ok", "removed": name})
    return jsonify({"error": f"face '{name}' not found"}), 404


@app.route("/status")
def status():
    face_names = face_db.list_names() if face_db else []
    return jsonify({
        "service": "face_service",
        "uptime_seconds": int(time.time() - service_started),
        "face_engine_ready": engine is not None,
        "faces_enrolled": face_names,
        "faces_count": len(face_names),
        "last_recognition": last_recognition or None,
        "match_threshold": FACE_MATCH_THRESHOLD,
        "cooldown_seconds": FACE_COOLDOWN_SECONDS,
        "backend": _backend_payload(),
    })


def _init_face_engine():
    global engine, face_db
    if not FACE_RECOGNITION_ENABLED:
        log.warning("Face recognition disabled by config")
        return
    face_db = FaceDB(FACE_DB_PATH)
    engine = FaceEngine(FACE_MODEL_DIR)


def _choose_stream_url(args):
    if args.url:
        return args.url

    cached_url = _load_cached_camera_url()
    if cached_url:
        return cached_url

    if args.discover:
        try:
            return _discover_camera_url(timeout=args.discovery_timeout)
        except Exception as exc:
            log.warning("Camera discovery failed; using configured URL: %s", exc)

    return ESP32_CAM_STREAM_URL


def main():
    global service_port
    parser = argparse.ArgumentParser(description="Smart Home Face Recognition Service")
    parser.add_argument("--url", help="Known ESP32-CAM stream URL")
    parser.add_argument("--discover", action="store_true", help="Try UDP ESP32-CAM discovery before config URL")
    parser.add_argument("--discovery-timeout", type=int, default=8)
    parser.add_argument("--port", type=int, default=FACE_SERVICE_PORT)
    args = parser.parse_args()
    service_port = args.port

    try:
        _init_face_engine()
    except Exception as exc:
        log.error("Face engine startup failed: %s", exc, exc_info=True)
        log.error("Video endpoints will still run, but recognition/enrollment need setup_face_recognition.sh")

    stream_url = _choose_stream_url(args)
    frames.set_camera_state(False, stream_url, "starting")

    mqtt_bridge.start()
    _publish_camera_backend_once()

    threading.Thread(target=_camera_loop, args=(stream_url,), daemon=True).start()
    threading.Thread(target=_recognition_loop, daemon=True).start()
    threading.Thread(target=_camera_command_loop, daemon=True).start()
    threading.Thread(target=_camera_backend_loop, daemon=True).start()

    log.info("Starting Flask on %s:%d", FACE_SERVICE_HOST, args.port)
    app.run(host=FACE_SERVICE_HOST, port=args.port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
