#!/usr/bin/env bash
# setup_ubuntu.sh - Linux-side WSL2 setup
#
# Usage:
#   bash setup_ubuntu.sh --phase 1   # Enable systemd (requires WSL restart after)
#   bash setup_ubuntu.sh --phase 2   # Install packages and verify WSLg
#   bash setup_ubuntu.sh             # Run both phases (assumes systemd already active or not needed yet)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"

# ---------- Helpers ----------

log_step() {
    local step="$1"
    local total="$2"
    local msg="$3"
    echo -e "\n\033[36m[$step/$total] $msg\033[0m"
}

log_ok() {
    echo -e "  \033[32m$1\033[0m"
}

log_warn() {
    echo -e "  \033[33m$1\033[0m"
}

log_error() {
    echo -e "  \033[31m[ERROR] $1\033[0m"
}

# Parse config.json using python3 (guaranteed in Ubuntu 22.04)
parse_config() {
    python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    config = json.load(f)
$1
"
}

# ---------- Phase 1: Enable systemd ----------

phase1() {
    log_step 1 1 "Enabling systemd..."

    if grep -q "systemd=true" /etc/wsl.conf 2>/dev/null; then
        log_ok "systemd is already enabled in /etc/wsl.conf."
    else
        # Check if [boot] section exists
        if grep -q "\[boot\]" /etc/wsl.conf 2>/dev/null; then
            # Add systemd=true under existing [boot] section
            sudo sed -i '/\[boot\]/a systemd=true' /etc/wsl.conf
        else
            # Append [boot] section
            echo "" | sudo tee -a /etc/wsl.conf > /dev/null
            echo "[boot]" | sudo tee -a /etc/wsl.conf > /dev/null
            echo "systemd=true" | sudo tee -a /etc/wsl.conf > /dev/null
        fi
        log_ok "systemd enabled in /etc/wsl.conf."
        log_warn "WSL restart required for systemd to take effect."
    fi
}

# ---------- Phase 2: Install packages and verify WSLg ----------

phase2() {
    local total=4

    # --- Step 1: apt update/upgrade ---
    log_step 1 $total "Updating apt packages..."
    sudo apt update -y
    sudo apt upgrade -y
    log_ok "apt packages updated."

    # --- Step 2: Install apt packages ---
    log_step 2 $total "Installing apt packages..."

    local apt_packages
    apt_packages=$(parse_config "
for pkg in config.get('aptPackages', []):
    print(pkg)
")

    while IFS= read -r pkg; do
        [ -z "$pkg" ] && continue
        if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            log_ok "$pkg is already installed."
        else
            echo "  Installing $pkg..."
            sudo apt install -y "$pkg"
            log_ok "$pkg installed."
        fi
    done <<< "$apt_packages"

    # --- Step 3: Install snaps ---
    log_step 3 $total "Installing snap packages..."

    # Verify systemd is running (required for snap)
    if ! systemctl is-system-running &>/dev/null; then
        log_error "systemd is not running. Snaps require systemd."
        log_error "Please ensure phase 1 ran and WSL was restarted."
        exit 1
    fi

    # Ensure snapd is installed and running
    if ! command -v snap &>/dev/null; then
        echo "  Installing snapd..."
        sudo apt install -y snapd
    fi
    sudo systemctl enable --now snapd.socket 2>/dev/null || true
    sudo systemctl enable --now snapd 2>/dev/null || true

    # Wait for snapd to be ready
    if ! sudo snap wait system seed.loaded 2>/dev/null; then
        log_warn "Waiting for snapd to initialize..."
        sleep 5
    fi

    local snap_data
    snap_data=$(parse_config "
for s in config.get('snaps', []):
    classic = '--classic' if s.get('classic', False) else ''
    print(f\"{s['name']} {classic}\")
")

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local snap_name snap_flags
        snap_name=$(echo "$line" | awk '{print $1}')
        snap_flags=$(echo "$line" | awk '{$1=""; print $0}' | xargs)

        if snap list "$snap_name" &>/dev/null; then
            log_ok "$snap_name is already installed."
        else
            echo "  Installing snap: $snap_name $snap_flags..."
            sudo snap install $snap_flags "$snap_name"
            log_ok "$snap_name installed."
        fi
    done <<< "$snap_data"

    # --- Step 4: Verify WSLg ---
    log_step 4 $total "Verifying WSLg..."

    local wslg_ok=true

    if [ -n "${DISPLAY:-}" ]; then
        log_ok "DISPLAY is set: $DISPLAY"
    else
        log_warn "DISPLAY is not set. WSLg may not be active."
        wslg_ok=false
    fi

    if [ -d "/mnt/wslg" ]; then
        log_ok "/mnt/wslg directory exists."
    else
        log_warn "/mnt/wslg not found. WSLg may not be available."
        wslg_ok=false
    fi

    # Test with xeyes if available
    if command -v xeyes &>/dev/null; then
        xeyes &
        local xeyes_pid=$!
        sleep 2
        if kill -0 $xeyes_pid 2>/dev/null; then
            log_ok "xeyes launched successfully - WSLg is working!"
            kill $xeyes_pid 2>/dev/null || true
        else
            log_warn "xeyes failed to stay running."
            wslg_ok=false
        fi
    else
        log_warn "xeyes not found. Install x11-apps to test WSLg."
    fi

    if $wslg_ok; then
        log_ok "WSLg verification passed."
    else
        log_warn "Some WSLg checks failed. See above for details."
        log_warn "Ensure your Windows GPU drivers are up to date."
    fi

    # --- Summary ---
    echo ""
    echo -e "\033[32m========================================\033[0m"
    echo -e "\033[32m  Linux-side setup complete!\033[0m"
    echo -e "\033[32m========================================\033[0m"
    echo ""
    echo "  Installed apt packages:"
    while IFS= read -r pkg; do
        [ -z "$pkg" ] && continue
        echo "    - $pkg"
    done <<< "$apt_packages"
    echo ""
    echo "  Installed snaps:"
    while IFS= read -r line; do
        [ -z "$line" ] && continue
        echo "    - $(echo "$line" | awk '{print $1}')"
    done <<< "$snap_data"
    echo ""
    echo "  Try launching an app:"
    echo "    code &"
    echo "    nautilus &"
    echo ""
}

# ---------- Main ----------

case "${1:-}" in
    --phase)
        case "${2:-}" in
            1) phase1 ;;
            2) phase2 ;;
            *)
                echo "Usage: $0 --phase [1|2]"
                exit 1
                ;;
        esac
        ;;
    *)
        phase1
        phase2
        ;;
esac
