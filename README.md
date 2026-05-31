# Local-First Smart Home Safety and Access Control System


## Overview

This project is a local-first cyber-physical smart home and smart irrigation system. The Raspberry Pi remains the real-time controller even when AWS or internet access fails. AWS IoT, DynamoDB, Lambda, SNS, and WeatherAPI are cloud enhancements for remote commands, telemetry history, smart irrigation decisions, and alerts.

Main functions:

* PIC16F877A reads MQ-2, DHT11, two soil/leak sensors, two IR sensors, and drives three relays, a servo, and a 16x2 I2C LCD.
* Raspberry Pi communicates with the PIC by UART, runs Mosquitto, automation, smart irrigation logic, face recognition, and camera HTTP endpoints.
* ESP32-CAM streams MJPEG locally.
* Flutter app controls relays/door, requests camera URLs over MQTT, opens the local stream, enrolls/deletes faces, and shows events.
* AWS IoT Core receives telemetry and commands; DynamoDB stores history through IoT Rule + Lambda.
* WeatherAPI integration prevents unnecessary irrigation when rain is expected in the next few hours.
* The system continues operating locally even if AWS or internet access is unavailable.

Main safety-critical features:

1. Gas leak detection with automatic fan activation.
2. Smart irrigation with weather-aware pump control and leak alerts.
3. Face-recognition-based access control with intrusion detection.
4. IR-Sensors to monitor intrusions through windows and doors.

## Layout

```text
code/raspberry_pi/         Linux controller, MQTT, UART, face service
code/pic16f877a_firmware/  PIC firmware organized as Common/MCAL/HAL/Services/APP
code/esp32_cam/            ESP32-CAM firmware
code/flutter_app/          Mobile app source, with placeholder certs only
docker/                    Dockerfile and compose demo environment
docs/report/               Main report and bonus report
docs/figures/              Architecture, IO map, plots, schematics
notebooks/                 ML/telemetry analysis notebook
data/                      Demo telemetry/control dataset
hardware/                  Schematics and PCB design archive
```

Key documents:

- `docs/report/REPORT_SmartHome.docx`: main required report, max 10-page target
- `docs/report/REPORT_SmartHome.md`: editable Markdown version of the main report
- `docs/report/REPORT_Bonus_Cloud_PCB.md`: separate bonus/cloud/PCB report
- `docs/SUBMISSION_CHECKLIST.md`: checklist mapped to the assignment deliverables

## Raspberry Pi Setup

```bash
sudo raspi-config
# Interface Options -> Serial Port -> login shell: No, serial hardware: Yes
sudo reboot
sudo apt update
sudo apt install -y python3-pip python3-serial python3-flask python3-numpy python3-opencv python3-paho-mqtt mosquitto mosquitto-clients curl
pip3 install --break-system-packages onnxruntime boto3
```

Copy `code/raspberry_pi/` to `/home/alaa-pi/smart_home_clean/raspberry_pi`.

Create AWS IoT certificates from AWS IoT Core and place them in `certs/` on the Pi:

- `AmazonRootCA1.pem`
- `device-certificate.pem.crt`
- `private.pem.key`

Real certificates are not included in this submission.

Install/start services:

```bash
cd ~/smart_home_clean/raspberry_pi
chmod +x setup_face_recognition.sh validate_stack.sh
./setup_face_recognition.sh
sudo systemctl enable --now mosquitto smarthome face-recognition
./validate_stack.sh --quick
```

For phone-to-local-MQTT mode, Mosquitto must listen on the LAN. Create `/etc/mosquitto/conf.d/smarthome_lan.conf`:

```text
listener 1883 0.0.0.0
allow_anonymous true
```

Then:

```bash
sudo systemctl restart mosquitto
```

For real deployments, use username/password or TLS instead of anonymous MQTT.

## AWS Backend

Resources:

- AWS IoT Core Thing/certificate
- IoT Policy for `smarthome/*`
- DynamoDB table `SmartHomeEvents`
- Lambda `SmartHomeTelemetryWriter`
- IoT Rule `SmartHomeToHistory`
- SNS topic `SmartHomeAlerts`

Run after configuring AWS CLI credentials:

```bash
cd code/raspberry_pi
python3 aws_cloud_bootstrap.py --region eu-central-1 --cert-arn <YOUR_IOT_CERT_ARN>
```

The IoT Rule SQL is:

```sql
SELECT *, topic() as topic, timestamp() as ts FROM 'smarthome/#'
```

## PIC Firmware

Use MPLAB X/XC8 with include paths:

```text
Common
MCAL/GPIO
MCAL/ADC
MCAL/UART
MCAL/I2C
Services/SmartHomeIO
```

K150/MPLAB fuses:

```text
Oscillator: HS
WDT: Disabled
PWRTE: Enabled
BODEN: Enabled
LVP: Disabled
Code Protect: Disabled
CPD: Disabled
```

## ESP32-CAM

Open `code/esp32_cam/esp32_cam_udp_stream/esp32_cam_udp_stream.ino`, enter WiFi credentials, and upload to AI-Thinker ESP32-CAM. The Pi uses UDP discovery or `ESP32_CAM_STREAM_URL=http://<ESP32_IP>:80/stream`.

## Flutter App

```bash
cd code/flutter_app
flutter pub get
flutter build apk --debug
adb install -r build/app/outputs/flutter-apk/app-debug.apk
```

For AWS demo mode, replace placeholder files in `assets/certs/` with your own IoT certificate files. For production, do not embed private keys in an APK; use Cognito, a custom authorizer, or a backend token service.

## Docker

Docker Image created and available at smarthome-final.tar

The container runs a dry-run/simulation environment. Physical UART/camera/relays still require Raspberry Pi hardware.

## Results

- Local Pi services operate offline.
- PIC UART supports `PING`, `GET`, relay, LCD, and access commands.
- MQTT publishes sensor/status/alert/camera backend topics.
- AWS stores telemetry in DynamoDB and can publish alerts through SNS.
- Flutter app controls actuators, opens LAN video, and handles face enrollment/list/delete.
- PCB/schematic files are included for the hardware packaging bonus.

## ML Dataset / HuggingFace Note

The representative telemetry/control dataset and model-analysis notebook are included locally:

```text
data/demo_sensor_control_log.csv
notebooks/smarthome_finetuning_analysis.ipynb
docs/ml/HUGGINGFACE_MODEL_DATASET_CARD.md
```

The face pipeline uses OpenCV face detection and a FaceNet ONNX embedding model. No private face images are included in this submission.
