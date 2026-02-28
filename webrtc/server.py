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
            serial_ok = True
            telemetry["serial_ok"] = True
            print(f"  ✓ Arduino en {port}")
            return
        except:
            continue
    print("  ⚠ Arduino no encontrado")

# --- MediaMTX ---
mediamtx_proc = None

MTX_LOG_FILE = "/tmp/mediamtx.log"
MTX_LOG_LINES = 5

def _mediamtx_log_reader(proc):
    """Guarda últimas MTX_LOG_LINES líneas en archivo; solo ERR va a consola."""
    buf = deque(maxlen=MTX_LOG_LINES)
    for line in proc.stdout:
        text = line.decode(errors="ignore").rstrip()
        buf.append(text)
        with open(MTX_LOG_FILE, "w") as f:
            f.write("\n".join(buf) + "\n")
        if "ERR" in text:
            print(f"  [MTX] {text}")

def start_mediamtx():
    global mediamtx_proc
    if not os.path.exists(MEDIAMTX_BIN):
        print(f"  ⚠ MediaMTX no encontrado en {MEDIAMTX_BIN}")
        return
    mediamtx_proc = subprocess.Popen(
        [MEDIAMTX_BIN, MEDIAMTX_CFG],
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
                    tx_hist.append("R")
            if btn_e and not prev_btn_e:
                if ser and ser.is_open:
                    ser.write(b"E\n")
                    tx_hist.append("E")

            prev_btn_r = btn_r
            prev_btn_e = btn_e

            # Envio periodico de ejes
            if ahora - ultimo_envio >= SEND_INTERVAL:
                if ser and ser.is_open:
                    msg = f"Q{valor_q:.2f} G{valor_g:.2f}"
                    try:
                        ser.write((msg + "\n").encode())
                        tx_hist.append(msg)
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

# --- Lifecycle ---

@app.on_event("startup")
async def startup():
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
