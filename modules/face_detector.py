"""
face_detector.py
----------------
Detects a human face in a BGR frame and returns a normalised, geometrically
aligned face crop ready for embedding extraction.

Pipeline
--------
1. MediaPipe Tasks FaceDetector  →  bounding box + key-point landmarks
2. Eye-pair alignment             →  affine rotation (eye-line horizontal)
3. Square crop + resize           →  fixed output (OUTPUT_SIZE × OUTPUT_SIZE, 3)

Model
-----
Requires the BlazeFace TFLite model file (short-range, ~228 KB):
    models/blaze_face_short_range.tflite

Download once:
    curl -sL https://storage.googleapis.com/mediapipe-models/face_detector/
         blaze_face_short_range/float16/latest/blaze_face_short_range.tflite
         -o models/blaze_face_short_range.tflite

Dependencies
------------
    pip install mediapipe opencv-python numpy

Compatibility
-------------
    Designed for mediapipe >= 0.10 (Tasks API).
    mp.solutions.face_detection is removed in 0.10+.
"""

import logging
import math
import pathlib
from typing import Final

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Output face size (square) fed to the encoder
OUTPUT_SIZE: Final[int] = 112

# Minimum detection confidence (0.0 – 1.0)
MIN_DETECTION_CONFIDENCE: Final[float] = 0.6

# Default path to the TFLite model file (relative to project root)
DEFAULT_MODEL_PATH: Final[str] = "models/blaze_face_short_range.tflite"

# How much to expand the bounding box (fraction of box size) to avoid clipping
BBOX_MARGIN: Final[float] = 0.20

# ---------------------------------------------------------------------------
# MediaPipe Tasks API types (shorthand aliases)
# ---------------------------------------------------------------------------
_Vision = mp.tasks.vision
_BaseOptions = mp.tasks.BaseOptions

# ---------------------------------------------------------------------------
# Module-level detector singleton
# ---------------------------------------------------------------------------
_detector: _Vision.FaceDetector | None = None


def _get_detector(model_path: str = DEFAULT_MODEL_PATH) -> _Vision.FaceDetector:
    """
    Return the module-level FaceDetector, creating it lazily on first call.

    Parameters
    ----------
    model_path : str
        Path to the BlazeFace TFLite model file.

    Returns
    -------
    mp.tasks.vision.FaceDetector
        Ready-to-use detector in IMAGE running mode.

    Raises
    ------
    FileNotFoundError
        If the model file is not found at *model_path*.
    """
    global _detector

    if _detector is not None:
        return _detector

    abs_model = str(pathlib.Path(model_path).resolve())
    if not pathlib.Path(abs_model).exists():
        raise FileNotFoundError(
            f"MediaPipe model not found: '{abs_model}'.\n"
            "Download with:\n"
            "  curl -sL https://storage.googleapis.com/mediapipe-models/"
            "face_detector/blaze_face_short_range/float16/latest/"
            "blaze_face_short_range.tflite -o models/blaze_face_short_range.tflite"
        )

    logger.info("Initialising MediaPipe FaceDetector (model='%s')…", abs_model)

    options = _Vision.FaceDetectorOptions(
        base_options=_BaseOptions(model_asset_path=abs_model),
        running_mode=_Vision.RunningMode.IMAGE,
        min_detection_confidence=MIN_DETECTION_CONFIDENCE,
    )
    _detector = _Vision.FaceDetector.create_from_options(options)
    logger.info("MediaPipe FaceDetector ready.")
    return _detector


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _expand_bbox(
    x: int, y: int, w: int, h: int,
    frame_h: int, frame_w: int,
    margin: float = BBOX_MARGIN,
) -> tuple[int, int, int, int]:
    """
    Expand a bounding box by *margin* fraction and clamp to frame boundaries.

    Parameters
    ----------
    x, y : int
        Top-left corner of the box (pixels).
    w, h : int
        Width and height of the box (pixels).
    frame_h, frame_w : int
        Frame dimensions for clamping.
    margin : float
        Fractional expansion (0.20 → +20 % on each side).

    Returns
    -------
    tuple[int, int, int, int]
        Clamped (x, y, w, h).
    """
    dx = int(w * margin)
    dy = int(h * margin)
    x1 = max(0, x - dx)
    y1 = max(0, y - dy)
    x2 = min(frame_w, x + w + dx)
    y2 = min(frame_h, y + h + dy)
    return x1, y1, x2 - x1, y2 - y1


