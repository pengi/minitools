#!/bin/sh
# Install perfctl for the current user. Usage: ./install.sh [--uninstall]
set -e

SRC=$(cd "$(dirname "$0")" && pwd)
SHARE="$HOME/.local/share/perfctl"
BIN="$HOME/.local/bin/perfctl"
AUTOSTART="$HOME/.config/autostart/perfctl.desktop"
TMPFILES=/etc/tmpfiles.d/perfctl.conf

pkill -f "$SHARE/perfctl.py tray" || true

if [ "$1" = "--uninstall" ]; then
    rm -rf "$SHARE" "$BIN" "$AUTOSTART"
    sudo rm -f "$TMPFILES"
    echo "perfctl uninstalled (boost file permissions reset at next reboot)"
    exit 0
fi

mkdir -p "$SHARE" "$(dirname "$BIN")" "$(dirname "$AUTOSTART")"
cp "$SRC/perfctl.py" "$SHARE/"
cp -r "$SRC/icons" "$SHARE/"
chmod +x "$SHARE/perfctl.py"
ln -sf "$SHARE/perfctl.py" "$BIN"

cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=perfctl
Comment=Fan boost and CPU frequency boost tray icon
Exec=$SHARE/perfctl.py tray
Icon=$SHARE/icons/perfctl-normal.svg
X-GNOME-Autostart-enabled=true
EOF

# Let the user's group write the CPU boost file, applied at every boot.
echo "z /sys/devices/system/cpu/cpufreq/boost 0664 root $(id -gn)" | sudo tee "$TMPFILES" >/dev/null
sudo systemd-tmpfiles --create "$TMPFILES"

nohup "$SHARE/perfctl.py" tray >/dev/null 2>&1 &
echo "perfctl installed and started"
