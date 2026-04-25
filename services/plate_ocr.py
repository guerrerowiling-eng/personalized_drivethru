"""
Servicio de lectura de placas por OCR.

- simulated: placas aleatorias / de clientes.csv
- real: captura con OpenCV (0) + EasyOCR, patrón Guatemala ^P[A-Z0-9]{6}$
  (ráfaga multi-frame, preprocesado CLAHE + bilateral, ROI por contornos).
"""
import csv
import random
import re
import string
import threading
import time
from collections import Counter
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

# Detección en modo real (límite total ~2 s incl. ráfaga)
_MIN_OCR_CONFIDENCE = 0.25
_BURST_FRAME_COUNT = 5
_BURST_DURATION_SEC = 0.8
_DETECTION_DEADLINE_SEC = 2.0
_OCR_MAX_FRAME_WIDTH = 720
_MAX_PLATE_ROIS = 5
_PLATE_ASPECT_MIN = 1.8
_PLATE_ASPECT_MAX = 4.0


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


def preprocess_frame(frame):
    """
    Mejora contraste y reduce ruido para OCR.
    Entrada/salida: BGR uint8 (3 canales) para compatibilidad con EasyOCR.
    """
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    filtered = cv2.bilateralFilter(enhanced, d=11, sigmaColor=17, sigmaSpace=17)
    return cv2.cvtColor(filtered, cv2.COLOR_GRAY2BGR)


def _resize_for_ocr(frame, max_width: int):
    import cv2

    if frame is None or frame.size == 0:
        return frame
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / float(w)
    nw = int(w * scale)
    nh = int(h * scale)
    return cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA)


def _safe_crop(frame, x: int, y: int, w: int, h: int):
    if frame is None or frame.size == 0:
        return None
    H, W = frame.shape[:2]
    x0 = max(0, int(x))
    y0 = max(0, int(y))
    x1 = min(W, int(x + w))
    y1 = min(H, int(y + h))
    if x1 <= x0 or y1 <= y0:
        return None
    crop = frame[y0:y1, x0:x1]
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return None
    return crop


def find_plate_region_rois(frame_bgr) -> list[tuple[int, int, int, int]]:
    """
    Rectángulos candidatos (x, y, w, h) vía Canny + contornos.
    Filtra relación de aspecto ancho/alto y área mínima.
    """
    import cv2

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    h_img, w_img = gray.shape[:2]
    min_area = max(2800, int(0.0018 * w_img * h_img))
    rois: list[tuple[int, int, int, int]] = []

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 30 or h < 12:
            continue
        aspect = w / float(h)
        if aspect < _PLATE_ASPECT_MIN or aspect > _PLATE_ASPECT_MAX:
            continue
        if w * h < min_area:
            continue
        rois.append((x, y, w, h))

    rois.sort(key=lambda r: r[2] * r[3], reverse=True)
    deduped: list[tuple[int, int, int, int]] = []
    for r in rois:
        if len(deduped) >= _MAX_PLATE_ROIS:
            break
        x, y, w, h = r
        cx, cy = x + w / 2.0, y + h / 2.0
        if any(
            abs(cx - (dx + dw / 2.0)) < (w + dw) * 0.35 and abs(cy - (dy + dh / 2.0)) < (h + dh) * 0.35
            for (dx, dy, dw, dh) in deduped
        ):
            continue
        deduped.append(r)
    return deduped


def _best_plate_and_confidence_from_readtext(
    results: list, min_confidence: float = _MIN_OCR_CONFIDENCE
) -> tuple[str | None, float]:
    """
    Mejor candidato Guatemala y su confianza (0 si no hay candidato).
    """
    candidates: list[tuple[str, float]] = []
    filtered: list = []
    for item in results:
        if len(item) < 3:
            continue
        if float(item[2]) < min_confidence:
            continue
        filtered.append(item)

    for item in filtered:
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
        combined = _normalize_plate_token("".join(item[1] for item in filtered if len(item) > 1))
        if _is_plate_shape(combined) and filtered:
            avg = sum(float(item[2]) for item in filtered if len(item) > 2) / len(filtered)
            if avg >= min_confidence:
                candidates.append((combined, avg))

    if not candidates:
        return None, 0.0

    candidates.sort(
        key=lambda x: (
            0 if x[0].startswith("P") else 1,
            -x[1],
            -len(x[0]),
        )
    )
    best = candidates[0]
    return best[0], best[1]


