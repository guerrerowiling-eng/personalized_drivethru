"""Servicio de base de datos de clientes (CSV)."""
import csv
import re
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def _normalize_plate(plate: str) -> str:
    """Normaliza la placa para búsqueda (mayúsculas, alfanumerico)."""
    if not plate:
        return ""
    # OCR y entradas manuales pueden traer espacios/guiones; filtramos caracteres no alfanumericos.
    return re.sub(r"[^A-Z0-9]", "", plate.strip().upper())


def get_customer_by_plate(plate: str) -> dict | None:
    """
    Busca un cliente por su placa.
    
    Returns:
        dict con keys: nombre, orden_favorita, visitas
        None si no existe
    """
    if not plate:
        return None
    
    normalized = _normalize_plate(plate)
    if not config.CUSTOMERS_CSV.exists():
        return None
    
    with open(config.CUSTOMERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if _normalize_plate(row.get("placa", "")) == normalized:
                return {
                    "nombre": row.get("nombre", ""),
                    "orden_favorita": row.get("orden_favorita", ""),
                    "visitas": int(row.get("visitas", 0)),
                }
    return None
