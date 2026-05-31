# HuggingFace Model/Dataset Card

This project uses a lightweight local face-recognition pipeline:

- Face detector: OpenCV Haar Cascade
- Embedding model: FaceNet ONNX
- Embedding size: 128 dimensions
- Similarity metric: cosine similarity
- Match threshold: `0.55`
- Enrollment database: `known_faces/face_db.json`

## Dataset

Representative project data is included at:

```text
data/demo_sensor_control_log.csv
```

It contains timestamped sensor values, warning flags, control signals, face events, confidence scores, and inference-time samples used by:

```text
notebooks/smarthome_finetuning_analysis.ipynb
```

## Suggested HuggingFace Upload Structure

Create one dataset/model repository named:

```text
zewail-smart-home-face-telemetry
```

Upload:

```text
data/demo_sensor_control_log.csv
notebooks/smarthome_finetuning_analysis.ipynb
docs/figures/sensor_trends.png
docs/figures/control_signals.png
docs/figures/face_scores.png
```

For the face model, include either:

```text
models/facenet.onnx
```

or cite the external FaceNet ONNX model used by `setup_face_recognition.sh`.

## Citation Text For README

```text
The project uses a FaceNet ONNX embedding model with OpenCV face detection. The representative telemetry/control dataset and notebook are packaged in this repository and are HuggingFace-ready under the name `zewail-smart-home-face-telemetry`.
```