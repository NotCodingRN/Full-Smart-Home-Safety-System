#!/usr/bin/env bash
# One-command deploy from laptop/desktop to Raspberry Pi.
#
# Examples:
#   ./deploy_to_pi.sh --host 10.46.211.30 --user alaa-pi
#   ./deploy_to_pi.sh
#
set -euo pipefail

PI_USER="alaa-pi"
PI_HOST=""
REMOTE_DIR="/home/alaa-pi/smart_home_clean/raspberry_pi"
SKIP_DEPS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --host) PI_HOST="$2"; shift 2 ;;
        --user) PI_USER="$2"; shift 2 ;;
        --dir) REMOTE_DIR="$2"; shift 2 ;;
        --skip-deps) SKIP_DEPS=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--host PI_IP_OR_NAME] [--user alaa-pi] [--dir REMOTE_DIR] [--skip-deps]"
            exit 0
            ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [ -z "${PI_HOST}" ]; then
    read -r -p "Enter Pi IP/host (example 10.46.211.30): " PI_HOST
fi

TARGET="${PI_USER}@${PI_HOST}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

FILES=(
    smarthome_config.py
    smarthome_logic.py
    smarthome_weather.py
    smarthome_daemon.py
    smarthome_menu.py
    pic_io.py
    mqtt_bridge.py
    camera_discovery.py
    camera_snapshot.py
    camera_viewer.py
    face_recognition_engine.py
    face_service.py
    aws_cloud_bootstrap.py
    setup_face_recognition.sh
    validate_stack.sh
)

echo ""
echo "================================================"
echo "  Smart Home Deploy"
echo "================================================"
echo "Target: ${TARGET}:${REMOTE_DIR}"
echo ""

echo "[1/6] Checking local files"
for f in "${FILES[@]}"; do
    test -f "${SCRIPT_DIR}/${f}" || { echo "Missing ${f}"; exit 1; }
done

echo "[2/6] Creating remote directories"
ssh "${TARGET}" "mkdir -p '${REMOTE_DIR}/certs' '${REMOTE_DIR}/logs' '${REMOTE_DIR}/known_faces' '${REMOTE_DIR}/models'"

echo "[3/6] Copying source files"
if command -v rsync >/dev/null 2>&1; then
    rsync -av --delete \
        --include='*.py' \
        --include='*.sh' \
        --include='certs/***' \
        --exclude='.claude/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='*.log' \
        --exclude='*.csv' \
        --exclude='known_faces/' \
        --exclude='models/' \
        --exclude='claude-admin-temp_credentials.csv' \
        "${SCRIPT_DIR}/" "${TARGET}:${REMOTE_DIR}/"
else
    for f in "${FILES[@]}"; do
        scp "${SCRIPT_DIR}/${f}" "${TARGET}:${REMOTE_DIR}/${f}"
    done
    if [ -d "${SCRIPT_DIR}/certs" ]; then
        scp -r "${SCRIPT_DIR}/certs/." "${TARGET}:${REMOTE_DIR}/certs/"
    fi
fi

echo "[4/6] Installing/updating Pi services"
ssh "${TARGET}" "REMOTE_DIR='${REMOTE_DIR}' SKIP_DEPS='${SKIP_DEPS}' PI_USER='${PI_USER}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

cd "${REMOTE_DIR}"
chmod +x setup_face_recognition.sh validate_stack.sh || true

if [ "${SKIP_DEPS}" != "1" ]; then
    echo "  Installing base packages"
    sudo apt-get update -qq
    sudo apt-get install -y \
        curl \
        mosquitto \
        mosquitto-clients \
        python3-flask \
        python3-numpy \
        python3-opencv \
        python3-paho-mqtt \
        python3-pip \
        python3-serial
fi

sudo systemctl enable --now mosquitto

echo "  Validating Python syntax"
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
    camera_viewer.py

echo "  Installing systemd unit: smarthome.service"
sudo tee /etc/systemd/system/smarthome.service >/dev/null <<SERVICE
[Unit]
Description=Smart Home Local-First Daemon
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=${PI_USER}
WorkingDirectory=${REMOTE_DIR}
Environment=SMARTHOME_APP_DIR=${REMOTE_DIR}
ExecStart=/usr/bin/python3 ${REMOTE_DIR}/smarthome_daemon.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

echo "  Installing systemd unit: face-recognition.service"
sudo tee /etc/systemd/system/face-recognition.service >/dev/null <<SERVICE
[Unit]
Description=Smart Home Local Face Recognition Service
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=${PI_USER}
WorkingDirectory=${REMOTE_DIR}
Environment=SMARTHOME_APP_DIR=${REMOTE_DIR}
ExecStart=/usr/bin/python3 ${REMOTE_DIR}/face_service.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

chmod 600 "${REMOTE_DIR}"/certs/*.key 2>/dev/null || true
chmod 644 "${REMOTE_DIR}"/certs/*.pem "${REMOTE_DIR}"/certs/*.crt 2>/dev/null || true

sudo systemctl daemon-reload
sudo systemctl enable smarthome.service face-recognition.service
REMOTE_SCRIPT

echo "[5/6] Restarting services"
ssh "${TARGET}" "sudo systemctl restart smarthome.service face-recognition.service"

echo "[6/6] Running validation"
ssh "${TARGET}" "cd '${REMOTE_DIR}' && ./validate_stack.sh --quick"

echo ""
echo "================================================"
echo "  Deploy complete"
echo "================================================"
echo "Useful commands:"
echo "  ssh ${TARGET}"
echo "  journalctl -u smarthome -f"
echo "  journalctl -u face-recognition -f"
echo "  curl http://${PI_HOST}:5000/status"
echo "  open http://${PI_HOST}:5000/video"
