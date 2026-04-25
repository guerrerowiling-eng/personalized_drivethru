"""
Sistema Drive-Thru para Cafeterías - Backend Flask.

Escanea placas, identifica clientes recurrentes y muestra
información personalizada al operador.
"""
import re
import threading
import time
from flask import Flask, jsonify, render_template, request, Response

import config
from services.customer_db import get_customer_by_plate, normalize_plate, upsert_customer
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
            "hint_nombre": None,
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
            "hint_nombre": None,
            "camera_mode": cm,
        }

    norm = normalize_plate(plate)
    customer = get_customer_by_plate(plate)
    visits = visit_history.visits_for_plate(norm)
    prior = len(visits)
    sug_text, sug_order = visit_history.suggestion_from_history(visits)

    hint_nombre = None
    if not customer and visits:
        hint_nombre = (visits[-1].get("nombre") or "").strip() or None

    if customer:
        message = f"Hola {customer['nombre']}"
        if prior == 0:
            message = f"{message} — ¿qué deseas hoy?"
        typ = "returning"
    else:
        if prior == 0:
            message = "Cliente nuevo — pide nombre y elige el pedido en el menú"
        elif sug_text:
            last_name = hint_nombre or ""
            if last_name:
                message = f"Cliente reconocido ({last_name})"
            else:
                message = "Cliente reconocido"
        else:
            message = "Cliente nuevo — completa registro"
        typ = "new"

    return {
        "type": typ,
        "message": message,
        "plate": plate.strip().upper(),
        "customer": {
            "nombre": customer["nombre"],
            "orden_favorita": customer["orden_favorita"],
            "visitas": customer["visitas"],
        }
        if customer
        else None,
        "prior_visits": prior,
        "suggestion_text": sug_text,
        "suggested_order": sug_order,
        "show_suggestion_actions": bool(sug_order),
        "hint_nombre": hint_nombre,
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


def _sync_customer_after_visit(plate: str, nombre_resolved: str) -> None:
    norm = normalize_plate(plate)
    visits = visit_history.visits_for_plate(norm)
    usual = visit_history.most_common_order(visits)
    if not usual and visits:
        usual = visits[-1].get("orden", "")
    if not usual:
        usual = ""
    upsert_customer(plate, nombre_resolved, usual, visitas=len(visits))


@app.route("/api/record-visit", methods=["POST"])
def api_record_visit():
    """
    Registra la visita actual: placa, nombre (si aplica), pedido del menú.
    Actualiza historial JSON y CSV de clientes.
    """
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()
    orden = (data.get("orden") or "").strip()
    nombre = (data.get("nombre") or "").strip()

    if not plate:
        return jsonify({"ok": False, "error": "Falta la placa"}), 400
    if not orden or not is_valid_order(orden):
        return jsonify({"ok": False, "error": "Selecciona un ítem válido del menú"}), 400

    norm = normalize_plate(plate)
    existing = get_customer_by_plate(plate)
    visits_before = visit_history.visits_for_plate(norm)
    fallback_name = ""
    if visits_before:
        fallback_name = (visits_before[-1].get("nombre") or "").strip()

    if not existing and not nombre and not fallback_name:
        return jsonify({"ok": False, "error": "Escribe el nombre del cliente"}), 400

    nombre_final = nombre or (existing["nombre"] if existing else "") or fallback_name
    visit_history.append_visit(
        placa_normalizada=norm,
        placa_original=plate.strip().upper(),
        nombre=nombre_final,
        orden=orden,
    )
    _sync_customer_after_visit(plate, nombre_final)

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
