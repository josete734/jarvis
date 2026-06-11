#!/usr/bin/env bash
# AEC test — Fase 0 gate (PLAN_FINAL §5.1).
# Usage: bash scripts/test_aec.sh plughw:1,0      (find X with: arecord -l)
# Mic and speaker MUST be the same USB device for hardware AEC.
# Requires on the host: alsa-utils, sox, espeak-ng (install_host.sh).
set -euo pipefail

DEV="${1:?Usage: test_aec.sh <alsa-device, e.g. plughw:1,0>}"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

rms() { sox "$1" -n stats 2>&1 | awk '/RMS lev dB/{print $4}'; }

echo "==> 1/3 Baseline: 5 s of room silence (stay quiet)..."
arecord -D "$DEV" -f S16_LE -r 16000 -c 1 -d 5 "$TMP/silence.wav" >/dev/null 2>&1
BASE=$(rms "$TMP/silence.wav")
echo "    baseline RMS: $BASE dB"

echo "==> 2/3 Echo test: playing speech through $DEV while recording it..."
espeak-ng -v es -s 150 \
  -w "$TMP/speech.wav" \
  "Esto es una prueba de cancelación de eco. Si me oyes en la grabación, el dispositivo no cancela su propia voz. Repito: esto es una prueba de cancelación de eco acústico para Jarvis."
aplay -D "$DEV" "$TMP/speech.wav" >/dev/null 2>&1 &
PLAY=$!
sleep 2   # convergence time for the canceller
arecord -D "$DEV" -f S16_LE -r 16000 -c 1 -d 8 "$TMP/echo.wav" >/dev/null 2>&1
wait $PLAY 2>/dev/null || true
ECHO=$(rms "$TMP/echo.wav")
echo "    echo-test RMS: $ECHO dB"

DELTA=$(awk -v a="$ECHO" -v b="$BASE" 'BEGIN{printf "%.1f", a-b}')
echo
echo "==> RESULT: delta = $DELTA dB over baseline"
awk -v d="$DELTA" 'BEGIN{
  if (d <= 6)       print "    ✅ AEC real: el dispositivo apenas se oye a sí mismo.";
  else if (d <= 15) print "    ⚠️  Dudoso: escucha echo.wav; puede bastar con barge-in degradado.";
  else              print "    ❌ Sin AEC utilizable: aplica el plan B/C (PLAN_FINAL §5.2).";
}'
cp "$TMP/echo.wav" ./aec_echo_sample.wav
echo "    Sample saved to ./aec_echo_sample.wav — listen to it."
echo
echo "==> 3/3 Double-talk (manual): re-run step 2 while speaking over the playback;"
echo "    your voice must come out clean. Then run the full pipeline test (Fase 1)."
