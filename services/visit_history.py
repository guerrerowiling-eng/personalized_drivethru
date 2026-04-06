"""Historial de visitas por placa (JSON)."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

HISTORY_PATH = config.VISIT_HISTORY_JSON


def _ensure_data_dir() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_all() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save_all(rows: list[dict]) -> None:
    _ensure_data_dir()
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def visits_for_plate(normalized_plate: str) -> list[dict]:
    """Visitas previas para una placa normalizada, orden cronológico."""
    if not normalized_plate:
        return []
    return [r for r in _load_all() if (r.get("placa_normalizada") or "") == normalized_plate]


def append_visit(
    *,
    placa_normalizada: str,
    placa_original: str,
    nombre: str,
    orden: str,
) -> dict:
    """Añade una visita y devuelve el registro guardado."""
    rows = _load_all()
    now = datetime.now(timezone.utc).astimezone()
    record = {
        "placa_normalizada": placa_normalizada,
        "placa_original": placa_original,
        "nombre": (nombre or "").strip(),
        "orden": (orden or "").strip(),
        "fecha_hora": now.isoformat(timespec="seconds"),
    }
    rows.append(record)
    _save_all(rows)
    return record


def prior_visit_count(normalized_plate: str) -> int:
    return len(visits_for_plate(normalized_plate))


def most_common_order(visits: list[dict]) -> str | None:
    if not visits:
        return None
    orders = [v.get("orden", "").strip() for v in visits if v.get("orden", "").strip()]
    if not orders:
        return None
    counts = Counter(orders)
    top = counts.most_common()
    if not top:
        return None
    max_count = top[0][1]
    tied = [o for o, c in top if c == max_count]
    # Desempate: el más reciente entre los empatados
    for v in reversed(visits):
        o = v.get("orden", "").strip()
        if o in tied:
            return o
    return tied[0]


def last_order(visits: list[dict]) -> str | None:
    if not visits:
        return None
    o = visits[-1].get("orden", "").strip()
    return o or None


def suggestion_from_history(visits: list[dict]) -> tuple[str | None, str | None]:
    """
    Devuelve (texto_sugerencia, orden_sugerido).

    El producto sugerido es el más pedido en el historial (empate → más reciente).
    El mensaje usa 1–2 / 3–8 / 9+ según cuántas veces aparece ese producto ganador,
    no según el total de visitas.
    """
    if not visits:
        return None, None

    usual = most_common_order(visits)
    if not usual:
        last = last_order(visits)
        if last:
            return f"Última vez pediste {last}", last
        return None, None

    w = sum(1 for v in visits if (v.get("orden") or "").strip() == usual)

    if w <= 2:
        return f"Última vez pediste {usual}", usual
    if w <= 8:
        return f"Sueles pedir {usual}", usual
    return f"Tu usual: {usual}", usual


def suggestion_for_prior_count(prior: int, visits: list[dict]) -> tuple[str | None, str | None]:
    """Compatibilidad: ignora prior; usa solo el historial."""
    if prior <= 0:
        return None, None
    return suggestion_from_history(visits)
