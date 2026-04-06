"""
Sistema Drive-Thru para Cafeterías - Backend Flask.

Escanea placas, identifica clientes recurrentes y muestra
información personalizada al operador.
"""
import threading
import time
from flask import Flask, jsonify, render_template, request

import config
from services.customer_db import get_customer_by_plate, normalize_plate, upsert_customer
from services.menu_data import MENU_CATEGORIES, is_valid_order
from services.plate_ocr import read_plate_from_camera
from services import visit_history

app = Flask(__name__)

# Estado actual: última placa detectada y timestamp
_current_plate: str | None = None
_plate_lock = threading.Lock()


def _build_operator_state(plate: str | None) -> dict:
    """Estado completo para la pantalla del operador."""
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
    }


def _camera_simulation_loop():
    """Hilo que simula detecciones de cámara periódicamente."""
    global _current_plate
    while True:
        time.sleep(config.CAMERA_SIMULATION_INTERVAL)
        if config.CAMERA_MODE == "simulated":
            plate = read_plate_from_camera()
            with _plate_lock:
                _current_plate = plate


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
    global _current_plate
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()

    with _plate_lock:
        _current_plate = plate if plate else None

    return jsonify(_build_operator_state(_current_plate))


@app.route("/api/simulate-arrival")
def api_simulate_arrival():
    """Simula la llegada de un cliente (placa aleatoria)."""
    global _current_plate
    plate = read_plate_from_camera()
    with _plate_lock:
        _current_plate = plate
    return jsonify(_build_operator_state(plate))


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
    if config.CAMERA_MODE == "simulated" and config.AUTO_SIMULATE_ARRIVALS:
        t = threading.Thread(target=_camera_simulation_loop, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
