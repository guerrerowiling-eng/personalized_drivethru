"""
Sistema Drive-Thru para Cafeterías - Backend Flask.

Escanea placas, identifica clientes recurrentes y muestra
información personalizada al operador.
"""
import re
import threading
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request, Response

import config
from services.customer_db import (
    get_customer_by_plate,
    normalize_plate,
    update_customer_nickname,
    upsert_customer,
)
from services.menu_data import MENU_CATEGORIES, is_valid_order
from services.plate_ocr import (
    get_cached_preview_jpeg,
    read_plate_from_camera,
    release_camera,
    start_preview_capture_loop,
)
from services import visit_history

app = Flask(__name__)

# Estado actual: última placa detectada y timestamp
_current_plate: str | None = None
_plate_lock = threading.RLock()
# Última placa Guatemala válida (cámara o manual) para fallback tras fallo OCR
_last_valid_plate: str | None = None
_last_valid_plate_monotonic: float = 0.0
# Tras fallo de detección real, mostrar mensaje hasta este instante (time.monotonic)
_detection_failed_until: float = 0.0

_GT_PLATE_RE = re.compile(r"^P[A-Z0-9]{6}$")


def _is_valid_gt_plate(plate: str) -> bool:
    """Placa Guatemala normalizada: P + 6 alfanuméricos."""
    if not plate or not plate.strip():
        return False
    n = normalize_plate(plate)
    return bool(_GT_PLATE_RE.fullmatch(n))


def _build_operator_state(plate: str | None) -> dict:
    """Estado completo para la pantalla del operador."""
    global _detection_failed_until
    cm = config.get_effective_camera_mode()
    with _plate_lock:
        now = time.monotonic()
        if _detection_failed_until and now >= _detection_failed_until:
            _detection_failed_until = 0.0
        show_detection_failed = bool(
            not plate and _detection_failed_until and now < _detection_failed_until
        )

    if show_detection_failed:
        return {
            "type": "detection_failed",
            "message": "No se detectó placa. Intenta de nuevo o ingresa manualmente",
            "plate": None,
            "customer": None,
            "prior_visits": 0,
            "suggestion_text": None,
            "suggested_order": None,
            "show_suggestion_actions": False,
            "hint_nickname": None,
            "needs_nickname": False,
            "camera_mode": cm,
        }

    if not plate:
        return {
            "type": "idle",
            "message": "Esperando cliente…",
            "plate": None,
            "customer": None,
            "prior_visits": 0,
            "suggestion_text": None,
            "suggested_order": None,
            "show_suggestion_actions": False,
            "hint_nickname": None,
            "needs_nickname": False,
            "camera_mode": cm,
        }

    norm = normalize_plate(plate)
    customer = get_customer_by_plate(plate)
    visits = visit_history.visits_for_plate(norm)
    prior = len(visits)
    sug_text, sug_order = visit_history.suggestion_from_history(visits)

    hint_nickname = None
    if not customer and visits:
        hint_nickname = (visits[-1].get("nombre") or "").strip() or None

    if customer:
        nickname = (customer.get("nickname") or customer.get("nombre") or "").strip()
        message = f"¡Hola {nickname}!" if nickname else "¡Hola!"
        typ = "returning"
    else:
        message = "¡Bienvenido!"
        typ = "new"

    return {
        "type": typ,
        "message": message,
        "plate": plate.strip().upper(),
        "customer": {
            "nickname": customer["nickname"],
            "nombre": customer["nickname"],
            "orden_favorita": customer["orden_favorita"],
            "visitas": customer["visitas"],
            "fecha_registro": customer.get("fecha_registro", ""),
            "ultima_visita": customer.get("ultima_visita", ""),
        }
        if customer
        else None,
        "prior_visits": prior,
        "suggestion_text": sug_text,
        "suggested_order": sug_order,
        "show_suggestion_actions": bool(sug_order and len(sug_order) > 0),
        "hint_nickname": hint_nickname,
        "needs_nickname": not bool(customer),
        "camera_mode": cm,
    }


def _camera_simulation_loop():
    """Hilo que simula detecciones de cámara periódicamente."""
    global _current_plate
    while True:
        time.sleep(config.CAMERA_SIMULATION_INTERVAL)
        if config.get_effective_camera_mode() == "simulated":
            plate = read_plate_from_camera()
            with _plate_lock:
                _current_plate = plate