def _align_face(
    frame: np.ndarray,
    left_eye: tuple[float, float],
    right_eye: tuple[float, float],
    x: int, y: int, w: int, h: int,
) -> np.ndarray | None:
    """
    Rotate the face crop so that the eye-line is horizontal.

    Parameters
    ----------
    frame : np.ndarray
        Full BGR input frame.
    left_eye, right_eye : tuple[float, float]
        Eye key-point absolute pixel coordinates (x, y).
    x, y, w, h : int
        Expanded bounding box of the face region.

    Returns
    -------
    np.ndarray | None
        Aligned face, shape (OUTPUT_SIZE, OUTPUT_SIZE, 3), or None on failure.
    """
    try:
        dx = right_eye[0] - left_eye[0]
        dy = right_eye[1] - left_eye[1]
        angle = math.degrees(math.atan2(dy, dx))

        eye_centre = (
            (left_eye[0] + right_eye[0]) / 2.0,
            (left_eye[1] + right_eye[1]) / 2.0,
        )

        rot_mat = cv2.getRotationMatrix2D(eye_centre, angle, scale=1.0)
        fh, fw = frame.shape[:2]
        rotated = cv2.warpAffine(
            frame, rot_mat, (fw, fh), flags=cv2.INTER_LINEAR
        )

        crop = rotated[y: y + h, x: x + w]
        if crop.size == 0:
            return None

        return cv2.resize(crop, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_AREA)

    except cv2.error as exc:
        logger.warning("Alignment error (cv2): %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Alignment error (unexpected): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_and_align(
    frame: np.ndarray,
    model_path: str = DEFAULT_MODEL_PATH,
) -> np.ndarray | None:
    """
    Detect the most prominent face in *frame* and return a normalised,
    geometrically aligned face image.

    Parameters
    ----------
    frame : np.ndarray
        BGR image captured by OpenCV (e.g. from camera_handler.get_frame()).
    model_path : str
        Path to the BlazeFace TFLite model file.

    Returns
    -------
    np.ndarray | None
        uint8 BGR face image of shape (OUTPUT_SIZE, OUTPUT_SIZE, 3) if a
        face is detected, otherwise None.

    Notes
    -----
    - Only the highest-confidence detection is returned.
    - All processing is in memory; no file I/O is performed.
    - MediaPipe Tasks API expects an mp.Image (RGB); conversion is internal.

    Key-point index mapping (BlazeFace short-range):
        0 = right eye
        1 = left eye
        2 = nose tip
        3 = mouth
        4 = right ear tragion
        5 = left ear tragion
    """
    if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
        logger.warning("detect_and_align(): invalid frame.")
        return None

    try:
        fh, fw = frame.shape[:2]

        # MediaPipe Tasks requires RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        detector = _get_detector(model_path)
        result = detector.detect(mp_image)

        if not result.detections:
            logger.debug("No face detected in frame.")
            return None

        # Pick highest-confidence detection
        best = max(result.detections, key=lambda d: d.categories[0].score)

        # ------------------------------------------------------------------ #
        # Bounding box (relative → absolute pixels)                           #
        # ------------------------------------------------------------------ #
        bb = best.bounding_box          # mediapipe.tasks.components.containers.BoundingBox
        x = int(bb.origin_x)
        y = int(bb.origin_y)
        w = int(bb.width)
        h = int(bb.height)

        if w <= 0 or h <= 0:
            logger.warning("Degenerate bounding box (%d,%d,%d,%d).", x, y, w, h)
            return None

        x, y, w, h = _expand_bbox(x, y, w, h, fh, fw)

        # ------------------------------------------------------------------ #
        # Eye key-points for geometric alignment                              #
        # ------------------------------------------------------------------ #
        kps = best.key_points           # list of NormalizedKeypoint
        right_eye = (kps[0].x * fw, kps[0].y * fh)
        left_eye  = (kps[1].x * fw, kps[1].y * fh)

        face_image = _align_face(frame, left_eye, right_eye, x, y, w, h)

        if face_image is None:
            logger.warning("Alignment failed; using plain crop as fallback.")
            crop = frame[y: y + h, x: x + w]
            if crop.size == 0:
                return None
            face_image = cv2.resize(
                crop, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_AREA
            )

        return face_image.astype(np.uint8)

    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in detect_and_align(): %s", exc, exc_info=True)
        return None


def release_detector() -> None:
    """
    Close the MediaPipe FaceDetector and free its resources.
    Call on application exit.
    """
    global _detector
    if _detector is not None:
        try:
            _detector.close()
            logger.info("MediaPipe FaceDetector released.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Error releasing detector: %s", exc)
        finally:
            _detector = None


# ---------------------------------------------------------------------------
# Quick self-test  (run: python -m modules.face_detector from project root)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

    from modules.camera_handler import get_frame, release_camera  # noqa: E402

    logger.info("Self-test: press 'q' to quit.")

    while True:
        bgr = get_frame()
        if bgr is None:
            logger.error("No frame — exiting.")
            break

        face = detect_and_align(bgr)
        display = bgr.copy()

        if face is not None:
            cv2.putText(display, "Face detected", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.imshow("Aligned face", face)
        else:
            cv2.putText(display, "No face", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

        cv2.imshow("FaceLock — face_detector self-test", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    release_camera()
    release_detector()
    cv2.destroyAllWindows()
