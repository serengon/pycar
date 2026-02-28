#!/bin/bash
# ============================================
# Desactiva el Access Point y restaura WiFi normal
# Ejecutar: sudo ./disable_ap.sh && sudo reboot
# ============================================

set -e

echo "=== Desactivando Access Point ==="

systemctl disable hostapd
systemctl disable dnsmasq
systemctl stop hostapd
systemctl stop dnsmasq

if [ -f /etc/dhcpcd.conf.backup ]; then
    cp /etc/dhcpcd.conf.backup /etc/dhcpcd.conf
    echo "  ✓ dhcpcd.conf restaurado"
fi

if [ -f /etc/dnsmasq.conf.backup ]; then
    cp /etc/dnsmasq.conf.backup /etc/dnsmasq.conf
    echo "  ✓ dnsmasq.conf restaurado"
fi

echo ""
echo "  AP desactivado. Reiniciar para volver a WiFi normal:"
echo "    sudo reboot"
