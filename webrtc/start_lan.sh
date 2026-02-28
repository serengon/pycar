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

# Generar config de MediaMTX con la IP real de la red
TMP_CFG="/tmp/mediamtx_lan_runtime.yml"
cp mediamtx_lan.yml "$TMP_CFG"
echo "" >> "$TMP_CFG"
echo "webrtcIPAddresses:" >> "$TMP_CFG"
echo "  - ${IP}" >> "$TMP_CFG"

. venv/bin/activate
export MEDIAMTX_CFG="$TMP_CFG"
python3 server.py
