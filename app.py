"""
Sistema Drive-Thru para Cafeterías - Backend Flask.

Escanea placas, identifica clientes recurrentes y muestra
información personalizada al operador.
"""
import threading
import time
from flask import Flask, jsonify, render_template, request

import config
from services.plate_ocr import read_plate_from_camera
from services.customer_db import get_customer_by_plate

app = Flask(__name__)

# Estado actual: última placa detectada y timestamp
_current_plate: str | None = None
_plate_lock = threading.Lock()


def _get_display_state(plate: str | None) -> dict:
    """Construye el estado para mostrar al operador."""
    if not plate:
        return {
            "type": "idle",
            "message": "Esperando cliente...",
            "plate": None,
            "customer": None,
        }
    
    customer = get_customer_by_plate(plate)
    if customer:
        return {
            "type": "returning",
            "message": f"Hola {customer['nombre']}, ¿tu {customer['orden_favorita']} de siempre?",
            "plate": plate,
            "customer": {
                "nombre": customer["nombre"],
                "orden_favorita": customer["orden_favorita"],
                "visitas": customer["visitas"],
            },
        }
    
    return {
        "type": "new",
        "message": "¡Bienvenido! Pregunta su nombre",
        "plate": plate,
        "customer": None,
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


@app.route("/api/current")
def api_current():
    """Obtiene el estado actual para la pantalla (polling)."""
    with _plate_lock:
        plate = _current_plate
    return jsonify(_get_display_state(plate))


@app.route("/api/lookup/<plate>")
def api_lookup(plate: str):
    """Busca un cliente por placa (usado al escribir manualmente)."""
    customer = get_customer_by_plate(plate)
    if customer:
        return jsonify({
            "found": True,
            "customer": customer,
            "message": f"Hola {customer['nombre']}, ¿tu {customer['orden_favorita']} de siempre?",
        })
    return jsonify({
        "found": False,
        "customer": None,
        "message": "¡Bienvenido! Pregunta su nombre",
    })


@app.route("/api/set-plate", methods=["POST"])
def api_set_plate():
    """Permite al operador escribir una placa manualmente."""
    global _current_plate
    data = request.get_json() or {}
    plate = (data.get("plate") or "").strip()
    
    with _plate_lock:
        _current_plate = plate if plate else None
    
    return jsonify(_get_display_state(_current_plate or plate))


@app.route("/api/simulate-arrival")
def api_simulate_arrival():
    """Simula la llegada de un cliente (placa aleatoria)."""
    global _current_plate
    plate = read_plate_from_camera()
    with _plate_lock:
        _current_plate = plate
    return jsonify(_get_display_state(plate))


def main():
    if config.CAMERA_MODE == "simulated":
        t = threading.Thread(target=_camera_simulation_loop, daemon=True)
        t.start()
    
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
