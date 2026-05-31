# =============================================================================
# smarthome_config.py
# Central runtime configuration.  Defaults are Pi-friendly, but every important
# value can be overridden with an environment variable for testing/deployment.
# =============================================================================

import os


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
APP_DIR = os.environ.get(
    "SMARTHOME_APP_DIR",
    os.path.dirname(os.path.abspath(__file__)),
)

LOG_DIR = os.environ.get("SMARTHOME_LOG_DIR", os.path.join(APP_DIR, "logs"))
CERT_DIR = os.environ.get("SMARTHOME_CERT_DIR", os.path.join(APP_DIR, "certs"))
FACE_DB_DIR = os.environ.get("SMARTHOME_FACE_DB_DIR", os.path.join(APP_DIR, "known_faces"))
FACE_MODEL_DIR = os.environ.get("SMARTHOME_FACE_MODEL_DIR", os.path.join(APP_DIR, "models"))


# ---------------------------------------------------------------------------
# PIC UART
# ---------------------------------------------------------------------------
PIC_SERIAL_PORT = os.environ.get("PIC_SERIAL_PORT", "/dev/serial0")
PIC_SERIAL_BAUD = _env_int("PIC_SERIAL_BAUD", 9600)
PIC_SERIAL_TIMEOUT = _env_float("PIC_SERIAL_TIMEOUT", 2.5)
PIC_COMMAND_RETRIES = _env_int("PIC_COMMAND_RETRIES", 2)


# ---------------------------------------------------------------------------
# MQTT (LOCAL + CLOUD)
# ---------------------------------------------------------------------------
LOCAL_MQTT_ENABLED = _env_bool("SMARTHOME_LOCAL_MQTT_ENABLED", True)
LOCAL_MQTT_HOST = os.environ.get("SMARTHOME_LOCAL_MQTT_HOST", "127.0.0.1")
LOCAL_MQTT_PORT = _env_int("SMARTHOME_LOCAL_MQTT_PORT", 1883)

MQTT_KEEPALIVE = _env_int("SMARTHOME_MQTT_KEEPALIVE", 45)
MQTT_RECONNECT_MIN = _env_int("SMARTHOME_MQTT_RECONNECT_MIN", 2)
MQTT_RECONNECT_MAX = _env_int("SMARTHOME_MQTT_RECONNECT_MAX", 60)
MQTT_QUEUE_SIZE = _env_int("SMARTHOME_MQTT_QUEUE_SIZE", 250)


# ---------------------------------------------------------------------------
# AWS CLOUD
# ---------------------------------------------------------------------------
AWS_ENABLED = _env_bool("SMARTHOME_AWS_ENABLED", True)
AWS_ENDPOINT = os.environ.get(
    "SMARTHOME_AWS_ENDPOINT",
    "a184ggwa834ixr-ats.iot.eu-central-1.amazonaws.com",
)
AWS_PORT = _env_int("SMARTHOME_AWS_PORT", 8883)
AWS_CLIENT_ID_PREFIX = os.environ.get("SMARTHOME_AWS_CLIENT_ID_PREFIX", "smarthome-pi")

CA_CERT = os.environ.get("SMARTHOME_CA_CERT", os.path.join(CERT_DIR, "AmazonRootCA1.pem"))
DEVICE_CERT = os.environ.get(
    "SMARTHOME_DEVICE_CERT",
    os.path.join(CERT_DIR, "device-certificate.pem.crt"),
)
PRIVATE_KEY = os.environ.get("SMARTHOME_PRIVATE_KEY", os.path.join(CERT_DIR, "private.pem.key"))


# ---------------------------------------------------------------------------
# MQTT TOPICS
# ---------------------------------------------------------------------------
TOPIC_ROOT = os.environ.get("SMARTHOME_TOPIC_ROOT", "smarthome")

TOPIC_SENSORS = f"{TOPIC_ROOT}/sensors"
TOPIC_ALERTS = f"{TOPIC_ROOT}/alerts"
TOPIC_STATUS = f"{TOPIC_ROOT}/status"
TOPIC_FACE_EVENTS = f"{TOPIC_ROOT}/face"
TOPIC_CAMERA_BACKEND = f"{TOPIC_ROOT}/camera/backend"

TOPIC_CMD_FAN1 = f"{TOPIC_ROOT}/cmd/fan1"
TOPIC_CMD_FAN2 = f"{TOPIC_ROOT}/cmd/fan2"
TOPIC_CMD_PUMP = f"{TOPIC_ROOT}/cmd/pump"
TOPIC_CMD_DOOR = f"{TOPIC_ROOT}/cmd/door"
TOPIC_CMD_ALL = f"{TOPIC_ROOT}/cmd/all_off"
TOPIC_CMD_CAMERA = f"{TOPIC_ROOT}/cmd/camera"


# ---------------------------------------------------------------------------
# RELAYS
# ---------------------------------------------------------------------------
RELAY_KITCHEN_FAN = 1
RELAY_ROOM_FAN = 2
RELAY_PUMP = 3

