# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Proyecto

**PyCar** es un sistema de control remoto para un vehículo RC basado en Raspberry Pi. Combina streaming FPV vía WebRTC, control por joystick USB y comunicación serial con un Arduino.

## Cómo ejecutar

### En Raspberry Pi (servidor)

```bash
# Configuración inicial (una sola vez)
sudo ./webrtc/setup_base.sh      # Instala dependencias y MediaMTX
sudo ./webrtc/setup_ap.sh        # Configura la RPi como Access Point WiFi
sudo reboot                      # Activa el AP

# Iniciar el servidor
cd webrtc
./start.sh                       # Equivale a: python3 server.py
```

El servidor expone:
- `http://192.168.4.1:8080` — Web UI (interfaz FPV para móvil)
- `ws://192.168.4.1:8080/ws` — WebSocket de telemetría
- `http://192.168.4.1:8889/cam/whep` — Stream WebRTC (WHEP)

### En Windows (estación de control de escritorio)

```bash
python imagen_comandos3.py
```

Requiere: joystick USB, Arduino en COM4 y webcam conectados.

### Instalar dependencias Python (Raspberry Pi)

```bash
pip install -r webrtc/requirements.txt
```

## Arquitectura

El sistema tiene **dos modos de operación** independientes:

### 1. Modo escritorio (`imagen_comandos3.py`)
Control local donde la PC actúa como estación de control:
- Pygame lee el joystick USB y dibuja el HUD con OpenCV
- Envía comandos directamente al Arduino vía serial (COM4, 115200 baud)
- Muestra historial TX/RX, estado de conexiones y FPS en tiempo real

### 2. Modo remoto (`webrtc/server.py` en RPi)
La Raspberry Pi funciona como AP WiFi autónomo (`PyCar` / `pycar1234`):
- **FastAPI** sirve la web UI y el endpoint WebSocket `/ws`
- **Pygame** (en hilo separado) lee el joystick USB conectado a la RPi
- **MediaMTX** captura `/dev/video0` vía ffmpeg y convierte RTSP → WebRTC
- El servidor transmite comandos seriales al Arduino (`/dev/ttyUSB0`) y hace broadcast de telemetría JSON por WebSocket a los clientes móviles

### Protocolo serial (Arduino)
Formato de comandos enviados:
- Ejes: `"Q<valor> G<valor>"` — steering (eje 3) y gas (eje 2)
- Botones: `"R"` (botón 9) y `"E"` (botón 5)
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
| `EJE_Q` (steering) | `3` | `server.py` |
| `EJE_G` (gas) | `2` | `server.py` |
| `BOTON_R` | `9` | `server.py` |
| `BOTON_E` | `5` | `server.py` |
| `DEADZONE` | `0.05` | `server.py` |
| AP SSID / Password | `PyCar` / `pycar1234` | `setup_ap.sh` |
| IP Raspberry Pi | `192.168.4.1` | `setup_ap.sh` / `mediamtx.yml` |
| Serial baud rate (Windows) | `115200`, `COM4` | `imagen_comandos3.py` |

## MediaMTX

El archivo `webrtc/mediamtx.yml` configura el servidor de streaming:
- Captura video con ffmpeg usando encoder hardware `h264_v4l2m2m` (RPi4); si falla, cae a software
- RTSP interno en puerto 8554, WebRTC en puerto 8889
- IP fija `192.168.4.1` para ICE candidates de WebRTC
