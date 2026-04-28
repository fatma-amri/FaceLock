#!/usr/bin/env python
"""
face_authenticator_pipe.py
--------------------------
Bridge between Windows Credential Provider and FaceLock Python AI pipeline.

This script is called by FaceRecognitionService.exe as a subprocess.
It captures one frame, runs authentication, and outputs result to stdout.

Behavior:
    - Reads one frame from webcam
    - Runs full face detection → encoding → authentication pipeline
    - Outputs AUTH_SUCCESS:<username> or AUTH_FAILED to stdout
    - Exits immediately (max 10 seconds total)

Used by:
    FaceRecognitionService.exe (C# Windows Service)
    pam_facelock (Ubuntu PAM module)

Exit codes:
    0 = Authentication successful (AUTH_SUCCESS printed to stdout)
    1 = Authentication failed (AUTH_FAILED printed to stdout)
    2 = No face detected
    3 = Database error
    4 = Timeout / camera error
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

# Add project root to path for module imports
sys.path.insert(0, str(Path(__file__).parent))

from modules.camera_handler import get_frame, release_camera
from modules.face_authenticator import authenticate
from modules.face_detector import release_detector

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

# Use minimal logging to avoid cluttering stdout (which is parsed by caller)
logging.basicConfig(
    level=logging.WARNING,
    format="[%(levelname)s] %(message)s",
    stream=sys.stderr,  # Log to stderr, not stdout
)
logger = logging.getLogger("facelock.pipe_authenticator")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum time allowed for entire authentication process
TIMEOUT_SECONDS: float = 10.0

# Database path (relative to project root)
DEFAULT_DB_PATH: str = str(Path(__file__).parent / "data" / "db" / "facelock.db")

# Exit codes
EXIT_SUCCESS = 0
EXIT_AUTH_FAILED = 1
EXIT_NO_FACE = 2
EXIT_DB_ERROR = 3
EXIT_TIMEOUT = 4


# ---------------------------------------------------------------------------
# Main Pipe Authenticator
# ---------------------------------------------------------------------------

def authenticate_pipe(
    db_path: str = DEFAULT_DB_PATH,
    timeout_s: float = TIMEOUT_SECONDS,
) -> int:
    """
    Single-shot authentication via pipe protocol.

    This function:
    1. Captures one frame from webcam
    2. Runs full face authentication pipeline
    3. Prints result to stdout (AUTH_SUCCESS:<name> or AUTH_FAILED)
    4. Returns appropriate exit code

    Parameters
    ----------
    db_path : str
        Path to the encrypted SQLite database.
    timeout_s : float
        Maximum time allowed for authentication (seconds).

    Returns
    -------
    int
        Exit code (0=success, 1=failed, 2=no_face, 3=db_error, 4=timeout)

    Output to stdout:
        AUTH_SUCCESS:<username>   (on successful authentication)
        AUTH_FAILED              (on failed authentication)

    Output to stderr:
        Diagnostic messages (only if verbosity is needed)
    """
    t_start = time.time()

    try:
        # ---- Step 1: Capture Frame ----
        logger.info("Capturing frame from webcam…")
        frame = get_frame(apply_brightness_correction=True)

        if frame is None:
            logger.error("Failed to capture frame from webcam.")
            print("AUTH_FAILED", file=sys.stdout, flush=True)
            return EXIT_NO_FACE

        # ---- Step 2: Authenticate ----
        logger.info("Running face authentication pipeline…")
        username: Optional[str] = authenticate(frame, db_path=db_path)

        # ---- Step 3: Output Result ----
        if username:
            print(f"AUTH_SUCCESS:{username}", file=sys.stdout, flush=True)
            logger.info(f"Authentication successful: {username}")
            return EXIT_SUCCESS
        else:
            print("AUTH_FAILED", file=sys.stdout, flush=True)
            logger.info("Authentication failed: no match within threshold")
            return EXIT_AUTH_FAILED

    except FileNotFoundError:
        logger.error(f"Database not found: {db_path}")
        print("AUTH_FAILED", file=sys.stdout, flush=True)
        return EXIT_DB_ERROR

    except Exception as exc:  # noqa: BLE001
        logger.error(f"Unexpected error during authentication: {exc}", exc_info=True)
        print("AUTH_FAILED", file=sys.stdout, flush=True)
        return EXIT_AUTH_FAILED

    finally:
        # ---- Cleanup ----
        try:
            release_camera()
            release_detector()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error during cleanup: {exc}")

        # ---- Check Timeout ----
        elapsed = time.time() - t_start
        if elapsed > timeout_s:
            logger.warning(f"Authentication took {elapsed:.1f}s, exceeded timeout of {timeout_s}s")
            return EXIT_TIMEOUT


def main() -> int:
    """
    Entry point when run as a standalone script.

    Returns
    -------
    int
        Exit code to be returned to the calling process.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="face_authenticator_pipe",
        description="Single-shot face authentication for Windows Credential Provider.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        metavar="PATH",
        help="Path to the encrypted FaceLock database.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="Maximum time for authentication (seconds).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging to stderr.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger("facelock").setLevel(logging.DEBUG)

    return authenticate_pipe(db_path=args.db, timeout_s=args.timeout)


if __name__ == "__main__":
    sys.exit(main())
