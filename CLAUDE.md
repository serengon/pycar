# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

**PyCar** es un sistema de control remoto para un vehículo RC basado en Raspberry Pi. Combina streaming FPV vía WebRTC, control por joystick USB y comunicación serial con un Arduino.

## Cómo ejecutar

### En Raspberry Pi (servidor)

```bash
# Configuración inicial (una sola vez)
sudo ./webrtc/setup_base.sh      # Instala dependencias, crea venv y MediaMTX

# Modo LAN — desarrollo, conectado al router de casa
cd webrtc
sh start_lan.sh                  # Detecta y muestra la IP automáticamente

# Modo FPV — autónomo con AP propio (configurar solo la primera vez)
sudo ./webrtc/setup_ap.sh
sudo reboot
sh webrtc/start_fpv.sh           # Verifica que el AP esté activo antes de arrancar
```

El servidor expone:
- `http://<IP>:8080` — Web UI (interfaz FPV para móvil)
- `ws://<IP>:8080/ws` — WebSocket de telemetría
- `http://<IP>:8889/cam/whep` — Stream WebRTC (WHEP)

En modo FPV la IP es siempre `192.168.4.1` (red `PyCar` / `pycar1234`).

### En Windows (estación de control de escritorio)

```bash
python imagen_comandos3.py
```

Requiere: joystick USB, Arduino en COM4 y webcam conectados.

### Diagnóstico de hardware

```bash
cd webrtc
sh test_hardware.sh   # Prueba serial, joystick, webcam, MediaMTX y puertos
```

## Arquitectura

El sistema tiene **dos modos de operación** para la Raspberry Pi:

### Modo LAN (`start_lan.sh`)
Para desarrollo: la RPi se conecta al router de casa y usa la IP asignada por DHCP. MediaMTX auto-detecta la IP para los ICE candidates de WebRTC (`mediamtx_lan.yml`).

### Modo FPV (`start_fpv.sh`)
La Raspberry Pi crea su propia red WiFi autónoma. Requiere haber corrido `setup_ap.sh` previamente. MediaMTX usa IP fija `192.168.4.1` (`mediamtx_fpv.yml`).

Ambos modos corren el mismo `server.py`; el script de arranque selecciona el yml correcto vía variable de entorno `MEDIAMTX_CFG`.

### Componentes de `server.py`
- **FastAPI** sirve la web UI (`/`) y el endpoint WebSocket (`/ws`)
- **Pygame** (en hilo separado) lee el joystick USB conectado a la RPi
- **MediaMTX** (subprocess) captura `/dev/video0` vía ffmpeg y convierte RTSP → WebRTC
- El servidor transmite comandos seriales al Arduino (`/dev/ttyUSB0`) y hace broadcast de telemetría JSON por WebSocket

### Modo escritorio (`imagen_comandos3.py`)
Control local donde la PC Windows actúa como estación de control:
- Pygame lee el joystick USB y dibuja el HUD con OpenCV
- Envía comandos directamente al Arduino vía serial (COM4, 115200 baud)

### Protocolo serial (Arduino)
- Ejes: `"Q<valor> G<valor>"` — steering (eje 4) y gas (eje 3)
- Botones: `"R"` (botón 10) y `"E"` (botón 5)
- Deadzone: 0.05 (5%), intervalo de envío: 100ms

### Web UI (`webrtc/static/index.html`)
Interfaz para móvil en modo landscape:
- Video WebRTC a pantalla completa
- HUD con historial TX/RX, indicadores de estado (VIDEO, LINK, SERIAL, JOY) y barras de steering/throttle en tiempo real

## Constantes clave de configuración

| Constante | Valor | Archivo |
|-----------|-------|---------|
| `SERIAL_PORT` | `/dev/ttyUSB0` | `server.py` |
| `WEB_PORT` | `8080` | `server.py` |
| `EJE_Q` (steering) | `4` | `server.py` |
| `EJE_G` (gas) | `3` | `server.py` |
| `BOTON_R` | `10` | `server.py` |
| `BOTON_E` | `5` | `server.py` |
| `DEADZONE` | `0.05` | `server.py` |
| AP SSID / Password | `PyCar` / `pycar1234` | `setup_ap.sh` |
| IP modo FPV | `192.168.4.1` | `setup_ap.sh` / `mediamtx_fpv.yml` |
| Serial baud rate (Windows) | `115200`, `COM4` | `imagen_comandos3.py` |

## MediaMTX

Dos configuraciones separadas:
- `mediamtx_lan.yml` — sin IP fija, auto-detecta la interfaz de red
- `mediamtx_fpv.yml` — IP fija `192.168.4.1` para ICE candidates WebRTC

Ambas capturan video con ffmpeg usando encoder hardware `h264_v4l2m2m` (RPi4); comentado el fallback a software `libx264`.
RTSP interno en puerto 8554, WebRTC en puerto 8889.
