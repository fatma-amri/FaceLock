# FaceLock Ubuntu/Linux PAM Module

## Overview

This directory contains the Linux/Ubuntu PAM (Pluggable Authentication Modules) integration for FaceLock, enabling facial recognition authentication for login screens.

## Components

1. **pam_facelock.c** - PAM module (C) - provides authentication to the login system
2. **facelock_daemon.py** - Background daemon that handles actual face recognition
3. **facelock.service** - systemd service file for daemon management
4. **install_pam.sh** - Installation script

## Architecture

```
Login Screen (GNOME, KDE, LightDM, etc.)
    ↓
PAM Stack (/etc/pam.d/common-auth)
    ↓
pam_facelock.so [C - connects via Unix socket]
    ↓ (Unix Domain Socket: /tmp/facelock_daemon.sock)
facelock_daemon.py [Python - runs as system service]
    ↓
Python AI Pipeline [existing modules]
    ↓
AUTH_SUCCESS:<username> or AUTH_FAILED
    ↓
PAM allows/denies login
```

## Installation

### Prerequisites

```bash
# Update package list
sudo apt-get update

# Install required packages
sudo apt-get install -y \
    build-essential \
    libpam0g-dev \
    python3 \
    python3-pip

# Install Python dependencies
pip3 install -r requirements.txt
```

### Install PAM Module

```bash
# Navigate to pam_facelock directory
cd pam_facelock

# Run installer (requires sudo)
sudo bash install_pam.sh
```

The installer will:
1. Compile the C PAM module
2. Install it to `/lib/x86_64-linux-gnu/security/`
3. Create configuration directories
4. Install the daemon script
5. Install the systemd service
6. Configure PAM to use the module

## Usage

### 1. Enroll Faces

```bash
# Run the enrollment UI (same as Windows)
facelock-enroll

# Or with Python directly
python3 enrollment_ui.py
```

### 2. Start the Daemon

```bash
# Start manually
sudo systemctl start facelock

# Enable auto-start on boot
sudo systemctl enable facelock

# Check status
sudo systemctl status facelock

# View logs
sudo journalctl -u facelock -f
```

### 3. Test Authentication

```bash
# Option 1: Via login screen
# Lock your screen and attempt login with face recognition

# Option 2: Via su command
su <username>
# Will show face recognition prompt

# Option 3: Via sudo
sudo su
# Will show face recognition prompt
```

## Files

| File | Purpose | Location |
|------|---------|----------|
| pam_facelock.c | PAM module source | `/lib/x86_64-linux-gnu/security/pam_facelock.so` |
| facelock_daemon.py | Background service | `/usr/local/bin/facelock_daemon` |
| facelock.service | systemd unit file | `/etc/systemd/system/facelock.service` |
| common-auth config | PAM configuration | `/etc/pam.d/common-auth` |
| Database | Face encodings | `/etc/facelock/facelock.db` |

## Configuration

### PAM Configuration

The module is configured as **"sufficient"** in `/etc/pam.d/common-auth`:

```
auth sufficient pam_facelock.so
auth required pam_unix.so nullok try_first_pass yescrypt
```

This means:
- If face recognition succeeds → login allowed (password skipped)
- If face recognition fails → fall back to password
- If daemon unavailable → fall back to password

### Daemon Configuration

Edit `/etc/systemd/system/facelock.service` to customize:
- Which user runs the daemon (default: root)
- Socket path
- Log location
- Restart policy

## Troubleshooting

### Daemon Won't Start

```bash
# Check systemd logs
sudo journalctl -xe

# Check if database exists
ls -la /etc/facelock/facelock.db

# Verify daemon can be run manually
/usr/local/bin/facelock_daemon --foreground
```

### Face Recognition Not Working

```bash
# Check daemon status
sudo systemctl status facelock

# Check socket exists
ls -la /tmp/facelock_daemon.sock

# View daemon logs
sudo journalctl -u facelock -n 50

# Test manually
python3 facelock_daemon.py --foreground
```

### PAM Module Not Loading

```bash
# Check if module file exists
ls -la /lib/x86_64-linux-gnu/security/pam_facelock.so

# Check PAM configuration
grep facelock /etc/pam.d/common-auth

# Verify it's not 32-bit on 64-bit system
file /lib/x86_64-linux-gnu/security/pam_facelock.so
```

### Camera Not Accessible

```bash
# Check camera permissions
ls -la /dev/video*

# Add user to video group
sudo usermod -a -G video $USER

# Restart (may need to log out/in)
```

## Security Considerations

1. **Daemon Privileges**: Runs as root (required for PAM integration)
2. **Socket Permissions**: Unix socket at `/tmp/facelock_daemon.sock` readable by all users
3. **Database**: Encrypted with Fernet (same as Windows version)
4. **Fallback**: Always allows password authentication if face recognition unavailable
5. **Logging**: All authentication attempts logged to syslog

## Uninstallation

```bash
# Stop the service
sudo systemctl stop facelock
sudo systemctl disable facelock

# Remove PAM configuration
sudo sed -i '/pam_facelock/d' /etc/pam.d/common-auth

# Remove files
sudo rm /lib/x86_64-linux-gnu/security/pam_facelock.so
sudo rm /usr/local/bin/facelock_daemon
sudo rm /usr/local/bin/facelock-enroll
sudo rm /etc/systemd/system/facelock.service
sudo systemctl daemon-reload

# Remove config directory (optional)
sudo rm -rf /etc/facelock
```

## Advanced Configuration

### Use with GDM (GNOME Display Manager)

```bash
# Edit GDM PAM config
sudo nano /etc/pam.d/gdm-password

# Add the same line as above
auth sufficient pam_facelock.so
```

### Use with LightDM

```bash
# Edit LightDM PAM config
sudo nano /etc/pam.d/lightdm

# Add face authentication
auth sufficient pam_facelock.so
```

### Use with KDM (KDE Display Manager)

```bash
# Edit KDM PAM config
sudo nano /etc/pam.d/kde

# Add face authentication
auth sufficient pam_facelock.so
```

### Enable Detailed Logging

Edit `/etc/systemd/system/facelock.service`:
```ini
[Service]
# Add this line for debug logs
Environment="FACELOCK_DEBUG=1"
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart facelock
```

## Performance Notes

- First authentication may take 10-15 seconds (face detection + encoding)
- Subsequent attempts are faster (cached face detection)
- Daemon maintains connection to camera
- Timeout: 15 seconds max per authentication attempt
- Falls back to password if timeout exceeded

## Supported Distributions

- Ubuntu 18.04 LTS and later
- Debian 9 and later
- Linux Mint 19 and later
- Elementary OS 5.0+
- Pop!_OS 20.04+

## Support

For issues:
1. Check logs: `sudo journalctl -u facelock -f`
2. Run in foreground: `/usr/local/bin/facelock_daemon --foreground`
3. Verify database: `ls -la /etc/facelock/facelock.db`
4. Test PAM: `pamtester -v <user> su authenticate`
