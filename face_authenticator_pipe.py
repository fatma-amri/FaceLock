#!/usr/bin/env python
"""
face_authenticator_pipe.py
--------------------------
Persistent face authentication service for the FaceLock Windows Credential Provider.

The C# FaceRecognitionService starts this script ONCE at service startup.
Models are loaded at startup so AUTH_REQUEST is served quickly.
Camera is opened fresh per request and released immediately after.

stdin/stdout protocol:
  Startup output: READY                     (models loaded, ready to authenticate)
  Input:          AUTH_REQUEST              (one line per request)
  Input:          SHUTDOWN                  (graceful exit)
  Output:         AUTH_SUCCESS:<username>   (on match)
  Output:         AUTH_FAILED               (on no-match, error, or timeout)

All diagnostic messages go to stderr — stdout is only used for the protocol.
"""

import os
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'

import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from modules.face_authenticator import authenticate
from modules.face_detector import release_detector

# ---------------------------------------------------------------------------
# Logging (stderr only — stdout is the protocol channel)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("facelock.pipe")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_DB_PATH = str(Path(__file__).parent / "data" / "db" / "facelock.db")


# ---------------------------------------------------------------------------
# Model warm-up
# ---------------------------------------------------------------------------
def _warmup_models(db_path: str) -> None:
    """Force face-recognition model weights into memory via a dummy inference."""
    logger.warning("Warming up face recognition models...")
    try:
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        authenticate(dummy, db_path=db_path)
    except Exception as exc:
        # Expected: MTCNN finds no face in a black frame. Model is still loaded.
        logger.warning("Warmup inference done (expected no-face result: %s)", exc)
    logger.warning("Model warmup complete.")


# ---------------------------------------------------------------------------
# Per-request handler — camera opened fresh each request, released after
# ---------------------------------------------------------------------------
def _handle_auth_request(db_path: str) -> str:
    import os
    os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'
    import cv2
    from modules.face_authenticator import authenticate
    import datetime

    def log(msg):
        try:
            with open(r'C:\FaceLock_python_debug.txt', 'a') as f:
                f.write(f'[{datetime.datetime.now().strftime("%H:%M:%S.%f")}] {msg}\n')
        except Exception:
            pass

    for attempt in range(3):
        log(f'Attempt {attempt+1}: opening camera')
        cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        frame = None
        for i in range(10):
            ret, f = cap.read()
            log(f'  read {i}: ret={ret}')
            if ret:
                frame = f
                break
        cap.release()
        log(f'  camera released, frame={frame is not None}')

        if frame is None:
            continue

        result = authenticate(frame, db_path=db_path)
        log(f'  authenticate result: {result}')

        if result is not None:
            return f'AUTH_SUCCESS:{result}'

    return 'AUTH_FAILED'


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main() -> int:
    db_path = DEFAULT_DB_PATH

    # Pre-load model weights before signalling ready (camera opened per-request)
    _warmup_models(db_path)

    # Tell the C# service we are ready to accept requests
    print("READY", flush=True)

    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break

        if not line:          # EOF — parent closed stdin
            break

        cmd = line.strip()
        if cmd == "AUTH_REQUEST":
            result = _handle_auth_request(db_path)
            print(result, flush=True)
        elif cmd == "SHUTDOWN":
            break
        # Unknown commands are silently ignored

    # Graceful cleanup
    try:
        release_detector()
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
