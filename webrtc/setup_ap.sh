#!/bin/bash
# ============================================
# Setup Access Point para PyCar
# Convierte la Raspi en AP WiFi propio
# Ejecutar: chmod +x setup_ap.sh && sudo ./setup_ap.sh
# REQUIERE: haber corrido setup_base.sh primero
# ============================================

set -e

echo "=== PyCar - Setup Access Point ==="

# 1. Instalar hostapd y dnsmasq
echo "[1/3] Instalando hostapd + dnsmasq..."
apt install -y hostapd dnsmasq

systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

# 2. IP estatica para wlan0
echo "[2/3] Configurando red..."

if [ ! -f /etc/dhcpcd.conf.backup ]; then
    cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup
    echo "  ✓ Backup de dhcpcd.conf creado"
fi

# Agregar config de IP estatica
grep -q "# PyCar AP" /etc/dhcpcd.conf || cat >> /etc/dhcpcd.conf <<'EOF'

# PyCar AP
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF

# hostapd (5GHz, 802.11ac)
cat > /etc/hostapd/hostapd.conf <<'EOF'
interface=wlan0
driver=nl80211
ssid=PyCar
hw_mode=a
channel=36
wmm_enabled=1
ieee80211n=1
ieee80211ac=1
ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40]
vht_capab=[SHORT-GI-80]
vht_oper_chwidth=1
vht_oper_centr_freq_seg0_idx=42
macaddr_acl=0
auth_algs=1
wpa=2
wpa_passphrase=pycar1234
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
country_code=AR
EOF

sed -i 's|^#DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd 2>/dev/null || true

# dnsmasq
if [ ! -f /etc/dnsmasq.conf.backup ]; then
    cp /etc/dnsmasq.conf /etc/dnsmasq.conf.backup
fi

cat > /etc/dnsmasq.conf <<'EOF'
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
domain=local
address=/pycar.local/192.168.4.1
EOF

# 3. Habilitar servicios
echo "[3/3] Habilitando servicios..."
rfkill unblock wlan
systemctl unmask hostapd
systemctl enable hostapd
systemctl enable dnsmasq

echo ""
echo "=== Access Point configurado ==="
echo ""
echo "  SSID:     PyCar"
echo "  Password: pycar1234"
echo "  IP Raspi: 192.168.4.1"
echo "  Banda:    5GHz (802.11ac)"
echo ""
echo "  REINICIAR para activar:"
echo "    sudo reboot"
echo ""
echo "  Despues del reboot:"
echo "    cd ~/pycar"
echo "    ./start.sh"
echo "    Desde el celu: http://192.168.4.1:8080"
echo ""
echo "  Para desactivar y volver a WiFi normal:"
echo "    sudo ./disable_ap.sh"
