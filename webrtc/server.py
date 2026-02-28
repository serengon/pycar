"""
PyCar WebRTC - Servidor Raspi (modo AP + joystick local)
=========================================================
Todo corre en la Raspi:
- Access Point WiFi propio
- Webcam → MediaMTX → WebRTC
- Joystick USB → pygame → Arduino serial
- WebSocket envia telemetria al celu (solo lectura)

Uso:
    cd ~/pycar
    source venv/bin/activate
    python server.py
    
    Desde el celu: http://192.168.4.1:8080
"""

import asyncio
import subprocess
import signal
import sys
import os
import json
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from collections import deque

import serial
import pygame
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

# ============== CONFIG ==============
SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUD = 115200
WEB_PORT = 8080
MEDIAMTX_BIN = "/opt/mediamtx"
MEDIAMTX_CFG = os.environ.get(
    "MEDIAMTX_CFG",
    str(Path(__file__).parent / "mediamtx_lan.yml")
)

# ============== PRESETS DE CALIDAD ==============
@dataclass
class VideoPreset:
    width: int
    height: int
    bitrate: str
    gop: int

VIDEO_PRESETS = {
    "low":  VideoPreset(424, 240,  "500k",  8),   # nativa C505, WiFi débil
    "med":  VideoPreset(640, 360,  "1500k", 10),  # nativa C505, sweet spot
    "high": VideoPreset(1280, 720, "4000k", 15),  # nativa C505, máxima calidad
}
DEFAULT_PRESET = "med"
MEDIAMTX_TMP_CFG = "/tmp/pycar_mediamtx_runtime.yml"
current_preset_name = DEFAULT_PRESET
# ================================================

# Joystick (mismos valores que el script original)
EJE_Q = 4          # Direccion
EJE_G = 3          # Acelerador
BOTON_R = 10
BOTON_E = 5
DEADZONE = 0.05
SEND_INTERVAL = 0.1  # Segundos entre envios de ejes
# ====================================

app = FastAPI()

# --- Estado global (compartido entre threads) ---
telemetry = {
    "q": 0.0,
    "g": 0.0,
    "btn_r": False,
    "btn_e": False,
    "serial_ok": False,
    "joystick_ok": False,
    "joystick_name": "",
    "tx_hist": [],
    "rx_hist": [],
    "fps": 0,
    "quality": DEFAULT_PRESET,
    "quality_changing": False,
}

MAX_HIST = 4
tx_hist = deque(maxlen=MAX_HIST)
rx_hist = deque(maxlen=MAX_HIST)

# Clientes WebSocket conectados (celulares viendo)
ws_clients = set()

# --- Serial al Arduino ---
ser = None
serial_ok = False

def init_serial():
    global ser, serial_ok
    for port in [SERIAL_PORT, "/dev/ttyACM0", "/dev/ttyUSB1"]:
        try:
            ser = serial.Serial(port, SERIAL_BAUD, timeout=0.01)
            time.sleep(2)  # Arduino resetea al abrir el puerto (DTR), esperar boot
            serial_ok = True
            telemetry["serial_ok"] = True
            print(f"  ✓ Arduino en {port}")
            return
        except:
            continue
    print("  ⚠ Arduino no encontrado")

# --- MediaMTX ---
mediamtx_proc = None

MTX_LOG_DIR = "/tmp/pycar_logs"
MTX_LOG_MAX = 5

def _mediamtx_log_reader(proc):
    """Escribe log de esta sesión a archivo rotativo; solo ERR va a consola."""
    os.makedirs(MTX_LOG_DIR, exist_ok=True)

    # Rotar: eliminar logs viejos si hay más de MTX_LOG_MAX
    logs = sorted(Path(MTX_LOG_DIR).glob("mediamtx_*.log"))
    for old in logs[: max(0, len(logs) - MTX_LOG_MAX + 1)]:
        old.unlink()

    log_path = Path(MTX_LOG_DIR) / f"mediamtx_{int(time.time())}.log"
    with open(log_path, "w") as f:
        for line in proc.stdout:
            text = line.decode(errors="ignore").rstrip()
            f.write(text + "\n")
            f.flush()
            if "ERR" in text:
                print(f"  [MTX] {text}")

