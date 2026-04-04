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

1. **Clone the repository** (if not already done):
   ```bash
   git clone <repository_url>
   cd FaceLock
   ```

2. **Create a virtual environment** to isolate dependencies:
   ```bash
   python -m venv .venv
   
   # On macOS/Linux:
   source .venv/bin/activate
   # On Windows:
   .venv\Scripts\activate
   ```

3. **Install the dependencies**:
   Install the required libraries using the provided `requirements.txt` file.
   ```bash
   pip install -r requirements.txt
   ```

## 🏃‍♂️ Usage

1. **Enrollment (First Step)**  
   Before the app can recognize you, you must enroll your face.
   ```bash
   python enrollment_ui.py
   ```
   Follow the on-screen prompts to capture and save your biometric profile.

2. **Enable Protection**  
   Start the background daemon to secure your session.
   ```bash
   python main.py
   ```
   The script will monitor the camera feed. If you leave the field of view for a predefined timeout, the system will automatically lock.

## 🔒 Security Notes
- Ensure your local `.venv` and `models/` folders are not accidentally pushed to your public Git repository (they are usually ignored via `.gitignore`).
- This system interacts with standard OS locking endpoints. It supplements rather than replaces your system's native password/biometric login.

---
*Maintained by the FaceLock dev team.*
