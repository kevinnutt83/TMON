# /workspaces/TMON/scripts/tmon-pi-installer.sh
#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# TMON Pi Zero environment installer
# Run as a normal user with sudo privileges:
#   chmod +x ./tmon-pi-installer.sh
#   ./tmon-pi-installer.sh

RUN_USER="$(id -un)"
HOME_DIR="${HOME:-/home/$RUN_USER}"

TMON_DIR="$HOME_DIR/tmon"
FIRMWARE_DIR="$TMON_DIR/firmware"
VENV_DIR="$FIRMWARE_DIR/.venv"

REPO_HTTP="https://github.com/kevinnutt83/TMON"

if [ "$(id -u)" -eq 0 ]; then
  echo "Error: do not run as root. Run as user '$RUN_USER' with sudo privileges." >&2
  exit 1
fi

echo "Running installation as user: $RUN_USER"
echo "Firmware dir: $FIRMWARE_DIR"

# ---- 1) OS packages (safe; no system pip) ----
sudo apt-get update
sudo apt-get -y upgrade

sudo apt-get install -y \
  ca-certificates curl wget \
  git subversion \
  python3 python3-venv python3-pip python3-dev build-essential \
  libffi-dev libssl-dev \
  libi2c-dev i2c-tools \
  libgpiod-dev python3-libgpiod \
  raspi-config

# Helpful hardware/python packages (avoid building on Pi Zero where possible)
sudo apt-get install -y \
  python3-serial python3-requests python3-ujson \
  python3-spidev python3-rpi.gpio python3-smbus || true

# ---- 2) Enable interfaces (non-interactive) ----
# Enables: I2C, SPI, Serial HW, SSH, VNC
if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_i2c 0 || true
  sudo raspi-config nonint do_spi 0 || true
  sudo raspi-config nonint do_serial_hw 0 || true
  sudo raspi-config nonint do_ssh 0 || true
  sudo raspi-config nonint do_vnc 0 || true
else
  echo "Warning: raspi-config not found; skipping interface enable." >&2
fi

# Add user to common hardware groups (takes effect after re-login/reboot)
sudo usermod -aG i2c,spi,gpio,dialout "$RUN_USER" || true

# ---- 3) Fetch firmware (svn export if possible; fallback to git clone) ----
mkdir -p "$TMON_DIR"
mkdir -p "$FIRMWARE_DIR"

fetch_firmware() {
  echo "Fetching firmware from $REPO_HTTP ..."
  if command -v svn >/dev/null 2>&1; then
    if svn export --force "${REPO_HTTP}/trunk/micropython" "$FIRMWARE_DIR" >/tmp/tmon_svn.log 2>&1; then
      echo "Fetched micropython/ via svn export."
      return 0
    fi
    echo "svn export failed; falling back to git (first lines):"
    sed -n '1,40p' /tmp/tmon_svn.log || true
  fi

  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' RETURN

  if ! git clone --depth 1 "$REPO_HTTP" "$tmpdir/tmon-repo" >/tmp/tmon_git.log 2>&1; then
    echo "ERROR: git clone failed. Repo private or network blocked." >&2
    sed -n '1,120p' /tmp/tmon_git.log || true
    return 1
  fi

  if [ ! -d "$tmpdir/tmon-repo/micropython" ]; then
    echo "ERROR: cloned repo but micropython/ directory missing." >&2
    return 1
  fi

  rm -rf "$FIRMWARE_DIR"
  mv "$tmpdir/tmon-repo/micropython" "$FIRMWARE_DIR"
  echo "Moved micropython/ to $FIRMWARE_DIR"
}

fetch_firmware

# ---- 4) Create venv and install ALL Python deps inside venv (no system pip) ----
python3 -m venv "$VENV_DIR"
VENV_PY="$VENV_DIR/bin/python"

# Always use venv python -m pip (never system pip)
"$VENV_PY" -m pip install --upgrade pip wheel

# Install required libs for the Pi runtime in the venv.
# --prefer-binary helps on ARM; if a wheel exists, it will use it.
"$VENV_PY" -m pip install --prefer-binary \
  aiofiles aiohttp future pyserial requests ujson \
  smbus2 spidev RPi.GPIO \
  adafruit-blinka \
  adafruit-circuitpython-bme280 adafruit-circuitpython-dht \
  adafruit-circuitpython-ssd1306 adafruit-circuitpython-sgp40 \
  adafruit-circuitpython-tsl2591 adafruit-circuitpython-ltr390 \
  mpu9250-jmdev sx126x

# ---- 5) systemd service using the venv interpreter ----
SERVICE_FILE="/etc/systemd/system/tmon.service"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=TMON Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$FIRMWARE_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV_DIR/bin/python $FIRMWARE_DIR/main.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tmon.service
sudo systemctl restart tmon.service || true

echo
echo "Install finished."
echo "Service status: sudo systemctl status tmon.service"
echo "Logs:          sudo journalctl -u tmon.service -n 200 --no-pager"
echo "Rebooting now to apply interface/group changes..."
sudo reboot