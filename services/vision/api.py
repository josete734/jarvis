"""Vision HTTP API (internal network only — no published ports).

GET /frame   -> latest JPEG (consumed by the orchestrator's ver_camara tool)
GET /health
"""

import os
import threading
import time

import cv2
import uvicorn
from fastapi import FastAPI, Response

import presence

app = FastAPI(title="jarvis-vision")


@app.get("/health")
def health():
    return {"ok": True, "presence": os.getenv("DISABLE_PRESENCE", "true") != "true"}


@app.get("/frame")
def frame():
    jpeg = presence.get_latest_jpeg()
    if jpeg is None:
        jpeg = _grab_once()
    if jpeg is None:
        return Response(status_code=503)
    return Response(content=jpeg, media_type="image/jpeg")


def _grab_once() -> bytes | None:
    """Fallback when the presence loop is disabled (pre-Fase 5): open, grab, release."""
    cap = cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            return None
        time.sleep(0.2)                    # let exposure settle
        ok, img = cap.read()
        if not ok:
            return None
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpg.tobytes() if ok else None
    finally:
        cap.release()


if __name__ == "__main__":
    if os.getenv("DISABLE_PRESENCE", "true") != "true":
        presence.start_in_thread()
    uvicorn.run(app, host="0.0.0.0", port=8089)
