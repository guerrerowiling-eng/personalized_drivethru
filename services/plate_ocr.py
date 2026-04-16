"""
Servicio de lectura de placas por OCR.

- simulated: placas aleatorias / de clientes.csv
- real: captura con OpenCV (0) + EasyOCR, candidatos 5–7 caracteres alfanuméricos
"""
import csv
import random
import re
import string
import threading
import time
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

_cap: object | None = None
_cap_lock = threading.Lock()
_reader = None
_reader_lock = threading.Lock()
_preview_jpeg_cache: bytes | None = None
_preview_cache_lock = threading.Lock()
_preview_thread: threading.Thread | None = None
_preview_thread_lock = threading.Lock()

# Placa Guatemala (tras normalizar):
# - exactamente 7 caracteres alfanuméricos
# - comienza con P
_PLATE_RE = re.compile(r"^P[A-Z0-9]{6}$")
_PREVIEW_MAX_WIDTH = 480
_PREVIEW_JPEG_QUALITY = 64
_PREVIEW_LOOP_INTERVAL_SEC = 0.06


def _generate_random_plate() -> str:
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=3))
    return f"{letters}{numbers}"


def _get_sample_plates() -> list[str]:
    plates = []
    if config.CUSTOMERS_CSV.exists():
        with open(config.CUSTOMERS_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                plate = (row.get("placa") or "").strip()
                if plate:
                    plates.append(plate)
    return plates


def release_camera() -> None:
    """Libera la cámara (p. ej. al volver a modo simulado)."""
    global _cap, _preview_jpeg_cache
    with _cap_lock:
        if _cap is not None:
            try:
                _cap.release()
            except Exception:
                pass
            _cap = None
    with _preview_cache_lock:
        _preview_jpeg_cache = None


def _preview_capture_loop() -> None:
    """Captura frames en segundo plano para vista previa fluida."""
    global _preview_jpeg_cache
    while True:
        if config.get_effective_camera_mode() != "real":
            with _preview_cache_lock:
                _preview_jpeg_cache = None
            time.sleep(0.18)
            continue

        frame = read_frame_bgr()
        if frame is None:
            time.sleep(0.05)
            continue

        data = frame_to_jpeg_bytes(
            frame,
            max_width=_PREVIEW_MAX_WIDTH,
            quality=_PREVIEW_JPEG_QUALITY,
        )
        if data:
            with _preview_cache_lock:
                _preview_jpeg_cache = data

        time.sleep(_PREVIEW_LOOP_INTERVAL_SEC)


def start_preview_capture_loop() -> None:
    """Arranca el hilo de preview si aún no existe."""
    global _preview_thread
    with _preview_thread_lock:
        if _preview_thread is not None and _preview_thread.is_alive():
            return
        _preview_thread = threading.Thread(target=_preview_capture_loop, daemon=True)
        _preview_thread.start()


def _get_easyocr_reader():
    global _reader
    import easyocr

    with _reader_lock:
        if _reader is None:
            _reader = easyocr.Reader(["en", "es"], gpu=False, verbose=False)
        return _reader


def _normalize_plate_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (text or "")).upper()


def _is_plate_shape(token: str) -> bool:
    if not token:
        return False
    return bool(_PLATE_RE.fullmatch(token))


def _best_plate_from_readtext(results: list) -> str | None:
    """
    results: lista EasyOCR (bbox, text, confidence).
    Devuelve el mejor candidato que cumpla el patrón esperado de placa.
    """
    candidates: list[tuple[str, float]] = []

    for item in results:
        if len(item) < 3:
            continue
        text, conf = item[1], float(item[2])
        raw = text or ""
        cleaned = _normalize_plate_token(raw)
        if _is_plate_shape(cleaned):
            candidates.append((cleaned, conf))
        for m in re.finditer(r"[A-Za-z0-9]{7}", raw):
            tok = _normalize_plate_token(m.group())
            if _is_plate_shape(tok):
                candidates.append((tok, conf))

    if not candidates:
        combined = _normalize_plate_token("".join(item[1] for item in results if len(item) > 1))
        if _is_plate_shape(combined):
            avg = sum(float(item[2]) for item in results if len(item) > 2) / max(len(results), 1)
            candidates.append((combined, avg))

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            0 if x[0].startswith("P") else 1,
            -x[1],
            -len(x[0]),
        )
    )
    return candidates[0][0]


def read_frame_bgr():
    """Lee un frame BGR o None."""
    if config.get_effective_camera_mode() != "real":
        return None
    import cv2

    global _cap
    with _cap_lock:
        if _cap is None or not _cap.isOpened():
            _cap = cv2.VideoCapture(0)
        ok, frame = _cap.read()
        if not ok or frame is None:
            return None
        return frame


def frame_to_jpeg_bytes(frame, max_width: int = 640, quality: int = 82) -> bytes | None:
    if frame is None:
        return None
    import cv2

    h, w = frame.shape[:2]
    if w > max_width and w > 0:
        scale = max_width / float(w)
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return None
    return buf.tobytes()


def get_cached_preview_jpeg() -> tuple[bool, bytes | None, str | None]:
    """
    JPEG de preview desde caché en memoria.
    Returns: (ok, jpeg_bytes_or_none, error_message_or_none)
    """
    if config.get_effective_camera_mode() != "real":
        return False, None, "Modo simulado — sin vista previa de cámara"

    with _preview_cache_lock:
        data = _preview_jpeg_cache
    if not data:
        return False, None, "Aún no hay frame de preview disponible"
    return True, data, None


def read_plate_from_camera() -> str | None:
    """
    Lee la placa desde la cámara (real) o simulación.

    Returns:
        str: Placa detectada o None si no se pudo leer.
    """
    if config.get_effective_camera_mode() == "simulated":
        return _simulate_plate_detection()

    frame = read_frame_bgr()
    if frame is None:
        return None

    try:
        reader = _get_easyocr_reader()
        results = reader.readtext(frame, detail=1, paragraph=False)
    except Exception:
        return None

    if not results:
        return None

    plate = _best_plate_from_readtext(results)
    return plate


def _simulate_plate_detection() -> str:
    plates = _get_sample_plates()
    if plates and random.random() < 0.7:
        return random.choice(plates)
    return _generate_random_plate()
