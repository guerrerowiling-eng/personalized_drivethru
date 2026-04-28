"""Servicio de base de datos de clientes (CSV)."""
import csv
import re
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

FIELDNAMES = ("placa", "nickname", "orden_favorita", "visitas", "fecha_registro", "ultima_visita")


def _normalize_plate(plate: str) -> str:
    """Normaliza la placa para búsqueda (mayúsculas, alfanumerico)."""
    if not plate:
        return ""
    # OCR y entradas manuales pueden traer espacios/guiones; filtramos caracteres no alfanumericos.
    return re.sub(r"[^A-Z0-9]", "", plate.strip().upper())


def normalize_plate(plate: str) -> str:
    """Placa normalizada para historial y búsquedas."""
    return _normalize_plate(plate)


def _now_iso_local() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_customer_by_plate(plate: str) -> dict | None:
    """
    Busca un cliente por su placa.
    
    Returns:
        dict con keys: nickname, orden_favorita, visitas, fecha_registro, ultima_visita
        (y alias nombre para compatibilidad)
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
                    "nickname": (row.get("nickname") or row.get("nombre") or "").strip(),
                    "nombre": (row.get("nickname") or row.get("nombre") or "").strip(),
                    "orden_favorita": row.get("orden_favorita", ""),
                    "visitas": int(row.get("visitas", 0)),
                    "fecha_registro": (row.get("fecha_registro") or "").strip(),
                    "ultima_visita": (row.get("ultima_visita") or "").strip(),
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
                "nickname": row.get("nickname", "") or row.get("nombre", ""),
                "orden_favorita": row.get("orden_favorita", ""),
                "visitas": str(int(row.get("visitas", 0) or 0)),
                "fecha_registro": row.get("fecha_registro", ""),
                "ultima_visita": row.get("ultima_visita", ""),
            })


def upsert_customer(
    plate: str,
    nickname: str,
    orden_favorita: str,
    visitas: int | None = None,
    fecha_registro: str | None = None,
    ultima_visita: str | None = None,
) -> dict:
    """
    Crea o actualiza cliente por placa.
    Si visitas es None, conserva el valor existente o usa 0.
    """
    normalized = _normalize_plate(plate)
    if not normalized:
        raise ValueError("placa vacía")
    now_iso = _now_iso_local()

    rows = _read_all_rows()
    found = False
    for i, row in enumerate(rows):
        if _normalize_plate(row.get("placa", "")) == normalized:
            v = visitas if visitas is not None else int(row.get("visitas", 0) or 0)
            existing_reg = (row.get("fecha_registro") or "").strip()
            rows[i] = {
                "placa": plate.strip().upper(),
                "nickname": nickname.strip(),
                "orden_favorita": orden_favorita.strip(),
                "visitas": v,
                "fecha_registro": fecha_registro or existing_reg or now_iso,
                "ultima_visita": ultima_visita or now_iso,
            }
            found = True
            break
    if not found:
        v = visitas if visitas is not None else 0
        rows.append({
            "placa": plate.strip().upper(),
            "nickname": nickname.strip(),
            "orden_favorita": orden_favorita.strip(),
            "visitas": v,
            "fecha_registro": fecha_registro or now_iso,
            "ultima_visita": ultima_visita or now_iso,
        })
    _write_all_rows(rows)
    cust = get_customer_by_plate(plate)
    if cust:
        return cust
    return {
        "nickname": nickname.strip(),
        "nombre": nickname.strip(),
        "orden_favorita": orden_favorita.strip(),
        "visitas": visitas or 0,
        "fecha_registro": fecha_registro or now_iso,
        "ultima_visita": ultima_visita or now_iso,
    }


def update_customer_nickname(plate: str, nickname: str) -> dict | None:
    """Actualiza solo el nickname para una placa existente."""
    normalized = _normalize_plate(plate)
    nick = (nickname or "").strip()
    if not normalized or not nick:
        return None

    rows = _read_all_rows()
    changed = False
    for i, row in enumerate(rows):
        if _normalize_plate(row.get("placa", "")) != normalized:
            continue
        rows[i] = {
            "placa": row.get("placa", "").strip().upper(),
            "nickname": nick,
            "orden_favorita": row.get("orden_favorita", "").strip(),
            "visitas": int(row.get("visitas", 0) or 0),
            "fecha_registro": (row.get("fecha_registro") or "").strip(),
            "ultima_visita": (row.get("ultima_visita") or "").strip() or _now_iso_local(),
        }
        changed = True
        break

    if not changed:
        return None
    _write_all_rows(rows)
    return get_customer_by_plate(plate)
