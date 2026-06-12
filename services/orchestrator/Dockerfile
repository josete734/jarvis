# 3.11 (no 3.12): openwakeword 0.6.0 declara tflite-runtime obligatorio en Linux
# y ese paquete no publica wheel para cp312 (último 2.14.0 = cp311). El gate corre
# por ONNX (WAKE_FRAMEWORK=onnx), así que tflite queda instalado pero sin uso.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential portaudio19-dev libasound2-dev alsa-utils curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Hornea los modelos compartidos de openWakeWord (melspectrogram/embedding/silero_vad
# + hey_jarvis) DENTRO del paquete: en runtime Model() y VAD() los buscan en
# site-packages/openwakeword/resources/models, no en /models — sin esto el gate
# crashea al arrancar (verificado contra el wheel 0.6.0).
RUN python -c "from openwakeword.utils import download_models; download_models(model_names=['hey_jarvis_v0.1'])"

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
