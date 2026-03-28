#!/usr/bin/env bash
# verify_setup.sh - Linux-side verification for WSL2 + Ubuntu + WSLg setup
#
# Can be called standalone or from verify_setup.ps1.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"

PASSED=0
FAILED=0
WARNINGS=0

pass() {
    echo -e "  \033[32m[PASS]\033[0m $1"
    ((PASSED++))
}

fail() {
    echo -e "  \033[31m[FAIL]\033[0m $1"
    ((FAILED++))
}

warn() {
    echo -e "  \033[33m[WARN]\033[0m $1"
    ((WARNINGS++))
}

# Parse config
parse_config() {
    python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
$1
"
}

# ---------- systemd ----------
echo "  Systemd:"
if [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]; then
    pass "systemd is PID 1"
else
    fail "systemd is not PID 1 (init system: $(ps -p 1 -o comm= 2>/dev/null))"
fi

# Check snapd
if systemctl is-active snapd &>/dev/null; then
    pass "snapd service is running"
else
    fail "snapd service is not running"
fi

# ---------- apt packages ----------
echo ""
echo "  Apt packages:"

apt_packages=$(parse_config "
for pkg in config.get('aptPackages', []):
    print(pkg)
")

while IFS= read -r pkg; do
    [ -z "$pkg" ] && continue
    if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        pass "$pkg installed"
    else
        fail "$pkg not installed"
    fi
done <<< "$apt_packages"

# ---------- snap packages ----------
echo ""
echo "  Snap packages:"

snap_names=$(parse_config "
for s in config.get('snaps', []):
    print(s['name'])
")

while IFS= read -r snap_name; do
    [ -z "$snap_name" ] && continue
    if snap list "$snap_name" &>/dev/null; then
        pass "$snap_name installed"
    else
        fail "$snap_name not installed"
    fi
done <<< "$snap_names"

# ---------- WSLg ----------
echo ""
echo "  WSLg:"

if [ -n "${DISPLAY:-}" ]; then
    pass "DISPLAY is set ($DISPLAY)"
else
    fail "DISPLAY is not set"
fi

if [ -d "/mnt/wslg" ]; then
    pass "/mnt/wslg directory exists"
else
    fail "/mnt/wslg not found"
fi

# ---------- V: drive mount ----------
echo ""
echo "  Storage:"

drive_letter=$(parse_config "print(config.get('wslDriveLetter', 'V').lower())")
if [ -d "/mnt/$drive_letter" ]; then
    pass "/mnt/$drive_letter is mounted"
else
    warn "/mnt/$drive_letter not found (drive may not be connected)"
fi

# ---------- Summary ----------
echo ""
echo -e "  \033[36mLinux results: $PASSED passed, $FAILED failed, $WARNINGS warnings\033[0m"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
exit 0