RELAY_FAN1 = RELAY_KITCHEN_FAN
RELAY_FAN2 = RELAY_ROOM_FAN


# ---------------------------------------------------------------------------
# THRESHOLDS
# ---------------------------------------------------------------------------
MQ2_ALERT_THRESHOLD = _env_int("SMARTHOME_MQ2_ALERT_THRESHOLD", 200)
GARDEN_DRY_THRESHOLD = _env_int("SMARTHOME_GARDEN_DRY_THRESHOLD", 300)
LEAK_ALERT_THRESHOLD = _env_int("SMARTHOME_LEAK_ALERT_THRESHOLD", 300)

IR_DOOR_LABEL = {
    0: "Front door",
    1: "Window",
}


# ---------------------------------------------------------------------------
# WEATHER
# ---------------------------------------------------------------------------
WEATHER_API_KEY = os.environ.get("WEATHERAPI_KEY", "")
WEATHER_LOCATION = os.environ.get("SMARTHOME_WEATHER_LOCATION", "Zewail City, Giza, Egypt")
WEATHER_LOOKAHEAD_HOURS = _env_int("SMARTHOME_WEATHER_LOOKAHEAD_HOURS", 5)
RAIN_CHANCE_THRESHOLD = _env_int("SMARTHOME_RAIN_CHANCE_THRESHOLD", 40)
WEATHER_REFRESH_INTERVAL = _env_int("SMARTHOME_WEATHER_REFRESH_INTERVAL", 15 * 60)
WEATHER_TIMEOUT_SECONDS = _env_float("SMARTHOME_WEATHER_TIMEOUT_SECONDS", 4.0)


# ---------------------------------------------------------------------------
# CAMERA / FACE SERVICE
# ---------------------------------------------------------------------------
ESP32_CAM_STREAM_URL = os.environ.get(
    "ESP32_CAM_STREAM_URL",
    "http://10.171.153.153:80/stream",
)

FACE_RECOGNITION_ENABLED = _env_bool("SMARTHOME_FACE_RECOGNITION_ENABLED", True)
FACE_SERVICE_HOST = os.environ.get("SMARTHOME_FACE_SERVICE_HOST", "0.0.0.0")
FACE_SERVICE_PORT = _env_int("SMARTHOME_FACE_SERVICE_PORT", 5000)
FACE_PUBLIC_HOST = os.environ.get("SMARTHOME_FACE_PUBLIC_HOST", "")

FACE_MATCH_THRESHOLD = _env_float("SMARTHOME_FACE_MATCH_THRESHOLD", 0.55)
FACE_COOLDOWN_SECONDS = _env_float("SMARTHOME_FACE_COOLDOWN_SECONDS", 10.0)
FACE_UNKNOWN_COOLDOWN_SECONDS = _env_float("SMARTHOME_FACE_UNKNOWN_COOLDOWN_SECONDS", 30.0)
FACE_RECOGNITION_INTERVAL = _env_float("SMARTHOME_FACE_RECOGNITION_INTERVAL", 0.25)
FACE_MJPEG_FPS = _env_float("SMARTHOME_FACE_MJPEG_FPS", 8.0)
FACE_JPEG_QUALITY = _env_int("SMARTHOME_FACE_JPEG_QUALITY", 70)
CAMERA_RECONNECT_SECONDS = _env_float("SMARTHOME_CAMERA_RECONNECT_SECONDS", 2.0)
CAMERA_BACKEND_PUBLISH_INTERVAL = _env_float(
    "SMARTHOME_CAMERA_BACKEND_PUBLISH_INTERVAL",
    30.0,
)

FACE_DB_PATH = os.environ.get("SMARTHOME_FACE_DB_PATH", os.path.join(FACE_DB_DIR, "face_db.json"))


# ---------------------------------------------------------------------------
# TIMING
# ---------------------------------------------------------------------------
SENSOR_POLL_INTERVAL = _env_float("SMARTHOME_SENSOR_POLL_INTERVAL", 1.0)
PUBLISH_INTERVAL = _env_float("SMARTHOME_PUBLISH_INTERVAL", 3.0)
STATUS_PUBLISH_INTERVAL = _env_float("SMARTHOME_STATUS_PUBLISH_INTERVAL", 3.0)
LCD_STATUS_INTERVAL = _env_float("SMARTHOME_LCD_STATUS_INTERVAL", 4.0)
COMMAND_DEDUP_SECONDS = _env_float("SMARTHOME_COMMAND_DEDUP_SECONDS", 0.8)
DOOR_HOLD_SECONDS = _env_float("SMARTHOME_DOOR_HOLD_SECONDS", 5.0)


# ---------------------------------------------------------------------------
# LCD
# ---------------------------------------------------------------------------
LCD_BOOT_LINE1 = os.environ.get("SMARTHOME_LCD_BOOT_LINE1", "SMART HOME")
LCD_BOOT_LINE2 = os.environ.get("SMARTHOME_LCD_BOOT_LINE2", "BOOTING...")
LCD_READY_LINE2 = os.environ.get("SMARTHOME_LCD_READY_LINE2", "SYSTEM READY")
