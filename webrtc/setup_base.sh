#!/bin/bash
# ============================================
# Setup base PyCar WebRTC
# Ejecutar: sudo ./setup_base.sh
# ============================================

set -e

echo "=== PyCar WebRTC - Setup Base ==="

# 1. Dependencias
echo "[1/3] Instalando dependencias del sistema..."
apt update
apt install -y ffmpeg python3-pip v4l-utils python3-pygame

# 2. Dependencias Python (venv para evitar conflictos con el sistema)
echo "[2/3] Instalando dependencias Python..."
apt install -y python3-venv
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install --upgrade pip -q
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 3. MediaMTX
echo "[3/3] Instalando MediaMTX..."
MEDIAMTX_VERSION="v1.11.3"

ARCH=$(dpkg --print-architecture)
case $ARCH in
    arm64|aarch64) ARCH="arm64v8" ;;
    armhf)         ARCH="armv7" ;;
    *)             echo "Arquitectura no soportada: $ARCH"; exit 1 ;;
esac

cd /opt
wget -q "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_linux_${ARCH}.tar.gz" -O mediamtx.tar.gz
tar xzf mediamtx.tar.gz mediamtx
rm mediamtx.tar.gz
chmod +x /opt/mediamtx
echo "  ✓ MediaMTX instalado"

# Verificar hardware
echo ""
echo "=== Hardware detectado ==="
echo "  Webcam:"
v4l2-ctl --list-devices 2>/dev/null || echo "    ⚠ No detectada"
echo "  Serial (Arduino):"
SERIAL=$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null)
if [ -n "$SERIAL" ]; then echo "$SERIAL"; else echo "    ⚠ No detectado"; fi
echo "  Joystick:"
ls /dev/input/js* 2>/dev/null || echo "    ⚠ No detectado"

echo ""
echo "=== Setup base completo ==="
echo ""
echo "  Para arrancar en modo LAN (desarrollo):"
echo "    sh webrtc/start_lan.sh"
echo ""
echo "  Para arrancar en modo FPV (AP propio):"
echo "    sudo ./webrtc/setup_ap.sh && sudo reboot"
echo "    sh webrtc/start_fpv.sh"
