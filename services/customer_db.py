"""Servicio de base de datos de clientes (CSV)."""
import csv
import re
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

FIELDNAMES = ("placa", "nombre", "orden_favorita", "visitas")


def _normalize_plate(plate: str) -> str:
    """Normaliza la placa para búsqueda (mayúsculas, alfanumerico)."""
    if not plate:
        return ""
    # OCR y entradas manuales pueden traer espacios/guiones; filtramos caracteres no alfanumericos.
    return re.sub(r"[^A-Z0-9]", "", plate.strip().upper())


def normalize_plate(plate: str) -> str:
    """Placa normalizada para historial y búsquedas."""
    return _normalize_plate(plate)


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


def _read_all_rows() -> list[dict]:
    if not config.CUSTOMERS_CSV.exists():
        return []
    with open(config.CUSTOMERS_CSV, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_all_rows(rows: list[dict]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.CUSTOMERS_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for row in rows:
            w.writerow({
                "placa": row.get("placa", ""),
                "nombre": row.get("nombre", ""),
                "orden_favorita": row.get("orden_favorita", ""),
                "visitas": str(int(row.get("visitas", 0) or 0)),
            })


def upsert_customer(plate: str, nombre: str, orden_favorita: str, visitas: int | None = None) -> dict:
    """
    Crea o actualiza cliente por placa.
    Si visitas es None, conserva el valor existente o usa 0.
    """
    normalized = _normalize_plate(plate)
    if not normalized:
        raise ValueError("placa vacía")

    rows = _read_all_rows()
    found = False
    for i, row in enumerate(rows):
        if _normalize_plate(row.get("placa", "")) == normalized:
            v = visitas if visitas is not None else int(row.get("visitas", 0) or 0)
            rows[i] = {
                "placa": plate.strip().upper(),
                "nombre": nombre.strip(),
                "orden_favorita": orden_favorita.strip(),
                "visitas": v,
            }
            found = True
            break
    if not found:
        v = visitas if visitas is not None else 0
        rows.append({
            "placa": plate.strip().upper(),
            "nombre": nombre.strip(),
            "orden_favorita": orden_favorita.strip(),
            "visitas": v,
        })
    _write_all_rows(rows)
    cust = get_customer_by_plate(plate)
    if cust:
        return cust
    return {
        "nombre": nombre.strip(),
        "orden_favorita": orden_favorita.strip(),
        "visitas": visitas or 0,
    }