def _build_mediamtx_cfg(preset: VideoPreset) -> str:
    """Lee el yml base, reemplaza solo el bloque paths con el preset dado."""
    with open(MEDIAMTX_CFG, "r") as f:
        base = f.read()
    header = base[:base.index("paths:")] if "paths:" in base else base
    ffmpeg_cmd = (
        f"ffmpeg -f v4l2 -input_format mjpeg "
        f"-video_size {preset.width}x{preset.height} -framerate 30 "
        f"-i /dev/video0 -fflags +nobuffer -flags +low_delay "
        f"-vf format=yuv420p -c:v libx264 -profile:v baseline "
        f"-preset ultrafast -tune zerolatency "
        f"-b:v {preset.bitrate} -g {preset.gop} "
        f"-f rtsp rtsp://localhost:$RTSP_PORT/$MTX_PATH"
    )
    return header + f"paths:\n  cam:\n    runOnInit: {ffmpeg_cmd}\n    runOnInitRestart: yes\n"

def write_preset_cfg(preset: VideoPreset) -> str:
    """Escribe el yml del preset en /tmp y retorna la ruta."""
    content = _build_mediamtx_cfg(preset)
    with open(MEDIAMTX_TMP_CFG, "w") as f:
        f.write(content)
    return MEDIAMTX_TMP_CFG

def start_mediamtx(cfg_path: str = None):
    global mediamtx_proc
    cfg = cfg_path or MEDIAMTX_CFG
    if not os.path.exists(MEDIAMTX_BIN):
        print(f"  ⚠ MediaMTX no encontrado en {MEDIAMTX_BIN}")
        return
    mediamtx_proc = subprocess.Popen(
        [MEDIAMTX_BIN, cfg],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    print(f"  ✓ MediaMTX PID:{mediamtx_proc.pid}")
    log_thread = threading.Thread(target=_mediamtx_log_reader, args=(mediamtx_proc,), daemon=True)
    log_thread.start()

def stop_mediamtx():
    global mediamtx_proc
    if mediamtx_proc:
        mediamtx_proc.terminate()
        try:
            mediamtx_proc.wait(timeout=5)
        except:
            mediamtx_proc.kill()

# --- Joystick + Serial Thread ---
def aplicar_deadzone(valor, zona):
    if abs(valor) < zona:
        return 0
    return -valor

def joystick_loop():
    """Thread dedicado: lee joystick → envia al Arduino → actualiza telemetria"""
    global serial_ok

    pygame.init()
    pygame.joystick.init()

    joy = None
    joystick_ok = False
    ultimo_envio = 0
    prev_btn_r = False
    prev_btn_e = False

    print("  ✓ Joystick loop iniciado")

    while True:
        try:
            # Eventos pygame
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    joy = pygame.joystick.Joystick(0)
                    joy.init()
                    joystick_ok = True
                    telemetry["joystick_ok"] = True
                    telemetry["joystick_name"] = joy.get_name()
                    print(f"  ✓ Joystick: {joy.get_name()}")

                if event.type == pygame.JOYDEVICEREMOVED:
                    joystick_ok = False
                    joy = None
                    telemetry["joystick_ok"] = False
                    telemetry["joystick_name"] = ""
                    print("  ✗ Joystick desconectado")

            if not joy or not joystick_ok:
                time.sleep(0.1)
                continue

            ahora = time.time()

            # Leer ejes
            valor_q = aplicar_deadzone(joy.get_axis(EJE_Q), DEADZONE)
            valor_g = aplicar_deadzone(joy.get_axis(EJE_G), DEADZONE)

            telemetry["q"] = round(valor_q, 2)
            telemetry["g"] = round(valor_g, 2)

            # Botones (flanco de subida)
            btn_r = joy.get_button(BOTON_R)
            btn_e = joy.get_button(BOTON_E)

            telemetry["btn_r"] = bool(btn_r)
            telemetry["btn_e"] = bool(btn_e)

            if btn_r and not prev_btn_r:
                if ser and ser.is_open:
                    ser.write(b"R\n")
                    tx_hist.appendleft("R")
            if btn_e and not prev_btn_e:
                if ser and ser.is_open:
                    ser.write(b"E\n")
                    tx_hist.appendleft("E")

            prev_btn_r = btn_r
            prev_btn_e = btn_e

            # Envio periodico de ejes
            if ahora - ultimo_envio >= SEND_INTERVAL:
                if ser and ser.is_open:
                    msg = f"Q{valor_q:.2f} G{valor_g:.2f}"
                    try:
                        ser.write((msg + "\n").encode())
                        tx_hist.appendleft(msg)
                    except serial.SerialException:
                        serial_ok = False
                        telemetry["serial_ok"] = False
                ultimo_envio = ahora

            # Leer respuesta Arduino
            if ser and ser.is_open:
                try:
                    while ser.in_waiting > 0:
                        linea = ser.readline().decode(errors="ignore").strip()
                        if linea:
                            rx_hist.append(linea)
                except:
                    pass

            # Actualizar historial en telemetria
            telemetry["tx_hist"] = list(tx_hist)
            telemetry["rx_hist"] = list(rx_hist)

            time.sleep(0.005)

        except Exception as e:
            print(f"  ✗ Error joystick loop: {e}")
            time.sleep(1)

# --- Broadcast telemetria a celulares ---
async def telemetry_broadcaster():
    """Envia telemetria a todos los celulares conectados cada 100ms"""
    while True:
        if ws_clients:
            data = json.dumps(telemetry)
            dead = set()
            for ws in ws_clients:
                try:
                    await ws.send_text(data)
                except:
                    dead.add(ws)
            ws_clients.difference_update(dead)
        await asyncio.sleep(0.1)

# --- Rutas HTTP ---

@app.get("/")
async def index():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text())

