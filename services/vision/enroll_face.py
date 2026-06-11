"""Face enrollment CLI (PLAN_FINAL §3.2, Fase 5).

Collects face samples from a directory of images or from /dev/video0,
extracts InsightFace normed embeddings (strictly one face per image),
averages them, re-normalizes to a unit vector and saves the template to
/faces/<name>.npy — the format presence.py matches against.

Usage (inside the vision container; stop the vision service first when
using the camera, V4L2 streaming is single-consumer):

    docker compose run --rm vision python3 enroll_face.py --name jose --from-camera 8
    docker compose run --rm vision python3 enroll_face.py --name jose --from-dir /faces/samples
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np

FACES_DIR = Path(os.getenv("FACES_DIR", "/faces"))
IMAGE_SUFFIXES = {".jpg", ".png"}
MIN_PAIR_SIMILARITY = 0.5      # below this, samples likely mix persons / bad shots
COUNTDOWN_SECS = 3
CAPTURE_INTERVAL_SECS = 1.0
RECOMMENDED_SAMPLES = 5


def load_face_analyzer():
    from insightface.app import FaceAnalysis

    app = FaceAnalysis(
        name=os.getenv("FACE_PACK", "buffalo_sc"),
        root=os.getenv("INSIGHTFACE_HOME", "/models/insightface"),
        allowed_modules=["detection", "recognition"],
        providers=["CPUExecutionProvider"],        # explicit: avoid CUDA probing (issue #2344)
    )
    app.prepare(ctx_id=-1, det_size=(640, 640))    # ctx_id=-1 -> CPU
    return app


def extract_embedding(app, frame: np.ndarray, label: str) -> np.ndarray | None:
    """Return the L2-normalized embedding if the frame has exactly one face."""
    faces = app.get(frame)                         # expects BGR, as cv2 delivers
    if len(faces) != 1:
        print(f"[skip] {label}: expected exactly 1 face, found {len(faces)}")
        return None
    return np.asarray(faces[0].normed_embedding, dtype=np.float32)


def collect_from_dir(app, directory: Path) -> list[np.ndarray]:
    if not directory.is_dir():
        sys.exit(f"error: {directory} is not a directory")
    images = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    if not images:
        sys.exit(f"error: no .jpg/.png images found in {directory}")

    embeddings: list[np.ndarray] = []
    for path in images:
        frame = cv2.imread(str(path))              # BGR, as InsightFace expects
        if frame is None:
            print(f"[skip] {path.name}: unreadable image")
            continue
        emb = extract_embedding(app, frame, path.name)
        if emb is not None:
            embeddings.append(emb)
            print(f"[ok]   {path.name}")
    return embeddings


def collect_from_camera(app, n_frames: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        sys.exit(
            "error: cannot open /dev/video0 — V4L2 is single-consumer; "
            "stop the vision service first (docker compose stop vision)"
        )

    embeddings: list[np.ndarray] = []
    try:
        print("look at the camera; vary the pose slightly between shots", flush=True)
        for sec in range(COUNTDOWN_SECS, 0, -1):
            print(f"capturing in {sec}...", flush=True)
            time.sleep(1)

        for i in range(1, n_frames + 1):
            for _ in range(5):                     # drain stale buffered frames
                cap.grab()
            ok, frame = cap.read()
            if not ok:
                print(f"[skip] frame {i}/{n_frames}: camera read failed")
                continue
            emb = extract_embedding(app, frame, f"frame {i}/{n_frames}")
            if emb is not None:
                embeddings.append(emb)
                print(f"[ok]   frame {i}/{n_frames}")
            if i < n_frames:
                time.sleep(CAPTURE_INTERVAL_SECS)
    finally:
        cap.release()
    return embeddings


def min_pairwise_similarity(embeddings: list[np.ndarray]) -> float:
    """Minimum cosine similarity over all sample pairs (inputs are unit vectors)."""
    mat = np.stack(embeddings)
    sims = mat @ mat.T
    iu = np.triu_indices(len(embeddings), k=1)
    return float(sims[iu].min())


def build_template(embeddings: list[np.ndarray]) -> np.ndarray:
    mean = np.mean(np.stack(embeddings), axis=0)
    norm = float(np.linalg.norm(mean))
    if norm < 1e-9:
        sys.exit("error: degenerate mean embedding (zero norm); enrollment aborted")
    return (mean / norm).astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enroll a face template for presence.py")
    parser.add_argument("--name", required=True, help="identity name; saved as /faces/<name>.npy")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-dir", type=Path, metavar="DIR",
                        help="directory with .jpg/.png sample images")
    source.add_argument("--from-camera", type=int, metavar="N",
                        help="capture N frames from /dev/video0 (countdown on stdout)")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        sys.exit("error: --name must match [A-Za-z0-9_-]+ (it becomes a filename)")
    if args.from_camera is not None and args.from_camera < 1:
        sys.exit("error: --from-camera N must be >= 1")

    print("loading InsightFace (CPU)...", flush=True)
    app = load_face_analyzer()

    if args.from_dir is not None:
        embeddings = collect_from_dir(app, args.from_dir)
    else:
        embeddings = collect_from_camera(app, args.from_camera)

    if not embeddings:
        sys.exit("error: no valid samples (each image needs exactly 1 face); nothing saved")
    if len(embeddings) < RECOMMENDED_SAMPLES:
        print(f"[warn] only {len(embeddings)} valid samples; {RECOMMENDED_SAMPLES}+ recommended")

    if len(embeddings) >= 2:
        min_sim = min_pairwise_similarity(embeddings)
        print(f"min pairwise cosine similarity: {min_sim:.3f}")
        if min_sim < MIN_PAIR_SIMILARITY:
            print(f"[warn] below {MIN_PAIR_SIMILARITY}: inconsistent samples "
                  "(mixed persons or bad shots?) — consider re-enrolling")

    template = build_template(embeddings)
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FACES_DIR / f"{args.name}.npy"
    if out_path.exists():
        print(f"[warn] overwriting existing template {out_path}")
    np.save(out_path, template)
    print(f"saved {out_path} ({len(embeddings)} samples, dim {template.shape[0]})")
    print("restart the vision service to reload templates: docker compose restart vision")


if __name__ == "__main__":
    main()
