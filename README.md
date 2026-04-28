# FaceLock 🔒

FaceLock is an advanced biometric security system that uses real-time facial recognition to continuously authenticate the user. It automatically locks your computer session (macOS / Windows) when you step away from the screen or if an unauthorized person takes your place.

**Privacy by Design:** All biometric data and processing are handled strictly locally. No images or face encodings are ever sent to the cloud.

## ✨ Key Features

- **Continuous Authentication:** Monitors the webcam feed in real-time to ensure the authorized user is present.
- **Auto-Lock (Zero-Trust):** Instantly locks the OS session (using system native commands) if the user is missing or unrecognized.
- **Enrollment Interface:** A simple and intuitive GUI (Tkinter) to register authorized users.
- **Low-Light Resilience:** Includes an automatic brightness correction algorithm using the LAB color space for better detection in low-lit environments.
- **Thread-Safe Architecture:** Sturdy multithreaded backend to ensure camera resources and UI never deadlock.

## 📂 Project Structure

```text
FaceLock/
├── main.py                   # Main daemon: runs the background continuous authentication.
├── enrollment_ui.py          # User interface to securely register a new face.
├── models/                   # Directory containing necessary ML weights/models.
├── modules/                  # Core operational components
│   ├── camera_handler.py     # Thread-safe OpenCV webcam capture and image processing.
│   ├── database.py           # Local persistence for user data and biometric encodings.
│   ├── face_detector.py      # Extracts faces from the webcam feed.
│   ├── face_encoder.py       # Converts face bounding boxes into mathematical encodings.
│   ├── face_authenticator.py # Compares real-time encodings against the local database.
│   └── system_controller.py  # Interfaces with the OS to lock the screen.
└── README.md                 # This documentation file.
```

## 🛠️ Prerequisites

- **Python 3.10+**
- A working integrated or external webcam.
- **macOS** or **Windows 10/11** environment.

## 🚀 Installation & Setup

### Step 1 — Build C# Service (10 min)
1. Open Visual Studio 2022
2. Open: `FaceRecognitionService/FaceRecognitionService.sln`
3. Top bar: Select `Release | x64`
4. Build → Build Solution
5. Check: `FaceRecognitionService/bin/Release/net6.0-windows/FaceRecognitionService.exe` exists

### Step 2 — Build C++ DLL (10 min)
1. Open Visual Studio 2022
2. Open: `CredentialProvider/CredentialProvider.sln`
3. Top bar: Select `Release | x64`
4. Build → Build Solution
5. Check: `CredentialProvider/bin/Release/x64/CredentialProvider.dll` exists

### Step 3 — Install Everything (5 min)
Open PowerShell as Administrator and run:
```powershell
powershell -ExecutionPolicy Bypass -File Installer/install.ps1
```

### Step 4 — Enroll Your Face (2 min)
```bash
python enrollment_ui.py
```
Follow the on-screen prompts to capture and save your biometric profile.

### Step 5 — Test
1. Press `Win+L` to lock screen
2. You should see **"Sign in with Face"** tile
3. Click it
4. Look at camera
5. Windows unlocks ✅

## 🏃‍♂️ Usage

Once installed, FaceLock runs automatically:

1. **Auto-starts on login**: The FaceRecognitionService.exe runs as a Windows service
2. **Continuous authentication**: Monitors your webcam in real-time
3. **Auto-lock**: If you leave the field of view for a timeout period, your session locks automatically

To start the service manually:
```powershell
net start FaceRecognitionService
```

To stop the service:
```powershell
net stop FaceRecognitionService
```

## 🔒 Security Notes
- Ensure your local `.venv` and `models/` folders are not accidentally pushed to your public Git repository (they are usually ignored via `.gitignore`).
- This system interacts with standard OS locking endpoints. It supplements rather than replaces your system's native password/biometric login.

---
*Maintained by the FaceLock dev team.*
