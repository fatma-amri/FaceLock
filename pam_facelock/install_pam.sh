#!/bin/bash
# FaceLock PAM Module Installation Script for Ubuntu/Linux
# Run with: sudo bash install_pam.sh

set -e

echo "========================================"
echo "FaceLock PAM Module Installer"
echo "========================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Check for required dependencies
echo "[1/7] Checking dependencies..."
if ! command -v gcc &> /dev/null; then
    echo "Error: gcc not found. Install with: sudo apt-get install build-essential"
    exit 1
fi

if ! dpkg -l | grep -q "libpam0g-dev"; then
    echo "Error: libpam0g-dev not found. Install with: sudo apt-get install libpam0g-dev"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Install with: sudo apt-get install python3"
    exit 1
fi

echo "✓ All dependencies found"
echo ""

# Get installation directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARENT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Compile PAM module
echo "[2/7] Compiling PAM module..."
gcc -fPIC -fno-stack-protector -c "$SCRIPT_DIR/pam_facelock.c" -o /tmp/pam_facelock.o
gcc -shared -o /tmp/pam_facelock.so /tmp/pam_facelock.o -lpam

if [ $? -eq 0 ]; then
    echo "✓ Compilation successful"
else
    echo "Error: Compilation failed"
    exit 1
fi
echo ""

# Install PAM module
echo "[3/7] Installing PAM module..."
cp /tmp/pam_facelock.so /lib/x86_64-linux-gnu/security/ || \
    cp /tmp/pam_facelock.so /lib/$(arch)-linux-gnu/security/

if [ -f /lib/x86_64-linux-gnu/security/pam_facelock.so ]; then
    echo "✓ PAM module installed to /lib/x86_64-linux-gnu/security/"
elif [ -f /lib/$(arch)-linux-gnu/security/pam_facelock.so ]; then
    echo "✓ PAM module installed to /lib/$(arch)-linux-gnu/security/"
else
    echo "Error: Failed to install PAM module"
    exit 1
fi
echo ""

# Create config directory
echo "[4/7] Creating configuration directory..."
mkdir -p /etc/facelock
cp "$PARENT_DIR/enrollment_ui.py" /usr/local/bin/facelock-enroll
chmod +x /usr/local/bin/facelock-enroll
echo "✓ Config directory created"
echo ""

# Install daemon script
echo "[5/7] Installing daemon..."
cp "$SCRIPT_DIR/facelock_daemon.py" /usr/local/bin/facelock_daemon
chmod +x /usr/local/bin/facelock_daemon

# Create symlink to parent FaceLock directory
ln -sf "$PARENT_DIR" /etc/facelock/source || true

echo "✓ Daemon installed to /usr/local/bin/"
echo ""

# Install systemd service
echo "[6/7] Installing systemd service..."
cp "$SCRIPT_DIR/facelock.service" /etc/systemd/system/

systemctl daemon-reload

# Don't auto-start yet
echo "✓ Service file installed"
echo ""

# Configure PAM
echo "[7/7] Configuring PAM..."

# Backup original
cp /etc/pam.d/common-auth /etc/pam.d/common-auth.bak

# Check if already added
if ! grep -q "pam_facelock" /etc/pam.d/common-auth; then
    # Add as 'sufficient' (success skips password, failure continues)
    sed -i '1i auth sufficient pam_facelock.so' /etc/pam.d/common-auth
    echo "✓ Added to /etc/pam.d/common-auth"
else
    echo "✓ Already configured in /etc/pam.d/common-auth"
fi
echo ""

echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Enroll your face:"
echo "   facelock-enroll"
echo ""
echo "2. Start the daemon:"
echo "   sudo systemctl start facelock"
echo ""
echo "3. Enable auto-start:"
echo "   sudo systemctl enable facelock"
echo ""
echo "4. Check status:"
echo "   sudo systemctl status facelock"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u facelock -f"
echo ""
