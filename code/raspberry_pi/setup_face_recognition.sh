#!/usr/bin/env bash
# Install face-recognition runtime dependencies on the Raspberry Pi.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="${SMARTHOME_SERVICE_USER:-$(id -un)}"
MODEL_DIR="${SCRIPT_DIR}/models"
FACES_DIR="${SCRIPT_DIR}/known_faces"
MODEL_FILE="${MODEL_DIR}/facenet.onnx"
MODEL_URL="${FACENET_ONNX_URL:-https://github.com/NicolasSM-001/faceNet.onnx-/raw/main/faceNet.onnx}"

echo ""
echo "================================================"
echo "  Smart Home Face Recognition Setup"
echo "================================================"
echo ""

echo "[1/5] Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y \
    curl \
    libatlas-base-dev \
    libopencv-dev \
    mosquitto \
    mosquitto-clients \
    python3-flask \
    python3-numpy \
    python3-opencv \
    python3-paho-mqtt \
    python3-pip \
    python3-serial \
    wget

echo "[2/5] Installing ONNX Runtime"
if python3 -c "import onnxruntime" >/dev/null 2>&1; then
    echo "  onnxruntime already installed"
else
    if ! pip3 install --break-system-packages onnxruntime; then
        echo ""
        echo "  WARNING: onnxruntime install failed."
        echo "  If your Pi OS is 32-bit, install a 64-bit Raspberry Pi OS image or a compatible onnxruntime wheel."
        echo "  The camera service will still run, but recognition/enrollment will not work until this is fixed."
        echo ""
    fi
fi

echo "[3/5] Creating model and face DB directories"
mkdir -p "${MODEL_DIR}" "${FACES_DIR}" "${SCRIPT_DIR}/logs"

echo "[4/5] Ensuring FaceNet ONNX model exists"
if [ -s "${MODEL_FILE}" ]; then
    echo "  Model already exists: ${MODEL_FILE}"
else
    echo "  Downloading ${MODEL_URL}"
    wget -O "${MODEL_FILE}" "${MODEL_URL}"
fi

echo "[5/5] Installing/reloading face-recognition systemd service"
sudo tee /etc/systemd/system/face-recognition.service >/dev/null <<SERVICE
[Unit]
Description=Smart Home Local Face Recognition Service
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
Environment=SMARTHOME_APP_DIR=${SCRIPT_DIR}
ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/face_service.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable face-recognition.service

echo ""
echo "Setup done."
echo "Test:"
echo "  cd ${SCRIPT_DIR}"
echo "  python3 face_service.py --url http://<ESP32_IP>:80/stream"
echo "  curl http://127.0.0.1:5000/status"