def _best_plate_from_readtext(results: list, min_confidence: float = _MIN_OCR_CONFIDENCE) -> str | None:
    """
    results: lista EasyOCR (bbox, text, confidence).
    Devuelve el mejor candidato que cumpla el patrón esperado de placa.
    Ignora detecciones con confianza estrictamente menor a min_confidence.
    """
    plate, _ = _best_plate_and_confidence_from_readtext(results, min_confidence)
    return plate


def _burst_capture_frames(
    n: int,
    burst_start: float,
    burst_end: float,
    hard_deadline: float,
) -> list:
    """Captura n frames repartidos entre burst_start y burst_end (sin superar hard_deadline)."""
    frames: list = []
    if n <= 0:
        return frames
    span = max(0.0, burst_end - burst_start)
    interval = span / (n - 1) if n > 1 else 0.0

    for i in range(n):
        if time.monotonic() >= hard_deadline:
            break
        slot_t = burst_start + i * interval
        while time.monotonic() < slot_t:
            if time.monotonic() >= hard_deadline:
                return frames
            time.sleep(0.002)

        f = read_frame_bgr()
        if f is not None:
            frames.append(f.copy())

    return frames


def _aggregate_frame_votes(votes_with_conf: list[tuple[str | None, float]]) -> str | None:
    """
    - Si alguna placa aparece 2+ veces, gana la de mayor frecuencia (empate → mayor suma de confianza).
    - Si ninguna llega a 2, se usa la detección individual con mayor confianza.
    """
    scored = [(p, c) for p, c in votes_with_conf if p]
    if not scored:
        return None
    counts = Counter(p for p, _ in scored)
    two_plus = [p for p, n in counts.items() if n >= 2]
    if two_plus:

        def rank(p: str) -> tuple[int, float]:
            return counts[p], sum(c for pp, c in scored if pp == p)

        return max(two_plus, key=rank)
    return max(scored, key=lambda x: x[1])[0]


def _detect_plate_single_frame(reader, frame_bgr, hard_deadline: float) -> tuple[str | None, float]:
    """Un frame: OCR en ROI + frame completo; devuelve (placa o None, mejor confianza del frame)."""
    if time.monotonic() >= hard_deadline:
        return None, 0.0

    work = _resize_for_ocr(frame_bgr, _OCR_MAX_FRAME_WIDTH)
    prep = preprocess_frame(work)
    merged: list = []

    for (x, y, w, h) in find_plate_region_rois(work):
        if time.monotonic() >= hard_deadline:
            break
        for src in (work, prep):
            crop = _safe_crop(src, x, y, w, h)
            if crop is None:
                continue
            try:
                merged.extend(reader.readtext(crop, detail=1, paragraph=False))
            except Exception:
                continue

    if time.monotonic() >= hard_deadline:
        return _best_plate_and_confidence_from_readtext(merged, _MIN_OCR_CONFIDENCE) if merged else (None, 0.0)

    for img in (work, prep):
        if time.monotonic() >= hard_deadline:
            break
        try:
            merged.extend(reader.readtext(img, detail=1, paragraph=False))
        except Exception:
            continue

    return (
        _best_plate_and_confidence_from_readtext(merged, _MIN_OCR_CONFIDENCE)
        if merged
        else (None, 0.0)
    )


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

    Modo real: ráfaga de 5 frames en ~0.8 s, OCR con preprocesado + ROI + voto
    por mayoría; tiempo total acotado (~2 s).

    Returns:
        str: Placa detectada o None si no se pudo leer.
    """
    if config.get_effective_camera_mode() == "simulated":
        return _simulate_plate_detection()

    t0 = time.monotonic()
    hard_deadline = t0 + _DETECTION_DEADLINE_SEC
    burst_start = t0
    burst_end = min(t0 + _BURST_DURATION_SEC, hard_deadline - 0.05)

    frames = _burst_capture_frames(
        _BURST_FRAME_COUNT,
        burst_start,
        burst_end,
        hard_deadline,
    )
    if not frames:
        return None

    try:
        reader = _get_easyocr_reader()
    except Exception:
        return None

    votes: list[tuple[str | None, float]] = []
    for fr in frames:
        if time.monotonic() >= hard_deadline:
            break
        try:
            votes.append(_detect_plate_single_frame(reader, fr, hard_deadline))
        except Exception:
            votes.append((None, 0.0))

    return _aggregate_frame_votes(votes)


def _simulate_plate_detection() -> str:
    plates = _get_sample_plates()
    if plates and random.random() < 0.7:
        return random.choice(plates)
    return _generate_random_plate()
