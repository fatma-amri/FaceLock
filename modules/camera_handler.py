"""
camera_handler.py
-----------------
Module responsible for capturing frames from the webcam using OpenCV.
Includes optional brightness correction and frame preprocessing.

Dependencies:
    - opencv-python  (pip install opencv-python)
    - numpy          (pip install numpy)

Notes:
    - On Windows (production), cv2.CAP_DSHOW is used to reduce latency.
    - On macOS / Linux (development), the default backend is used.
"""

import logging
import platform
import sys
import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level camera instance (singleton pattern)
# ---------------------------------------------------------------------------
_capture: cv2.VideoCapture | None = None

# Default webcam index (0 = first available device)
DEFAULT_CAMERA_INDEX: int = 0

# Target resolution for captured frames
FRAME_WIDTH: int = 640
FRAME_HEIGHT: int = 480


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_capture() -> cv2.VideoCapture | None:
    """
    Return the module-level VideoCapture instance, initialising it lazily.

    Returns
    -------
    cv2.VideoCapture | None
        An opened VideoCapture object, or None if the camera cannot be opened.
    """
    global _capture

    if _capture is not None and _capture.isOpened():
        return _capture

    logger.info("Initialising webcam (index=%d)…", DEFAULT_CAMERA_INDEX)

    if platform.system() == "Windows":
        # MSMF + MJPG is the only combination that works with the
        # VMware Virtual USB Video Device (CAP_DSHOW returns frames of all zeros).
        import os
        os.environ.setdefault('OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS', '0')
        cap = cv2.VideoCapture(DEFAULT_CAMERA_INDEX, cv2.CAP_MSMF)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    else:
        cap = cv2.VideoCapture(DEFAULT_CAMERA_INDEX)

    if not cap.isOpened():
        logger.error("Cannot open webcam at index %d.", DEFAULT_CAMERA_INDEX)
        return None

    # Force resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    _capture = cap
    logger.info("Webcam opened successfully.")
    return _capture


def _auto_brightness(frame: np.ndarray, target: float = 100.0) -> np.ndarray:
    """
    Apply a simple automatic brightness correction based on the mean luminance
    of the frame.  Converts to LAB, scales the L channel, then converts back
    to BGR.

    Parameters
    ----------
    frame : np.ndarray
        BGR image as returned by OpenCV.
    target : float
        Desired mean luminance value (0-255).  Default is 100.

    Returns
    -------
    np.ndarray
        Brightness-corrected BGR image.
    """
    try:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        mean_l = float(np.mean(l_channel))
        if mean_l < 1.0:
            # Avoid division by zero in very dark conditions
            return frame

        scale = target / mean_l
        # Clip to valid [0, 255] range after scaling
        l_scaled = np.clip(l_channel * scale, 0, 255).astype(np.uint8)

        corrected_lab = cv2.merge([l_scaled, a_channel, b_channel])
        corrected_bgr = cv2.cvtColor(corrected_lab, cv2.COLOR_LAB2BGR)
        return corrected_bgr

    except cv2.error as exc:
        logger.warning("Brightness correction failed: %s", exc)
        return frame


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_frame(
    apply_brightness_correction: bool = True,
) -> np.ndarray | None:
    """
    Capture a single frame from the webcam.

    The frame is read from the internal VideoCapture singleton.  An optional
    automatic brightness correction is applied to improve detection in low-
    light environments.

    Parameters
    ----------
    apply_brightness_correction : bool
        When True (default), apply auto-brightness correction using the LAB
        colour space before returning the frame.

    Returns
    -------
    np.ndarray | None
        A BGR image as a NumPy array of shape (H, W, 3), or None if the
        frame could not be captured.

    Notes
    -----
    - The function never stores the frame to disk.
    - All processing is done in memory.
    - The returned frame is guaranteed to be uint8.
    """
    try:
        cap = _get_capture()
        if cap is None:
            logger.error("VideoCapture is not available.")
            return None

        ret, frame = cap.read()

        if not ret or frame is None:
            logger.warning("Failed to read frame from webcam.")
            return None

        # Sanity-check: frame must be a valid 3-channel image
        if frame.ndim != 3 or frame.shape[2] != 3:
            logger.warning(
                "Unexpected frame shape %s; skipping.", frame.shape
            )
            return None

        if apply_brightness_correction:
            frame = _auto_brightness(frame)

        return frame.astype(np.uint8)

    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in get_frame(): %s", exc, exc_info=True)
        return None


def release_camera() -> None:
    """
    Release the webcam resource and reset the module-level capture handle.

    Should be called on application exit to free the device properly.
    """
    global _capture

    if _capture is not None:
        try:
            _capture.release()
            logger.info("Webcam released.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error while releasing webcam: %s", exc)
        finally:
            _capture = None


# ---------------------------------------------------------------------------
# Quick self-test  (run: python camera_handler.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Self-test: displaying live webcam feed.  Press 'q' to quit.")

    while True:
        captured_frame = get_frame(apply_brightness_correction=True)

        if captured_frame is None:
            logger.error("No frame captured — exiting.")
            sys.exit(1)

        cv2.imshow("FaceLock — camera_handler self-test", captured_frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    release_camera()
    cv2.destroyAllWindows()
    logger.info("Self-test complete.")
