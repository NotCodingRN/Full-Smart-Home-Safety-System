import json
import logging
import os
import threading

import cv2
import numpy as np


log = logging.getLogger("face_engine")


class FaceDB:
    """Persistent face embedding storage in face_db.json."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._data = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.db_path):
            log.info("No face DB found at %s; starting empty", self.db_path)
            return

        with open(self.db_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        for name, entries in raw.items():
            self._data[name] = [np.array(e, dtype=np.float32) for e in entries]
        log.info("Loaded %d enrolled people from %s", len(self._data), self.db_path)

    def _save(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        raw = {name: [e.tolist() for e in embeds] for name, embeds in self._data.items()}
        tmp = self.db_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, separators=(",", ":"), sort_keys=True)
        os.replace(tmp, self.db_path)

    def enroll(self, name, embedding):
        clean_name = self._clean_name(name)
        with self._lock:
            self._data.setdefault(clean_name, [])
            self._data[clean_name].append(embedding.astype(np.float32))
            self._data[clean_name] = self._data[clean_name][-5:]
            total = len(self._data[clean_name])
            self._save()
        log.info("Enrolled face for '%s' (%d embeddings)", clean_name, total)
        return total

    def remove(self, name):
        clean_name = self._clean_name(name)
        with self._lock:
            if clean_name not in self._data:
                return False
            del self._data[clean_name]
            self._save()
        log.info("Removed face '%s'", clean_name)
        return True

    def list_names(self):
        with self._lock:
            return sorted(self._data.keys())

    def stats(self):
        with self._lock:
            return {name: len(entries) for name, entries in sorted(self._data.items())}

    def identify(self, embedding, threshold):
        with self._lock:
            if not self._data:
                return None

            best_name = None
            best_score = -1.0
            emb_norm = embedding / (np.linalg.norm(embedding) + 1e-10)

            for name, stored_list in self._data.items():
                for stored in stored_list:
                    stored_norm = stored / (np.linalg.norm(stored) + 1e-10)
                    score = float(np.dot(emb_norm, stored_norm))
                    if score > best_score:
                        best_score = score
                        best_name = name

            if best_name is not None and best_score >= threshold:
                return best_name, best_score
            return None

    @staticmethod
    def _clean_name(name):
        clean = str(name).strip()
        clean = "".join(ch for ch in clean if ch.isalnum() or ch in (" ", "_", "-")).strip()
        if not clean:
            raise ValueError("name cannot be empty")
        return clean[:40]


class FaceEngine:
    """Haar cascade detection + FaceNet ONNX embeddings."""

    def __init__(self, model_dir):
        self._model_dir = model_dir
        self._detector = None
        self._session = None
        self._input_name = None
        self._input_size = (160, 160)
        self._input_layout = "NHWC"
        self._init_detector()
        self._init_embedder()

    def _init_detector(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._detector = cv2.CascadeClassifier(cascade_path)
        if self._detector.empty():
            raise FileNotFoundError(f"Haar cascade not found at {cascade_path}")
        log.info("Haar cascade face detector loaded")

    def _init_embedder(self):
        import onnxruntime as ort

        model_path = os.path.join(self._model_dir, "facenet.onnx")
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"FaceNet model not found at {model_path}. Run setup_face_recognition.sh first."
            )

        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=self._session_options(ort),
        )

        inp = self._session.get_inputs()[0]
        self._input_name = inp.name
        shape = list(inp.shape)
        self._input_layout, self._input_size = self._parse_input_shape(shape)
        out_shape = self._session.get_outputs()[0].shape
        log.info(
            "FaceNet ONNX loaded: %s input=%s layout=%s size=%s output=%s",
            model_path,
            shape,
            self._input_layout,
            self._input_size,
            out_shape,
        )

    @staticmethod
    def _session_options(ort):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        return opts

    @staticmethod
    def _parse_input_shape(shape):
        if len(shape) != 4:
            return "NHWC", (160, 160)

        def dim(index, fallback):
            value = shape[index]
            return fallback if value is None or isinstance(value, str) else int(value)

        if shape[1] in (1, 3):
            return "NCHW", (dim(3, 160), dim(2, 160))
        return "NHWC", (dim(2, 160), dim(1, 160))

    def detect_faces(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        rects = self._detector.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=5,
            minSize=(60, 60),
        )

        h, w = frame.shape[:2]
        boxes = []
        for (x, y, bw, bh) in rects:
            boxes.append({
                "x1": max(0, int(x)),
                "y1": max(0, int(y)),
                "x2": min(w, int(x + bw)),
                "y2": min(h, int(y + bh)),
                "conf": 1.0,
            })
        return boxes

    def get_embedding(self, frame, bbox):
        pad = 20
        h, w = frame.shape[:2]
        x1 = max(0, int(bbox["x1"]) - pad)
        y1 = max(0, int(bbox["y1"]) - pad)
        x2 = min(w, int(bbox["x2"]) + pad)
        y2 = min(h, int(bbox["y2"]) + pad)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        inp_w, inp_h = self._input_size
        face = cv2.resize(crop, (inp_w, inp_h), interpolation=cv2.INTER_AREA)
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        face = (face - 127.5) / 128.0

        if self._input_layout == "NCHW":
            face = np.transpose(face, (2, 0, 1))

        face = np.expand_dims(face, axis=0).astype(np.float32)
        outputs = self._session.run(None, {self._input_name: face})
        return outputs[0].flatten().astype(np.float32)

    def process_frame(self, frame):
        boxes = self.detect_faces(frame)
        results = []
        for bbox in boxes:
            embedding = self.get_embedding(frame, bbox)
            if embedding is not None:
                results.append({"bbox": bbox, "embedding": embedding})
        return results
