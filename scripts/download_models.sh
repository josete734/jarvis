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
# El export INT8 calibra con coco8 (se descarga solo) y produce la carpeta yolo11n_openvino_model/.
if [ ! -d "$MODELS/yolo11n_int8_320_openvino" ]; then
    docker run --rm -v "$MODELS":/work -w /work ultralytics/ultralytics:latest \
        yolo export model=yolo11n.pt format=openvino int8=True imgsz=320
    mv "$MODELS"/yolo11n_openvino_model "$MODELS"/yolo11n_int8_320_openvino 2>/dev/null || \
        echo "NOTE: revisa el nombre real de la carpeta exportada y muévela a yolo11n_int8_320_openvino"
fi

echo "==> InsightFace buffalo_sc (Fase 5; este pack NO se auto-descarga como buffalo_l)"
docker compose run --rm --no-deps vision python3 - <<'EOF'
# buffalo_sc NO está en la lista de auto-download de insightface (sí buffalo_l/antelopev2).
# Si no baja solo, descarga el pack y descomprime en /models/insightface/models/buffalo_sc/
# (debe contener det_500m.onnx + w600k_mbf.onnx). Espejo: SourceForge insightface.mirror v0.7.
from insightface.app import FaceAnalysis
try:
    app = FaceAnalysis(name="buffalo_sc", root="/models/insightface",
                       allowed_modules=["detection", "recognition"],
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1)
    print("buffalo_sc OK")
except Exception as e:
    print(f"NOTE: buffalo_sc no disponible automáticamente ({e}).")
    print("Descárgalo manual a /models/insightface/models/buffalo_sc/ (Fase 5).")
EOF

echo "All models in $MODELS:"
du -sh "$MODELS"/* 2>/dev/null || true
