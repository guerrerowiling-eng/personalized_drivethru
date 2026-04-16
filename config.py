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

# Modo de cámara por defecto (env): "simulated" | "real"
CAMERA_MODE = os.getenv("CAMERA_MODE", "simulated").strip().lower()
if CAMERA_MODE not in ("simulated", "real"):
    CAMERA_MODE = "simulated"

# Override en tiempo de ejecución (UI operador). None = usar CAMERA_MODE del entorno.
_runtime_camera_mode: str | None = None


def get_effective_camera_mode() -> str:
    """Modo activo: primero override de UI, si no el valor de entorno."""
    if _runtime_camera_mode in ("simulated", "real"):
        return _runtime_camera_mode
    return CAMERA_MODE if CAMERA_MODE in ("simulated", "real") else "simulated"


def set_runtime_camera_mode(mode: str) -> None:
    global _runtime_camera_mode
    m = (mode or "").strip().lower()
    if m not in ("simulated", "real"):
        raise ValueError("mode debe ser 'simulated' o 'real'")
    _runtime_camera_mode = m
