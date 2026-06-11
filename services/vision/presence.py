"""Staged presence pipeline (PLAN_FINAL §3.2):

motion (OpenCV frame-diff, ~0% CPU) -> person (YOLO11n INT8 on the iGPU via
OpenVINO, ~25-35 ms) -> face (InsightFace buffalo_sc, CPU, ~20-60 ms) ->
hysteresis -> POST event to orchestrator.

This module owns /dev/video0 exclusively (V4L2 streaming is single-consumer).
api.py serves the latest frame to the orchestrator (ver_camara tool).

TODO(Fase 5): calibrate thresholds on real hardware; enroll faces with
scripts in docs/RUNBOOK.md (save mean embeddings to /faces/<name>.npy).
"""

import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from loguru import logger

DETECT_FPS = float(os.getenv("DETECT_FPS", "2"))
MOTION_MIN_AREA = 4000                      # px² of changed area to count as motion
MATCH_THRESHOLD = 0.45                      # cosine similarity vs known embeddings
CONSECUTIVE_MATCHES = 3                     # frames of same identity before event
ABSENCE_MINUTES = 30                        # only greet if away longer than this
GREET_COOLDOWN_MINUTES = 60
ORCHESTRATOR = os.getenv("ORCHESTRATOR_EVENTS", "http://orchestrator:8070")
FACES_DIR = Path("/faces")

latest_jpeg: bytes | None = None            # shared with api.py
_lock = threading.Lock()


def get_latest_jpeg() -> bytes | None:
    with _lock:
        return latest_jpeg


class PresenceService:
    def __init__(self):
        self._yolo = self._load_yolo()
        self._faces = self._load_faces()
        self._app = self._load_insightface()
        self._last_seen: dict[str, float] = {}
        self._last_greeted: dict[str, float] = {}
        self._streak: tuple[str, int] | None = None

    # -- model loading ---------------------------------------------------------

    def _load_yolo(self):
        import openvino as ov

        model_dir = Path(os.getenv("YOLO_MODEL_DIR", "/models/yolo11n_int8_320_openvino"))
        xml = next(model_dir.glob("*.xml"), None)
        if not xml:
            logger.warning(f"YOLO model not found in {model_dir} — person stage disabled")
            return None
        core = ov.Core()
        device = os.getenv("OPENVINO_DEVICE", "GPU")
        try:
            model = core.compile_model(str(xml), device)
            logger.info(f"YOLO11n compiled on {device}")
            return model
        except Exception as e:
            logger.warning(f"OpenVINO {device} failed ({e}); falling back to CPU")
            return core.compile_model(str(xml), "CPU")

    def _load_insightface(self):
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(
            name=os.getenv("FACE_PACK", "buffalo_sc"),
            root=os.getenv("INSIGHTFACE_HOME", "/models/insightface"),
            allowed_modules=["detection", "recognition"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))   # ctx_id=-1 → CPU
        return app

    def _load_faces(self) -> dict[str, np.ndarray]:
        faces = {}
        if FACES_DIR.exists():
            for f in FACES_DIR.glob("*.npy"):
                faces[f.stem] = np.load(f)
        logger.info(f"known faces: {list(faces)}")
        return faces

    # -- stages -----------------------------------------------------------------

    def _person_detected(self, frame) -> bool:
        if self._yolo is None:
            return True                              # degrade gracefully: skip stage
        img = cv2.resize(frame, (320, 320))
        blob = img.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        out = self._yolo(blob)[self._yolo.output(0)]
        # TODO(Fase 5): proper YOLO post-process (NMS) — this is a coarse check
        # for class 0 (person) above confidence on the raw output.
        return bool((out[..., 4] * out[..., 5]).max() > 0.5) if out.ndim == 3 else True

    def _identify(self, frame) -> str | None:
        for face in self._app.get(frame):
            emb = face.normed_embedding
            best, best_sim = None, 0.0
            for name, known in self._faces.items():
                sim = float(np.dot(emb, known) / (np.linalg.norm(known) + 1e-9))
                if sim > best_sim:
                    best, best_sim = name, sim
            if best and best_sim >= MATCH_THRESHOLD:
                return best
        return None

    def _maybe_greet(self, person: str) -> None:
        now = time.time()
        away = now - self._last_seen.get(person, 0) > ABSENCE_MINUTES * 60
        cooled = now - self._last_greeted.get(person, 0) > GREET_COOLDOWN_MINUTES * 60
        self._last_seen[person] = now
        if not (away and cooled):
            return
        self._last_greeted[person] = now
        try:
            requests.post(f"{ORCHESTRATOR}/event/presence", json={"person": person}, timeout=5)
            logger.info(f"presence event sent: {person}")
        except requests.RequestException as e:
            logger.warning(f"presence event failed: {e}")

    # -- main loop ----------------------------------------------------------------

    def run(self) -> None:
        global latest_jpeg
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("cannot open /dev/video0")
            return
        prev_gray = None
        interval = 1.0 / DETECT_FPS

        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(1)
                continue

            ok_jpg, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok_jpg:
                with _lock:
                    latest_jpeg = jpg.tobytes()

            gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (21, 21), 0)
            motion = False
            if prev_gray is not None:
                delta = cv2.threshold(cv2.absdiff(prev_gray, gray), 25, 255, cv2.THRESH_BINARY)[1]
                motion = int(delta.sum() / 255) > MOTION_MIN_AREA
            prev_gray = gray

            if motion and self._person_detected(frame):
                person = self._identify(frame)
                if person:
                    name, count = (person, self._streak[1] + 1) if self._streak and self._streak[0] == person else (person, 1)
                    self._streak = (name, count)
                    if count >= CONSECUTIVE_MATCHES:
                        self._maybe_greet(person)
                        self._streak = None
                else:
                    self._streak = None

            time.sleep(interval)


def start_in_thread() -> None:
    threading.Thread(target=PresenceService().run, daemon=True).start()
