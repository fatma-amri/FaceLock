"""
face_encoder.py
---------------
Extracts a 128-dimensional facial embedding from a pre-aligned face image
using the `face_recognition` library (backed by dlib's ResNet model).

The embedding is a normalised unit vector in R^128. Similarity between two
embeddings is measured with Euclidean distance (see face_authenticator.py).

Pipeline
--------
    aligned face (BGR, 112×112)
        ↓  BGR → RGB conversion
        ↓  face_recognition.face_encodings()  [dlib ResNet34]
        ↓  128-d float64 numpy array
        ↓  L2 normalisation  →  unit vector
    embedding (np.ndarray, shape=(128,))

Dependencies
------------
    pip install face_recognition numpy opencv-python

    On macOS (ARM) you may need:
        brew install cmake
        pip install dlib face_recognition

    On Windows:
        pip install dlib‑binary face_recognition   # pre-built wheel

Notes
-----
- The input face image must already be cropped and aligned
  (e.g. returned by face_detector.detect_and_align()).
- dlib's model is downloaded automatically on first use by face_recognition.
- No image or embedding is written to disk here.
"""

import logging

import cv2
import face_recognition
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

# "small" = HOG + ResNet (fast, good accuracy, CPU-friendly)
# "large" = CNN-based (slower but slightly more accurate)
ENCODING_MODEL: str = "small"

# Number of re-samples for each face (higher = more accurate, slower).
# 1 is recommended for real-time use.
NUM_JITTERS: int = 1

# Expected embedding dimensionality produced by dlib / face_recognition
EMBEDDING_DIM: int = 128


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _l2_normalize(vector: np.ndarray) -> np.ndarray:
    """
    L2-normalise *vector* to produce a unit vector.

    Parameters
    ----------
    vector : np.ndarray
        Raw embedding vector.

    Returns
    -------
    np.ndarray
        Unit-norm version of *vector*.  If the norm is zero (degenerate
        input), the original vector is returned unchanged.
    """
    norm = np.linalg.norm(vector)
    if norm < 1e-10:
        logger.warning("Embedding norm is near-zero; returning raw vector.")
        return vector
    return vector / norm


def _validate_face_image(face_image: np.ndarray) -> bool:
    """
    Validate that *face_image* is a non-empty 3-channel uint8 array.

    Parameters
    ----------
    face_image : np.ndarray
        Input face image to validate.

    Returns
    -------
    bool
        True if the image is valid, False otherwise.
    """
    if face_image is None:
        logger.warning("encode_face(): received None as input.")
        return False
    if face_image.ndim != 3 or face_image.shape[2] != 3:
        logger.warning(
            "encode_face(): unexpected image shape %s (expected H×W×3).",
            face_image.shape,
        )
        return False
    if face_image.dtype != np.uint8:
        logger.debug(
            "encode_face(): image dtype is %s, converting to uint8.",
            face_image.dtype,
        )
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode_face(face_image: np.ndarray) -> np.ndarray | None:
    """
    Extract a normalised 128-dimensional embedding from an aligned face image.

    The function treats the **entire input image as a single face** — it
    bypasses face re-detection, which would be redundant since the caller
    (face_detector.detect_and_align) has already isolated the face region.

    Parameters
    ----------
    face_image : np.ndarray
        A BGR uint8 image of shape (H, W, 3) containing exactly one aligned
        face (as produced by face_detector.detect_and_align()).

    Returns
    -------
    np.ndarray | None
        A float64 unit vector of shape (128,) if encoding succeeds, or None
        if the input is invalid or dlib fails to produce an encoding.

    Notes
    -----
    - The returned embedding is L2-normalised for consistent distance
      comparison downstream.
    - No file I/O is performed.
    """
    if not _validate_face_image(face_image):
        return None

    try:
        # face_recognition requires RGB input
        rgb_image: np.ndarray = cv2.cvtColor(
            face_image.astype(np.uint8), cv2.COLOR_BGR2RGB
        )

        h, w = rgb_image.shape[:2]

        # Provide the bounding box covering the whole image so that
        # face_recognition skips its internal face-detection step.
        # Format: (top, right, bottom, left)  — CSS-like order.
        known_location = [(0, w, h, 0)]

        encodings: list[np.ndarray] = face_recognition.face_encodings(
            rgb_image,
            known_face_locations=known_location,
            num_jitters=NUM_JITTERS,
            model=ENCODING_MODEL,
        )

        if not encodings:
            logger.warning(
                "face_recognition returned no encodings for the provided face image."
            )
            return None

        raw_embedding: np.ndarray = encodings[0]  # shape (128,), float64

        if raw_embedding.shape != (EMBEDDING_DIM,):
            logger.error(
                "Unexpected embedding shape %s (expected (%d,)).",
                raw_embedding.shape,
                EMBEDDING_DIM,
            )
            return None

        # Normalise to unit vector for consistent cosine/euclidean comparison
        embedding = _l2_normalize(raw_embedding)

        logger.debug(
            "Embedding extracted — shape=%s, norm=%.4f",
            embedding.shape,
            float(np.linalg.norm(embedding)),
        )

        return embedding.astype(np.float64)

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error in encode_face(): %s", exc, exc_info=True
        )
        return None


# ---------------------------------------------------------------------------
# Quick self-test  (run: python face_encoder.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import pathlib

    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

    from modules.camera_handler import get_frame, release_camera  # noqa: E402
    from modules.face_detector import detect_and_align, release_detector  # noqa: E402

    logger.info("Self-test: press 'q' to quit.")
    encoded_count = 0

    while True:
        bgr = get_frame()
        if bgr is None:
            logger.error("No frame — exiting.")
            break

        face = detect_and_align(bgr)

        status_text = "No face detected"
        colour = (0, 0, 255)

        if face is not None:
            embedding = encode_face(face)
            if embedding is not None:
                encoded_count += 1
                status_text = (
                    f"Embedding OK  dim={embedding.shape[0]}"
                    f"  norm={np.linalg.norm(embedding):.3f}"
                    f"  frames={encoded_count}"
                )
                colour = (0, 255, 0)
            else:
                status_text = "Face found but encoding failed"
                colour = (0, 165, 255)

        display = bgr.copy()
        cv2.putText(
            display, status_text, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, colour, 2,
        )
        cv2.imshow("FaceLock — face_encoder self-test", display)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    release_camera()
    release_detector()
    cv2.destroyAllWindows()
    logger.info("Self-test complete. Total embeddings produced: %d", encoded_count)
