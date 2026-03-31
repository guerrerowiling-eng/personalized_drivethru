"""
Servicio de lectura de placas por OCR.

Actualmente usa simulación. Para conectar OCR real:
- Instalar biblioteca de visión (OpenCV, Tesseract, EasyOCR, etc.)
- Implementar read_plate_from_camera() con tu hardware
- Cambiar CAMERA_MODE a "real" en config
"""
import csv
import random
import string
from pathlib import Path
import warnings

# Rutas relativas para importar config
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def _generate_random_plate() -> str:
    """Genera una placa aleatoria estilo mexicano (3 letras + 3 números)."""
    letters = "".join(random.choices(string.ascii_uppercase, k=3))
    numbers = "".join(random.choices(string.digits, k=3))
    return f"{letters}{numbers}"


def _get_sample_plates() -> list[str]:
    """Obtiene placas de la base de datos para simulación realista."""
    plates = []
    if config.CUSTOMERS_CSV.exists():
        with open(config.CUSTOMERS_CSV, "r", encoding="utf-8", newline="") as f:
            # DictReader maneja comas en el resto de columnas.
            reader = csv.DictReader(f)
            for row in reader:
                plate = (row.get("placa") or "").strip()
                if plate:
                    plates.append(plate)
    return plates


def read_plate_from_camera() -> str | None:
    """
    Lee la placa desde la cámara del drive-thru.
    
    SIMULADO: Retorna una placa aleatoria (70% de clientes conocidos, 30% nuevos).
    REAL: Conecta con tu módulo OCR y retorna la placa detectada.
    
    Returns:
        str: Placa detectada o None si no se pudo leer.
    """
    if config.CAMERA_MODE == "simulated":
        return _simulate_plate_detection()
    
    # --- AQUÍ CONECTAR TU OCR REAL ---
    # Ejemplo con OpenCV + Tesseract:
    # import cv2
    # cap = cv2.VideoCapture(0)
    # ret, frame = cap.read()
    # plate = your_ocr_function(frame)
    # cap.release()
    # return plate
    warnings.warn("CAMERA_MODE='real' pero OCR no implementado aun; usando simulacion.")
    return _simulate_plate_detection()


def _simulate_plate_detection() -> str:
    """Simula detección: 70% placa conocida, 30% placa nueva."""
    plates = _get_sample_plates()
    if plates and random.random() < 0.7:
        return random.choice(plates)
    return _generate_random_plate()
