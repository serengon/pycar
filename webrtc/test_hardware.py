"""
PyCar - Diagnóstico de hardware
Ejecutar: python3 test_hardware.py
Prueba cada componente independientemente y reporta el estado.
"""

import sys
import os

OK  = "  [OK] "
ERR = "  [FAIL] "
WRN = "  [WARN] "

# ─── 1. Serial / Arduino ────────────────────────────────────────────────────
def test_serial():
    print("\n── Arduino (serial) ──")
    try:
        import serial
        import serial.tools.list_ports
    except ImportError:
        print(ERR + "pyserial no instalado")
        return

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print(ERR + "Ningún puerto serie detectado")
        return

    for p in ports:
        print(f"  Encontrado: {p.device}  ({p.description})")

    candidatos = [p.device for p in ports
                  if any(x in p.device for x in ["ttyUSB", "ttyACM"])]
    if not candidatos:
        print(WRN + "No hay ttyUSB/ttyACM — ¿driver ch341 cargado?")
        print("       Probar: sudo modprobe ch341")
        return

    for puerto in candidatos:
        try:
            s = serial.Serial(puerto, 115200, timeout=1)
            s.close()
            print(OK + f"Conexión exitosa en {puerto}")
        except PermissionError:
            print(ERR + f"{puerto} — Sin permisos. Ejecutar:")
            print(f"       sudo usermod -a -G dialout {os.getenv('USER','$USER')}")
            print("       (luego cerrar sesión y volver a entrar)")
        except Exception as e:
            print(ERR + f"{puerto} — {e}")

# ─── 2. Joystick ────────────────────────────────────────────────────────────
def test_joystick():
    print("\n── Joystick ──")
    try:
        import pygame
    except ImportError:
        print(ERR + "pygame no instalado")
        return

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.joystick.init()

    n = pygame.joystick.get_count()
    if n == 0:
        print(ERR + "Ningún joystick detectado")
        print("       ¿Está conectado el 8BitDo? Verificar: ls /dev/input/js*")
        pygame.quit()
        return

    for i in range(n):
        joy = pygame.joystick.Joystick(i)
        joy.init()
        print(OK + f"Joystick {i}: {joy.get_name()}")
        print(f"       Ejes: {joy.get_numaxes()}  Botones: {joy.get_numbuttons()}")

        # Leer ejes actuales
        vals = [round(joy.get_axis(a), 3) for a in range(joy.get_numaxes())]
        print(f"       Valores ejes: {vals}")

    pygame.quit()

# ─── 3. Webcam ──────────────────────────────────────────────────────────────
def test_webcam():
    print("\n── Webcam ──")
    import glob
    devs = sorted(glob.glob("/dev/video*"))
    if not devs:
        print(ERR + "No se encontró ningún /dev/video*")
        return
    for d in devs:
        print(f"  Encontrado: {d}")

    # Verificar que ffmpeg puede abrir el primero
    import subprocess
    cmd = ["ffmpeg", "-f", "v4l2", "-i", devs[0],
           "-frames:v", "1", "-f", "null", "-", "-loglevel", "error"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    if r.returncode == 0:
        print(OK + f"{devs[0]} accesible por ffmpeg")
    else:
        print(ERR + f"ffmpeg no puede abrir {devs[0]}")
        print(f"       {r.stderr.strip()}")

# ─── 4. MediaMTX ────────────────────────────────────────────────────────────
def test_mediamtx():
    print("\n── MediaMTX ──")
    bin_path = "/opt/mediamtx"
    if not os.path.exists(bin_path):
        print(ERR + f"No encontrado en {bin_path}")
        print("       Ejecutar: sudo ./setup_base.sh")
        return
    print(OK + f"Binario presente en {bin_path}")

    # Ver si ya está corriendo
    import subprocess
    r = subprocess.run(["pgrep", "-x", "mediamtx"], capture_output=True)
    if r.returncode == 0:
        print(OK + f"Proceso activo (PID {r.stdout.strip().decode()})")
    else:
        print(WRN + "No está corriendo (se inicia automáticamente con start.sh)")

# ─── 5. Puertos en uso ──────────────────────────────────────────────────────
def test_puertos():
    print("\n── Puertos de red ──")
    import subprocess
    for puerto, nombre in [(8080, "Web UI"), (8889, "WebRTC"), (8554, "RTSP")]:
        r = subprocess.run(["ss", "-tlnp", f"sport = :{puerto}"],
                           capture_output=True, text=True)
        if f":{puerto}" in r.stdout:
            print(OK + f":{puerto} ({nombre}) — escuchando")
        else:
            print(WRN + f":{puerto} ({nombre}) — no está escuchando aún")

# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("  PyCar — Diagnóstico de hardware")
    print("=" * 50)

    test_serial()
    test_joystick()
    test_webcam()
    test_mediamtx()
    test_puertos()

    print("\n" + "=" * 50)
    print("  Diagnóstico completo")
    print("=" * 50)
