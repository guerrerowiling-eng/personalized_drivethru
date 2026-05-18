"""Configuración del sistema drive-thru."""
import logging
import os
from pathlib import Path
from urllib.parse import quote

# Debe definirse antes de cualquier import de cv2 en el proyecto.
# Para RTSP en LAN priorizamos UDP para minimizar latencia/buffering.
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CUSTOMERS_CSV = DATA_DIR / "clientes.csv"
VISIT_HISTORY_JSON = DATA_DIR / "historial_visitas.json"

# Umbral para sugerencia probabilística (Phase 2, 60%)
SUGGESTION_THRESHOLD = 0.60

# Simulación de cámara: intervalo en segundos (solo si AUTO_SIMULATE_ARRIVALS=True)
CAMERA_SIMULATION_INTERVAL = 12

# Si True, un hilo cambia la placa sola cada CAMERA_SIMULATION_INTERVAL.
# False = solo "Simular llegada", placa manual u OCR real.
AUTO_SIMULATE_ARRIVALS = os.getenv("AUTO_SIMULATE_ARRIVALS", "").lower() in ("1", "true", "yes")

# Modo de cámara por defecto (env): "simulated" | "real" | "hikvision_rtsp"
SUPPORTED_CAMERA_MODES = ("simulated", "real", "hikvision_rtsp")
CAMERA_MODE = os.getenv("CAMERA_MODE", "simulated").strip().lower()
if CAMERA_MODE not in SUPPORTED_CAMERA_MODES:
    CAMERA_MODE = "simulated"

HIKVISION_IP = os.getenv("HIKVISION_IP", "192.168.0.64").strip()
HIKVISION_USER = os.getenv("HIKVISION_USER", "admin").strip()
HIKVISION_PASSWORD = os.getenv("HIKVISION_PASSWORD", "")
HIKVISION_RTSP_PORT = int(os.getenv("HIKVISION_RTSP_PORT", "554"))
HIKVISION_RTSP_PATH = os.getenv("HIKVISION_RTSP_PATH", "/Streaming/Channels/102").strip()

# Override en tiempo de ejecución (UI operador). None = usar CAMERA_MODE del entorno.
_runtime_camera_mode: str | None = None


def get_effective_camera_mode() -> str:
    """Modo activo: primero override de UI, si no el valor de entorno."""
    if _runtime_camera_mode in SUPPORTED_CAMERA_MODES:
        return _runtime_camera_mode
    return CAMERA_MODE if CAMERA_MODE in SUPPORTED_CAMERA_MODES else "simulated"


def set_runtime_camera_mode(mode: str) -> None:
    global _runtime_camera_mode
    m = (mode or "").strip().lower()
    if m not in SUPPORTED_CAMERA_MODES:
        raise ValueError("mode debe ser 'simulated', 'real' o 'hikvision_rtsp'")
    _runtime_camera_mode = m


def build_hikvision_rtsp_url() -> str:
    """Construye la URL RTSP para cámara Hikvision desde variables de entorno."""
    path = HIKVISION_RTSP_PATH if HIKVISION_RTSP_PATH.startswith("/") else f"/{HIKVISION_RTSP_PATH}"
    user = quote(HIKVISION_USER, safe="")
    password = quote(HIKVISION_PASSWORD, safe="")
    return f"rtsp://{user}:{password}@{HIKVISION_IP}:{HIKVISION_RTSP_PORT}{path}"


def warn_if_hikvision_password_missing() -> None:
    """Registra advertencia clara si falta contraseña en modo hikvision_rtsp."""
    if get_effective_camera_mode() == "hikvision_rtsp" and not HIKVISION_PASSWORD:
        logging.warning(
            "CAMERA_MODE=hikvision_rtsp pero HIKVISION_PASSWORD está vacío. "
            "Configura la contraseña para evitar fallos de autenticación RTSP."
        )
