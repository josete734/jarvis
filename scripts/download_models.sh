#!/usr/bin/env bash
# Downloads/produces all local models into /var/lib/jarvis/models (NVMe).
# Requires images built first: make build. Run from the repo root.
set -euo pipefail

MODELS=/var/lib/jarvis/models
mkdir -p "$MODELS"/{piper,openwakeword,hf,insightface}

echo "==> Piper voice es_ES-davefx-medium (HF rhasspy/piper-voices, verified jun-2026)"
BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium"
for f in es_ES-davefx-medium.onnx es_ES-davefx-medium.onnx.json; do
    [ -f "$MODELS/piper/$f" ] || curl -fL "$BASE/$f" -o "$MODELS/piper/$f"
done

echo "==> openWakeWord hey_jarvis (+ shared melspectrogram/embedding models)"
docker compose run --rm --no-deps orchestrator python - <<'EOF'
import openwakeword.utils as u
u.download_models(model_names=["hey_jarvis_v0.1"], target_directory="/models/openwakeword")
EOF

echo "==> faster-whisper small INT8 (pre-pull into HF cache on NVMe)"
docker compose run --rm --no-deps orchestrator python - <<'EOF'
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8")
print("whisper small ready")
EOF

echo "==> Embeddings multilingual-e5-small (pre-pull)"
docker compose run --rm --no-deps orchestrator python - <<'EOF'
from huggingface_hub import snapshot_download
snapshot_download("intfloat/multilingual-e5-small")
print("e5-small ready")
EOF

echo "==> YOLO11n -> OpenVINO INT8 @320 (one-off export via ultralytics image)"
if [ ! -d "$MODELS/yolo11n_int8_320_openvino" ]; then
    docker run --rm -v "$MODELS":/work -w /work ultralytics/ultralytics:latest \
        yolo export model=yolo11n.pt format=openvino int8=True imgsz=320
    mv "$MODELS"/yolo11n_int8_openvino_model "$MODELS"/yolo11n_int8_320_openvino 2>/dev/null || \
        echo "NOTE: check the export output dir name and move it to yolo11n_int8_320_openvino"
fi

echo "==> InsightFace buffalo_sc (auto-download into /models/insightface)"
docker compose run --rm --no-deps vision python3 - <<'EOF'
from insightface.app import FaceAnalysis
app = FaceAnalysis(name="buffalo_sc", root="/models/insightface",
                   allowed_modules=["detection", "recognition"])
app.prepare(ctx_id=-1)
print("buffalo_sc ready")
EOF

echo "All models in $MODELS:"
du -sh "$MODELS"/* 2>/dev/null || true
