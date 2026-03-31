"""Configuración del sistema drive-thru."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CUSTOMERS_CSV = DATA_DIR / "clientes.csv"

# Simulación de cámara: intervalo en segundos entre "detecciones"
CAMERA_SIMULATION_INTERVAL = 12

# Modo de cámara: "simulated" | "real" (para cuando conectes OCR real)
CAMERA_MODE = os.getenv("CAMERA_MODE", "simulated")
