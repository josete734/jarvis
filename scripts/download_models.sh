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

echo "==> Piper voice es_ES-carlfm-high (voz por defecto; comunidad, no en el repo oficial)"
CARLFM="https://huggingface.co/friyin/vits-piper-es_ES-carlfm-high/resolve/main"
for f in es_ES-carlfm-high.onnx es_ES-carlfm-high.onnx.json; do
    [ -f "$MODELS/piper/$f" ] || curl -fL "$CARLFM/$f" -o "$MODELS/piper/$f"
done

echo "==> openWakeWord hey_jarvis (+ shared melspectrogram/embedding models)"
docker compose run --rm --no-deps -T orchestrator python - <<'EOF'
import openwakeword.utils as u
u.download_models(model_names=["hey_jarvis_v0.1"], target_directory="/models/openwakeword")
EOF

echo "==> faster-whisper small INT8 (pre-pull into HF cache on NVMe)"
docker compose run --rm --no-deps -T orchestrator python - <<'EOF'
from faster_whisper import WhisperModel
WhisperModel("small", device="cpu", compute_type="int8")
print("whisper small ready")
EOF

echo "==> Embeddings multilingual-e5-small (pre-pull)"
docker compose run --rm --no-deps -T orchestrator python - <<'EOF'
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

echo "==> InsightFace buffalo_sc (det_500m + w600k_mbf; release v0.7, URL verificada jun-2026)"
# Descarga directa en el host (idempotente por los .onnx, no por la carpeta). Requiere unzip (install_host.sh).
BUFFALO_DIR="$MODELS/insightface/models/buffalo_sc"
BUFFALO_URL="https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_sc.zip"
BUFFALO_MIRROR="https://downloads.sourceforge.net/project/insightface.mirror/v0.7/buffalo_sc.zip"
BUFFALO_SHA256="57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72"
if [ -s "$BUFFALO_DIR/det_500m.onnx" ] && [ -s "$BUFFALO_DIR/w600k_mbf.onnx" ]; then
    echo "buffalo_sc ya presente en $BUFFALO_DIR, skip"
else
    tmpzip=$(mktemp /tmp/buffalo_sc.XXXXXX.zip)
    trap 'rm -f "$tmpzip"' EXIT
    curl -fL --retry 3 --connect-timeout 15 -o "$tmpzip" "$BUFFALO_URL" \
        || curl -fL --retry 3 --connect-timeout 15 -o "$tmpzip" "$BUFFALO_MIRROR"
    echo "$BUFFALO_SHA256  $tmpzip" | sha256sum -c -
    mkdir -p "$BUFFALO_DIR"
    unzip -o "$tmpzip" -d "$BUFFALO_DIR"
    rm -f "$tmpzip"; trap - EXIT
    for f in det_500m.onnx w600k_mbf.onnx; do
        [ -s "$BUFFALO_DIR/$f" ] || { echo "ERROR: falta $f en $BUFFALO_DIR" >&2; exit 1; }
    done
    echo "buffalo_sc OK en $BUFFALO_DIR"
fi

echo "All models in $MODELS:"
du -sh "$MODELS"/* 2>/dev/null || true
