#!/usr/bin/env bash
set -u

QUICK=0
PIC_DIRECT=0
if [ "${1:-}" = "--quick" ]; then
    QUICK=1
elif [ "${1:-}" = "--pic-direct" ]; then
    PIC_DIRECT=1
fi

FAIL=0

ok() { echo "[OK]   $*"; }
warn() { echo "[WARN] $*"; }
bad() { echo "[FAIL] $*"; FAIL=1; }

echo "================================================"
echo "  Smart Home Stack Validation"
echo "================================================"

cd "$(dirname "$0")" || exit 1

python3 -m py_compile \
    smarthome_config.py \
    smarthome_logic.py \
    smarthome_weather.py \
    pic_io.py \
    mqtt_bridge.py \
    face_recognition_engine.py \
    face_service.py \
    aws_cloud_bootstrap.py \
    smarthome_daemon.py \
    smarthome_menu.py \
    camera_discovery.py \
    camera_snapshot.py \
    camera_viewer.py \
    >/dev/null 2>&1 && ok "Python syntax" || bad "Python syntax"

systemctl is-active --quiet mosquitto && ok "Mosquitto service active" || bad "Mosquitto service is not active"
systemctl is-active --quiet smarthome && ok "smarthome service active" || bad "smarthome service is not active"
systemctl is-active --quiet face-recognition && ok "face-recognition service active" || warn "face-recognition service is not active"

if command -v mosquitto_pub >/dev/null 2>&1; then
    mosquitto_pub -h 127.0.0.1 -t smarthome/validate -m '{"ok":true}' >/dev/null 2>&1 \
        && ok "Local MQTT publish" || bad "Local MQTT publish failed"
else
    warn "mosquitto_pub missing"
fi

if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 http://127.0.0.1:5000/status >/tmp/smarthome_face_status.json 2>/dev/null \
        && ok "Face service /status" || warn "Face service /status not reachable yet"
else
    warn "curl missing"
fi

if [ "${QUICK}" != "1" ]; then
    if systemctl is-active --quiet smarthome && [ "${PIC_DIRECT}" != "1" ]; then
        ok "PIC UART owned by smarthome service"
        warn "Direct PIC test skipped because smarthome keeps /dev/serial0 exclusively locked"
        warn "For a direct UART test: sudo systemctl stop smarthome && ./validate_stack.sh --pic-direct && sudo systemctl start smarthome"
    else
    python3 - <<'PY'
from pic_io import PicIoBoard
pic = PicIoBoard()
print("PIC ID:", pic.identify())
print("PIC PING:", pic.ping())
print("PIC GET:", pic.get_sensors())
pic.close()
PY
        if [ $? -eq 0 ]; then
            ok "PIC UART command test"
        else
            bad "PIC UART command test failed"
        fi
    fi
fi

echo ""
echo "Recent smarthome logs:"
journalctl -u smarthome -n 12 --no-pager 2>/dev/null || true

echo ""
echo "Recent face-recognition logs:"
journalctl -u face-recognition -n 12 --no-pager 2>/dev/null || true

echo ""
if [ "${FAIL}" -eq 0 ]; then
    ok "Validation finished"
else
    bad "Validation found problems"
fi

exit "${FAIL}"