@app.route("/api/camera-mode", methods=["GET"])
def api_camera_mode_get():
    """Modo de cámara efectivo y valor por defecto del entorno."""
    return jsonify({
        "effective": config.get_effective_camera_mode(),
        "env_default": config.CAMERA_MODE,
    })


@app.route("/api/camera-mode", methods=["POST"])
def api_camera_mode_post():
    """Cambia simulado / real en caliente (no modifica variables de entorno)."""
    global _detection_failed_until
    data = request.get_json() or {}
    mode = (data.get("mode") or "").strip().lower()
    try:
        config.set_runtime_camera_mode(mode)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if mode == "simulated":
        release_camera()
    elif mode == "real":
        start_preview_capture_loop()
    with _plate_lock:
        _detection_failed_until = 0.0
    return jsonify({
        "ok": True,
        "effective": config.get_effective_camera_mode(),
    })


@app.route("/api/camera-preview")
def api_camera_preview():
    """Devuelve el último JPEG en caché para vista previa del operador."""
    ok, data, err = get_cached_preview_jpeg()
    if not ok:
        return jsonify({"ok": False, "error": err or "Vista previa no disponible"}), 503
    return Response(data, mimetype="image/jpeg")


@app.route("/")
def operator_page():
    """Pantalla principal del operador."""
    return render_template("operator.html")


@app.route("/api/menu")
def api_menu():
    """Menú por categorías (Café Barista)."""
    return jsonify({"categories": MENU_CATEGORIES})


@app.route("/api/current")
def api_current():
    """Obtiene el estado actual para la pantalla (polling)."""
    with _plate_lock:
        plate = _current_plate
    return jsonify(_build_operator_state(plate))


@app.route("/api/lookup/<plate>")
def api_lookup(plate: str):
    """Busca un cliente por placa (usado al escribir manualmente)."""
    return jsonify(_build_operator_state(plate.strip()))


@app.route("/api/set-plate", methods=["POST"])
def api_set_plate():
    """Permite al operador escribir una placa manualmente."""
    global _current_plate, _last_valid_plate, _last_valid_plate_monotonic, _detection_failed_until
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()

    with _plate_lock:
        _current_plate = plate if plate else None
        now = time.monotonic()
        if plate and _is_valid_gt_plate(plate):
            _last_valid_plate = plate.strip().upper()
            _last_valid_plate_monotonic = now
        _detection_failed_until = 0.0

    return jsonify(_build_operator_state(_current_plate))


@app.route("/api/simulate-arrival")
def api_simulate_arrival():
    """Simula la llegada de un cliente (placa aleatoria)."""
    global _current_plate, _last_valid_plate, _last_valid_plate_monotonic, _detection_failed_until
    plate = read_plate_from_camera()
    with _plate_lock:
        now = time.monotonic()
        if plate:
            p = plate.strip().upper()
            _current_plate = p
            if _is_valid_gt_plate(p):
                _last_valid_plate = p
                _last_valid_plate_monotonic = now
            _detection_failed_until = 0.0
        elif config.get_effective_camera_mode() == "real":
            if _last_valid_plate and (now - _last_valid_plate_monotonic) <= 30.0:
                _current_plate = _last_valid_plate
                _detection_failed_until = 0.0
            else:
                _current_plate = None
                _detection_failed_until = now + 30.0
        else:
            _current_plate = plate
        out_plate = _current_plate
    return jsonify(_build_operator_state(out_plate))


def _sync_customer_after_visit(plate: str, nickname_resolved: str) -> None:
    norm = normalize_plate(plate)
    visits = visit_history.visits_for_plate(norm)
    usual_list = visit_history.most_common_order(visits)
    if not usual_list and visits:
        usual_list = visit_history.order_as_list(visits[-1].get("orden"))
    usual = visit_history.format_order_summary(usual_list) if usual_list else ""
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    existing = get_customer_by_plate(plate)
    fecha_registro = (existing or {}).get("fecha_registro") or now_iso
    upsert_customer(
        plate,
        nickname_resolved,
        usual,
        visitas=len(visits),
        fecha_registro=fecha_registro,
        ultima_visita=now_iso,
    )


