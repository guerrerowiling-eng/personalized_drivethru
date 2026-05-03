"""Historial de visitas por placa (JSON)."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def order_as_list(orden_raw: Any) -> list[dict]:
    """
    Normaliza el campo 'orden' de una visita a lista de {item, quantity}.
    Acepta lista nueva o string legacy (un solo ítem).
    """
    if orden_raw is None:
        return []
    if isinstance(orden_raw, str):
        s = orden_raw.strip()
        if not s:
            return []
        return [{"item": s, "quantity": 1}]
    if not isinstance(orden_raw, list):
        return []
    out: list[dict] = []
    for row in orden_raw:
        if not isinstance(row, dict):
            continue
        item = (row.get("item") or "").strip()
        if not item:
            continue
        try:
            q = int(row.get("quantity", 1))
        except (TypeError, ValueError):
            continue
        if q < 1:
            continue
        out.append({"item": item, "quantity": q})
    return out


def format_order_summary(order_array: list[dict]) -> str:
    """
    Ordena alfabéticamente por nombre de ítem.
    Devuelve: "2x Cappuccino (16oz), 1x Croissant jamón y queso"
    """
    if not order_array:
        return ""
    lines = sorted(
        [{"item": (r.get("item") or "").strip(), "quantity": int(r.get("quantity", 1))} for r in order_array],
        key=lambda x: x["item"].lower(),
    )
    parts = [f"{r['quantity']}x {r['item']}" for r in lines if r["item"]]
    return ", ".join(parts)


def canonical_order_key(order_array: list[dict]) -> str:
    """Clave canónica para comparar dos pedidos (mismo contenido y cantidades)."""
    if not order_array:
        return ""
    lines = sorted(
        [{"item": (r.get("item") or "").strip(), "quantity": int(r.get("quantity", 1))} for r in order_array],
        key=lambda x: x["item"].lower(),
    )
    return "|".join(f"{r['quantity']}x {r['item']}" for r in lines if r["item"])


def append_visit(
    *,
    placa_normalizada: str,
    placa_original: str,
    nombre: str,
    orden: list[dict],
    suggestion_accepted: bool | None = None,
) -> dict:
    """Añade una visita y devuelve el registro guardado."""
    rows = _load_all()
    now = datetime.now(timezone.utc).astimezone()
    record = {
        "placa_normalizada": placa_normalizada,
        "placa_original": placa_original,
        "nombre": (nombre or "").strip(),
        "orden": orden,
        "fecha_hora": now.isoformat(timespec="seconds"),
        "suggestion_accepted": suggestion_accepted,
    }
    rows.append(record)
    _save_all(rows)
    return record


def prior_visit_count(normalized_plate: str) -> int:
    return len(visits_for_plate(normalized_plate))


def most_common_order(visits: list[dict]) -> list[dict] | None:
    """
    Agrupa visitas por canonical_order_key(orden), cuenta frecuencia.
    Devuelve el array 'orden' de la clave más frecuente; empate → visita más reciente.
    """
    if not visits:
        return None
    pairs: list[tuple[int, str, list[dict]]] = []
    for i, v in enumerate(visits):
        ol = order_as_list(v.get("orden"))
        if not ol:
            continue
        k = canonical_order_key(ol)
        if not k:
            continue
        pairs.append((i, k, ol))
    if not pairs:
        return None
    counts = Counter(p for _, p, _ in pairs)
    max_count = max(counts.values())
    tied = {p for p, n in counts.items() if n == max_count}
    for i, k, ol in reversed(pairs):
        if k in tied:
            return [dict(x) for x in ol]
    return None


def last_complete_order(visits: list[dict]) -> list[dict] | None:
    """Última visita con 'orden' no vacío (desde el final)."""
    for v in reversed(visits):
        ol = order_as_list(v.get("orden"))
        if ol:
            return [dict(x) for x in ol]
    return None


# Tier boundaries for suggestion strategy (Phase 2)
TIER_1_MAX_VISITS = 2      # 1–2 visitas: último pedido
TIER_2_MAX_VISITS = 10     # 3–10 visitas: repetición exacta o fallback
TIER_3_MAX_VISITS = 19     # 11–19 visitas: perfil probabilístico
TIER_3_PLUS_MIN_VISITS = 20  # 20+ visitas: perfil probabilístico "usual"


def _has_repeated_combo(visits: list[dict]) -> bool:
    """True si existe alguna combinación exacta de pedido repetida (count > 1)."""
    keys: list[str] = []
    for v in visits:
        ol = order_as_list(v.get("orden"))
        if not ol:
            continue
        k = canonical_order_key(ol)
        if k:
            keys.append(k)
    if not keys:
        return False
    counts = Counter(keys)
    return any(n > 1 for n in counts.values())


def _tier1_last_order(visits: list[dict]) -> tuple[str | None, list[dict] | None]:
    last = last_complete_order(visits)
    if not last:
        return None, None
    summary = format_order_summary(last)
    return f"Última vez pediste: {summary}", last


def _tier2_repeated_or_last(visits: list[dict]) -> tuple[str | None, list[dict] | None]:
    """
    Usa combinación exacta repetida cuando existe.
    Si no, vuelve a lógica de Tier 1.
    """
    if _has_repeated_combo(visits):
        common = most_common_order(visits)
        if common:
            summary = format_order_summary(common)
            return f"¿Tu pedido de siempre? {summary}", common
    return _tier1_last_order(visits)


def _build_probabilistic_profile(visits: list[dict]) -> list[dict]:
    """
    Para cada ítem, calcula % de visitas donde aparece.
    Incluye ítems con presencia >= config.SUGGESTION_THRESHOLD.
    Cantidad elegida por ítem: moda de cantidades observadas.
    """
    if not visits:
        return []

    # item -> set(indices de visita donde aparece)
    appearance_by_item: dict[str, set[int]] = {}
    # item -> Counter(cantidades vistas)
    qty_counter_by_item: dict[str, Counter] = {}

    for idx, v in enumerate(visits):
        ol = order_as_list(v.get("orden"))
        if not ol:
            continue
        seen_in_visit: set[str] = set()
        for row in ol:
            item = (row.get("item") or "").strip()
            q = int(row.get("quantity", 1))
            if not item:
                continue
            if item not in seen_in_visit:
                appearance_by_item.setdefault(item, set()).add(idx)
                seen_in_visit.add(item)
            qty_counter_by_item.setdefault(item, Counter())[q] += 1

    if not appearance_by_item:
        return []

    total_visits = len(visits)
    out: list[dict] = []
    for item, idx_set in appearance_by_item.items():
        pct = len(idx_set) / total_visits
        if pct < config.SUGGESTION_THRESHOLD:
            continue
        qty_counts = qty_counter_by_item.get(item, Counter())
        if not qty_counts:
            continue
        # Moda; desempate: cantidad menor para consistencia.
        max_n = max(qty_counts.values())
        tied = [q for q, n in qty_counts.items() if n == max_n]
        chosen_qty = min(tied)
        out.append({"item": item, "quantity": int(chosen_qty)})

    out.sort(key=lambda r: (r.get("item") or "").lower())
    return out


def suggestion_from_history(visits: list[dict]) -> tuple[str | None, list[dict] | None]:
    """
    Devuelve (texto_sugerencia, orden_sugerido como lista).
    """
    if not visits:
        return None, None

    n = len(visits)

    # Tier 1 (1–2): último pedido completo
    if n <= TIER_1_MAX_VISITS:
        return _tier1_last_order(visits)

    # Tier 2 (3–10): combinación exacta repetida, si existe
    if n <= TIER_2_MAX_VISITS:
        return _tier2_repeated_or_last(visits)

    # Tier 3 / 3+ (11+): perfil probabilístico
    profile = _build_probabilistic_profile(visits)
    if profile:
        summary = format_order_summary(profile)
        if n <= TIER_3_MAX_VISITS:
            return f"Sueles pedir: {summary}", profile
        if n >= TIER_3_PLUS_MIN_VISITS:
            return f"Tu usual: {summary}", profile

    # Fallback estricto solicitado: Tier 3 -> Tier 2 -> Tier 1
    t2_text, t2_order = _tier2_repeated_or_last(visits)
    if t2_order:
        return t2_text, t2_order

    # Nunca devolver None/None si hay visitas: fallback mínimo a lista vacía legible.
    return "Última vez pediste: ", []


def suggestion_for_prior_count(prior: int, visits: list[dict]) -> tuple[str | None, list[dict] | None]:
    """Compatibilidad: ignora prior; usa solo el historial."""
    if prior <= 0:
        return None, None
    return suggestion_from_history(visits)
