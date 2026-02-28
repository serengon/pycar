#!/bin/bash
# ============================================
# PyCar - Modo LAN (conectado al router)
# Ejecutar: ./start_lan.sh
# ============================================

cd "$(dirname "$0")"

# Detectar IP actual en la red
IP=$(hostname -I | awk '{print $1}')

echo "🚗 Iniciando PyCar - Modo LAN"
echo "   Web:   http://${IP}:8080"
echo "   Video: http://${IP}:8889/cam/whep"
echo ""

. venv/bin/activate
export MEDIAMTX_CFG="$(pwd)/mediamtx_lan.yml"
python3 server.py