@app.get("/status")
async def status():
    return JSONResponse(telemetry)

# --- WebSocket (solo envia telemetria, el celu no controla) ---

@app.websocket("/ws")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    print(f"  📱 Celu conectado ({len(ws_clients)} activos)")

    try:
        while True:
            # Mantener conexion viva, ignorar mensajes del celu
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)
        print(f"  📱 Celu desconectado ({len(ws_clients)} activos)")

# --- Calidad de video ---

quality_lock = None  # asyncio.Lock, se inicializa en startup
QUALITY_RESTART_DELAY = 2.0

@app.post("/quality/{preset_name}")
async def set_quality(preset_name: str):
    global current_preset_name
    if preset_name not in VIDEO_PRESETS:
        return JSONResponse({"error": f"Preset inválido. Opciones: {list(VIDEO_PRESETS.keys())}"}, status_code=400)
    if preset_name == current_preset_name:
        return JSONResponse({"status": "ok", "changed": False})

    async with quality_lock:
        telemetry["quality_changing"] = True
        telemetry["quality"] = preset_name
        try:
            cfg_path = write_preset_cfg(VIDEO_PRESETS[preset_name])
        except Exception as e:
            telemetry["quality_changing"] = False
            telemetry["quality"] = current_preset_name
            return JSONResponse({"error": str(e)}, status_code=500)
        stop_mediamtx()
        await asyncio.sleep(QUALITY_RESTART_DELAY)
        start_mediamtx(cfg_path)
        current_preset_name = preset_name
        telemetry["quality_changing"] = False

    p = VIDEO_PRESETS[preset_name]
    print(f"  ✓ Calidad: {preset_name} ({p.width}x{p.height} {p.bitrate})")
    return JSONResponse({"status": "ok", "quality": preset_name, "changed": True})

# --- Lifecycle ---

@app.on_event("startup")
async def startup():
    global quality_lock
    quality_lock = asyncio.Lock()
    try:
        cfg_path = write_preset_cfg(VIDEO_PRESETS[DEFAULT_PRESET])
        start_mediamtx(cfg_path)
    except Exception:
        start_mediamtx()
    asyncio.create_task(telemetry_broadcaster())

@app.on_event("shutdown")
async def shutdown():
    stop_mediamtx()
    if ser and ser.is_open:
        ser.close()
    pygame.quit()

def signal_handler(sig, frame):
    stop_mediamtx()
    if ser and ser.is_open:
        ser.close()
    pygame.quit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# --- Main ---
if __name__ == "__main__":
    print("=" * 50)
    print("  🚗 PyCar - Control Station (AP Mode)")
    print("=" * 50)

    init_serial()

    # Joystick en thread separado
    joy_thread = threading.Thread(target=joystick_loop, daemon=True)
    joy_thread.start()

    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=WEB_PORT)
