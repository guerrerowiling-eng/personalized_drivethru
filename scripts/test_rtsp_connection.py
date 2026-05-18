"""Prueba standalone de conectividad RTSP para cámara Hikvision."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
import cv2

FRAME_TARGET = 10
TEST_WINDOW_SEC = 3.0
FRAME_WAIT_SEC = 0.30
OUTPUT_FRAME_PATH = config.DATA_DIR / "test_rtsp_frame.jpg"


def main() -> int:
    url = config.build_hikvision_rtsp_url()
    print("=== Test RTSP Hikvision ===")
    print(f"URL: {url}")
    print(f"OPENCV_FFMPEG_CAPTURE_OPTIONS={config.os.environ.get('OPENCV_FFMPEG_CAPTURE_OPTIONS')}")

    cap = cv2.VideoCapture(url)
    if not cap or not cap.isOpened():
        print(
            "ERROR: No se pudo abrir el stream RTSP.\n"
            "Sugerencias:\n"
            "- Verifica IP, usuario y contraseña HIKVISION_*.\n"
            "- Verifica conectividad de red (ping a la cámara).\n"
            "- Confirma que el RTSP path y puerto estén correctos."
        )
        if cap is not None:
            cap.release()
        return 1

    start = time.monotonic()
    received = 0
    last_frame = None

    while received < FRAME_TARGET and (time.monotonic() - start) <= TEST_WINDOW_SEC:
        ok, frame = cap.read()
        now = datetime.now().isoformat(timespec="seconds")
        if not ok or frame is None:
            print(f"[{now}] frame={received + 1}: fallo de lectura")
            time.sleep(FRAME_WAIT_SEC)
            continue

        received += 1
        last_frame = frame
        print(f"[{now}] frame={received}: shape={frame.shape}")
        time.sleep(FRAME_WAIT_SEC)

    cap.release()

    if last_frame is not None:
        OUTPUT_FRAME_PATH.parent.mkdir(parents=True, exist_ok=True)
        if cv2.imwrite(str(OUTPUT_FRAME_PATH), last_frame):
            print(f"Frame final guardado en: {OUTPUT_FRAME_PATH}")
        else:
            print(f"Advertencia: no se pudo guardar frame en {OUTPUT_FRAME_PATH}")

    print("=== Resumen ===")
    print(f"Frames leídos correctamente: {received}/{FRAME_TARGET}")
    if received == 0:
        print(
            "FALLO: No se recibió ningún frame. Revisa red/cámara/credenciales.\n"
            "Tip: prueba conectividad con ping y confirma que el substream RTSP esté habilitado."
        )
        return 1
    if received < FRAME_TARGET:
        print("Parcial: hubo conexión, pero se recibieron menos de 10 frames en la ventana de prueba.")
        return 0
    print("Éxito: stream RTSP estable y lectura de frames completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
