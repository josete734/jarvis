# Vision service — PLAN_FINAL §3.2
# CRITICAL: the OpenCL driver for the UHD 630 (Gen9.5) must be the legacy
# branch. Ubuntu 24.04's repo intel-opencl-icd still supports Gen9 — do NOT
# add Intel's GitHub compute-runtime repo (new NEO releases dropped Gen9).
FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip \
        intel-opencl-icd ocl-icd-libopencl1 clinfo \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
# Sanity check on start: `clinfo | grep -i 'device name'` should list the iGPU.
CMD ["python3", "api.py"]
