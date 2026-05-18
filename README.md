# Sistema Drive-Thru para Cafeterías

MVP de un sistema que reconoce placas en el drive-thru y muestra información personalizada al operador.

## Flujo del sistema

1. Una cámara lee la placa del vehículo que llega
2. El sistema busca en la base de datos si el cliente ya ha visitado antes
3. **Cliente conocido:** "Hola [Nombre], ¿tu [orden favorita] de siempre?"
4. **Cliente nuevo:** "¡Bienvenido! Pregunta su nombre"
5. La pantalla se actualiza automáticamente al detectar nuevos clientes

## Estructura del proyecto

```
Prototype_cursor/
├── app.py              # Backend Flask
├── config.py           # Configuración
├── requirements.txt
├── data/
│   └── clientes.csv    # Base de datos de clientes
├── services/
│   ├── plate_ocr.py    # Lectura de placas (simulado, listo para OCR real)
│   └── customer_db.py  # Consultas a la base de datos
├── static/
│   ├── css/style.css
│   └── js/main.js
├── templates/
│   └── operator.html
└── README.md
```

## Cómo ejecutar

### 1. Crear entorno virtual (recomendado)

```bash
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate   # Linux/Mac
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Iniciar el servidor

```bash
python app.py
```

### 4. Abrir en el navegador

```
http://localhost:5000
```

## Uso

- **Detección automática:** Cada ~12 segundos se simula la llegada de un cliente (70% conocidos, 30% nuevos)
- **Probar manualmente:** Escribe una placa (ej: `ABC123`, `XYZ789`) y pulsa **Buscar**
- **Simular llegada:** Pulsa **Simular llegada** para una detección inmediata aleatoria

## Placas de ejemplo en la base de datos

| Placa   | Nombre          |
|---------|-----------------|
| ABC123  | Carlos Mendoza  |
| XYZ789  | María González  |
| DEF456  | Rosa Martínez   |
| GHI789  | Pedro Sánchez   |
| JKL012  | Ana Rodríguez   |
| MNO345  | Luis Fernández  |
| PQR678  | Carmen López    |
| STU901  | Jorge Ramírez   |
| VWX234  | Sofía Herrera   |
| YZA567  | Ricardo Torres  |

## Modos de cámara

El backend soporta 3 modos de captura configurables con `CAMERA_MODE`:

- `simulated`: placas falsas/aleatorias (sin cámara física).
- `real`: webcam local con `cv2.VideoCapture(0)`.
- `hikvision_rtsp`: cámara IP Hikvision por RTSP con grabber en hilo de fondo (latest-frame cache).

Ejemplos en Windows:

```bash
set CAMERA_MODE=simulated
python app.py
```

```bash
set CAMERA_MODE=real
python app.py
```

```bash
set CAMERA_MODE=hikvision_rtsp
python app.py
```

## Hikvision setup

Variables de entorno disponibles (todas opcionales, con default):

- `HIKVISION_IP=192.168.0.64`
- `HIKVISION_USER=admin`
- `HIKVISION_PASSWORD=` (vacío por defecto)
- `HIKVISION_RTSP_PORT=554`
- `HIKVISION_RTSP_PATH=/Streaming/Channels/102`

Prueba de conectividad RTSP (sin levantar Flask):

```bash
python scripts/test_rtsp_connection.py
```

El script intenta leer 10 frames en ~3 segundos y guarda el último en `data/test_rtsp_frame.jpg`.