@app.route("/api/update-nickname", methods=["POST"])
def api_update_nickname():
    """Actualiza solo el nickname de una placa existente."""
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()
    nickname = (data.get("nickname") or "").strip()
    if not plate:
        return jsonify({"ok": False, "error": "Falta la placa"}), 400
    if not nickname:
        return jsonify({"ok": False, "error": "Escribe el apodo"}), 400

    existing = get_customer_by_plate(plate)
    if existing:
        updated = update_customer_nickname(plate, nickname)
        if not updated:
            return jsonify({"ok": False, "error": "No se pudo actualizar"}), 500
        return jsonify({"ok": True, "state": _build_operator_state(plate)})

    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    upsert_customer(
        plate=plate,
        nickname=nickname,
        orden_favorita="",
        visitas=0,
        fecha_registro=now_iso,
        ultima_visita=now_iso,
    )
    return jsonify({"ok": True, "state": _build_operator_state(plate)})


def _parse_and_validate_items(data: dict) -> tuple[list[dict] | None, str | None]:
    """Valida body['items']; devuelve (lista normalizada, mensaje_error_es) o (None, error)."""
    raw = data.get("items")
    if not isinstance(raw, list):
        return None, "Envía la lista de ítems (items)"
    if len(raw) < 1 or len(raw) > 10:
        return None, "El pedido debe tener entre 1 y 10 líneas"
    merged: dict[str, int] = {}
    for i, row in enumerate(raw):
        if not isinstance(row, dict):
            return None, "Cada línea del pedido debe ser un objeto con item y quantity"
        item = (row.get("item") or "").strip()
        if not item or not is_valid_order(item):
            return None, f"Ítem no válido en la línea {i + 1}"
        q = row.get("quantity", 1)
        try:
            qi = int(q)
        except (TypeError, ValueError):
            return None, f"La cantidad debe ser un número entero (línea {i + 1})"
        if qi < 1 or qi > 99:
            return None, f"Cada cantidad debe estar entre 1 y 99 (línea {i + 1})"
        merged[item] = merged.get(item, 0) + qi
    out = [{"item": k, "quantity": v} for k, v in merged.items()]
    total_qty = sum(r["quantity"] for r in out)
    if total_qty > 10:
        return None, "El total de unidades no puede superar 10"
    if not out:
        return None, "El pedido no tiene líneas válidas"
    return out, None


def _parse_suggestion_accepted(data: dict) -> bool | None:
    v = data.get("suggestion_accepted", None)
    if v is True or v is False:
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
    return None


@app.route("/api/record-visit", methods=["POST"])
def api_record_visit():
    """
    Registra la visita actual: placa, items (lista), nickname (si aplica), suggestion_accepted.
    Actualiza historial JSON y CSV de clientes.
    """
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()
    nickname = (data.get("nickname") or data.get("nombre") or "").strip()

    items_norm, err = _parse_and_validate_items(data)
    if err:
        return jsonify({"ok": False, "error": err}), 400

    if not plate:
        return jsonify({"ok": False, "error": "Falta la placa"}), 400

    norm = normalize_plate(plate)
    existing = get_customer_by_plate(plate)
    visits_before = visit_history.visits_for_plate(norm)
    fallback_name = ""
    if visits_before:
        fallback_name = (visits_before[-1].get("nombre") or "").strip()

    if not existing and not nickname and not fallback_name:
        return jsonify({"ok": False, "error": "Escribe cómo le gusta que le llamen"}), 400

    nickname_final = (
        nickname or (existing["nickname"] if existing else "") or fallback_name
    )
    suggestion_accepted = _parse_suggestion_accepted(data)

    visit_history.append_visit(
        placa_normalizada=norm,
        placa_original=plate.strip().upper(),
        nombre=nickname_final,
        orden=items_norm,
        suggestion_accepted=suggestion_accepted,
    )
    _sync_customer_after_visit(plate, nickname_final)

    with _plate_lock:
        current = _current_plate

    return jsonify({
        "ok": True,
        "state": _build_operator_state(current),
    })


def main():
    if config.get_effective_camera_mode() == "simulated" and config.AUTO_SIMULATE_ARRIVALS:
        t = threading.Thread(target=_camera_simulation_loop, daemon=True)
        t.start()
    if config.get_effective_camera_mode() == "real":
        start_preview_capture_loop()

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
