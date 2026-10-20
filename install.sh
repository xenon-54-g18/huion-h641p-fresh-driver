#!/usr/bin/env bash
# huion-h641p-fresh-driver installer — idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HOME/.local/bin"
UNIT_DIR="$HOME/.config/systemd/user"

# 1. dependency (usersystem pkg, not the broken huion driver)
if ! python3 -c 'import evdev' 2>/dev/null; then
    echo "installing python3-evdev (sudo needed)"
    sudo apt install -y python3-evdev
fi

# 2. install script + unit
mkdir -p "$BIN" "$UNIT_DIR"
install -m 0755 "$SCRIPT_DIR/huion-fresh-driver.py" "$BIN/huion-fresh-driver.py"
install -m 0644 "$SCRIPT_DIR/huion-fresh-driver.service" "$UNIT_DIR/huion-fresh-driver.service"

# 3. make sure our own daemon can create uinput devices as the user
#    (independent of OpenTabletDriver/its rules)
mkdir -p "$HOME/.config/autostart"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"' \
    | sudo tee /etc/udev/rules.d/50-uinput-uaccess.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc

# 4. make sure the broken huion driver can never hijack the pen again
if [ ! -f "$HOME/.config/autostart/huiontablet.desktop" ]; then
    cat > "$HOME/.config/autostart/huiontablet.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=HuionTablet
Hidden=true
X-GNOME-Autostart-enabled=false
EOF
fi

systemctl --user daemon-reload
systemctl --user enable --now huion-fresh-driver.service
systemctl --user status huion-fresh-driver --no-pager -n 3 || true
