"""Configuración del sistema drive-thru."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CUSTOMERS_CSV = DATA_DIR / "clientes.csv"
VISIT_HISTORY_JSON = DATA_DIR / "historial_visitas.json"

# Simulación de cámara: intervalo en segundos (solo si AUTO_SIMULATE_ARRIVALS=True)
CAMERA_SIMULATION_INTERVAL = 12

# Si True, un hilo cambia la placa sola cada CAMERA_SIMULATION_INTERVAL.
# False = solo "Simular llegada", placa manual u OCR real.
AUTO_SIMULATE_ARRIVALS = os.getenv("AUTO_SIMULATE_ARRIVALS", "").lower() in ("1", "true", "yes")

# Modo de cámara: "simulated" | "real" (para cuando conectes OCR real)
CAMERA_MODE = os.getenv("CAMERA_MODE", "simulated")
