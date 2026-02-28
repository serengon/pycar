#!/bin/bash
# ============================================
# PyCar - Modo FPV (AP propio, sin router)
# Requiere haber corrido setup_ap.sh antes
# Ejecutar: ./start_fpv.sh
# ============================================

cd "$(dirname "$0")"

# Verificar que el AP está activo
if ! ip addr show wlan0 | grep -q "192.168.4.1"; then
    echo "⚠  El AP no está activo en wlan0"
    echo "   Ejecutar primero: sudo ./setup_ap.sh && sudo reboot"
    exit 1
fi

echo "🚗 Iniciando PyCar - Modo FPV"
echo "   WiFi:  PyCar / pycar1234"
echo "   Web:   http://192.168.4.1:8080"
echo "   Video: http://192.168.4.1:8889/cam/whep"
echo ""

. venv/bin/activate
export MEDIAMTX_CFG="$(pwd)/mediamtx_fpv.yml"
python3 server.py
