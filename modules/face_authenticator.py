"""
face_authenticator.py
---------------------
Compares facial embeddings to authenticate a user against the local database.

Authentication pipeline
-----------------------
    camera frame (BGR)
        ↓  face_detector.detect_and_align()
        ↓  face_encoder.encode_face()        → candidate embedding (128-d)
        ↓  database.get_all_users()          → list of (name, known_embedding)
        ↓  compare_embeddings()  ×  N users  → Euclidean distances
        ↓  best match below threshold?
    str (user name)  or  None (rejected)

Distance metric
---------------
Both embeddings are L2-normalised (unit vectors, produced by face_encoder).
For unit vectors, Euclidean distance and cosine distance carry identical
information.  Euclidean distance is used here for compatibility with the
face_recognition library convention (default threshold ≈ 0.6).

    d = ||e_known − e_candidate||₂

    d < threshold → accept (return name)
    d ≥ threshold → reject (return None)

Dependencies
------------
    pip install numpy
    (face_detector, face_encoder, and database are internal modules)
"""

import logging
import time
from pathlib import Path

import numpy as np

from modules.database import get_all_users
# Internal modules (same package)
from modules.face_detector import detect_and_align
from modules.face_encoder import encode_face

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

# Default similarity threshold (Euclidean distance between unit vectors).
# Values recommended by dlib / face_recognition authors: 0.4 (strict) – 0.6 (lenient).
DEFAULT_THRESHOLD: float = 0.6

# Default database path — absolute path relative to this module's location
# This ensures it works regardless of where the script is run from
DEFAULT_DB_PATH: str = str(
    Path(__file__).parent.parent / "data" / "db" / "facelock.db"
)

# Track if we've already warned about missing database (to avoid spam logging)
_database_warning_logged: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compare_embeddings(
    known: np.ndarray,
    candidate: np.ndarray,
    threshold: float = DEFAULT_THRESHOLD,
) -> bool:
    """
    Decide whether *candidate* matches *known* using Euclidean distance.

    Both vectors are expected to be L2-normalised (unit vectors).
    The decision rule is:  distance < threshold  →  match.

    Parameters
    ----------
    known : np.ndarray
        Reference embedding stored in the database, shape (D,).
    candidate : np.ndarray
        Embedding extracted from the current camera frame, shape (D,).
    threshold : float
        Maximum Euclidean distance to consider a match.
        Default is 0.6 (face_recognition / dlib convention).

    Returns
    -------
    bool
        True if the candidate is within *threshold* of the known embedding,
        False otherwise.

    Raises
    ------
    ValueError
        If the two embeddings have incompatible shapes.
    """
    if known.shape != candidate.shape:
        raise ValueError(
            f"Embedding shape mismatch: known={known.shape}, "
            f"candidate={candidate.shape}."
        )
    if threshold <= 0.0:
        raise ValueError(f"threshold must be > 0, got {threshold}.")

    distance: float = float(np.linalg.norm(known - candidate))
    logger.debug("Euclidean distance: %.4f  (threshold=%.4f)", distance, threshold)
    return distance < threshold


def authenticate(
    frame: np.ndarray,
    db_path: str = DEFAULT_DB_PATH,
    threshold: float = DEFAULT_THRESHOLD,
) -> str | None:
    """
    Attempt to identify the person visible in *frame* against all users
    stored in the local database.

    Steps
    -----
    1. Detect and align the face in the frame.
    2. Encode the aligned face into a 128-d embedding.
    3. Load all (name, embedding) pairs from the database.
    4. Compute Euclidean distance to every known embedding.
    5. Accept the closest match if its distance is below *threshold*.
    6. Return the matched user name, or None if no match is found.

    Parameters
    ----------
    frame : np.ndarray
        BGR image from the webcam (e.g. from camera_handler.get_frame()).
    db_path : str
        Path to the SQLite database file.
    threshold : float
        Maximum Euclidean distance accepted as a genuine match.

    Returns
    -------
    str | None
        The name of the authenticated user, or None if authentication fails
        (no face detected, encoding failure, empty database, or distance
        exceeds threshold).

    Notes
    -----
    - If multiple users are within *threshold*, the closest one is returned
      and a warning is logged (possible look-alike scenario).
    - No image is written to disk at any point.
    - Performance is O(N) in the number of enrolled users; suitable for
      small-to-medium databases (N < 1000) on CPU.
    """
    if frame is None:
        logger.warning("authenticate(): received None frame.")
        return None

    t_start: float = time.perf_counter()

    # ------------------------------------------------------------------ #
    # Step 1 — Face detection & alignment                                 #
    # ------------------------------------------------------------------ #
    aligned_face = detect_and_align(frame)
    if aligned_face is None:
        logger.debug("authenticate(): no face detected in frame.")
        return None

    # ------------------------------------------------------------------ #
    # Step 2 — Embedding extraction                                       #
    # ------------------------------------------------------------------ #
    candidate_embedding = encode_face(aligned_face)
    if candidate_embedding is None:
        logger.warning("authenticate(): face found but encoding failed.")
        return None

    # ------------------------------------------------------------------ #
    # Step 3 — Load known users                                           #
    # ------------------------------------------------------------------ #
    if not Path(db_path).exists():
        global _database_warning_logged
        if not _database_warning_logged:
            logger.warning(
                "authenticate(): database '%s' does not exist. "
                "No users are enrolled yet. Run enrollment_ui.py to enroll faces.",
                db_path,
            )
            _database_warning_logged = True
        return None

    known_users: list[tuple[str, np.ndarray]] = get_all_users(db_path)

    if not known_users:
        logger.warning("authenticate(): database is empty — no enrolled users.")
        return None

    # ------------------------------------------------------------------ #
    # Step 4 — Compute distances                                          #
    # ------------------------------------------------------------------ #
    distances: list[tuple[float, str]] = []

    for name, known_embedding in known_users:
        try:
            dist = float(np.linalg.norm(known_embedding - candidate_embedding))
            distances.append((dist, name))
            logger.debug("  %-20s  dist=%.4f", name, dist)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error computing distance for user '%s': %s", name, exc
            )

    if not distances:
        logger.error("authenticate(): all distance computations failed.")
        return None

    # Sort ascending by distance — closest match first
    distances.sort(key=lambda t: t[0])
    best_distance, best_name = distances[0]

    # ------------------------------------------------------------------ #
    # Step 5 — Accept / reject decision                                   #
    # ------------------------------------------------------------------ #
    if best_distance >= threshold:
        logger.info(
            "authenticate(): REJECTED  best_match='%s'  dist=%.4f  threshold=%.4f",
            best_name,
            best_distance,
            threshold,
        )
        return None

    # Warn if multiple users fall within the threshold (ambiguous match)
    matches_within_threshold = [
        (d, n) for d, n in distances if d < threshold
    ]
    if len(matches_within_threshold) > 1:
        names_list = [n for _, n in matches_within_threshold]
        logger.warning(
            "authenticate(): %d users within threshold %s — "
            "ambiguous match detected. Choosing closest: '%s'.",
            len(matches_within_threshold),
            threshold,
            best_name,
        )
        _ = names_list  # suppress unused-variable warning

    elapsed_ms: float = (time.perf_counter() - t_start) * 1000
    logger.info(
        "authenticate(): ACCEPTED  user='%s'  dist=%.4f  threshold=%.4f  %.1f ms",
        best_name,
        best_distance,
        threshold,
        elapsed_ms,
    )

    return best_name


# ---------------------------------------------------------------------------
# Utility: batch verification (useful for enrollment UI diagnostics)
# ---------------------------------------------------------------------------

def get_best_match(
    frame: np.ndarray,
    db_path: str = DEFAULT_DB_PATH,
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[str | None, float | None]:
    """
    Like authenticate(), but also returns the raw Euclidean distance of the
    best match.  Useful for debugging and UI confidence displays.

    Parameters
    ----------
    frame : np.ndarray
        BGR webcam frame.
    db_path : str
        Path to the SQLite database.
    threshold : float
        Acceptance threshold.

    Returns
    -------
    tuple[str | None, float | None]
        (matched_name, distance) if a face is found and the database is not
        empty; (None, None) if no face is detected or the DB is missing.
        The name is None (but distance is still returned) if the match was
        rejected by the threshold.
    """
    if frame is None:
        return None, None

    aligned_face = detect_and_align(frame)
    if aligned_face is None:
        return None, None

    candidate_embedding = encode_face(aligned_face)
    if candidate_embedding is None:
        return None, None

    if not Path(db_path).exists():
        return None, None

    known_users = get_all_users(db_path)
    if not known_users:
        return None, None

    distances = [
        (float(np.linalg.norm(emb - candidate_embedding)), name)
        for name, emb in known_users
    ]
    distances.sort()
    best_dist, best_name = distances[0]

    matched = best_name if best_dist < threshold else None
    return matched, best_dist


# ---------------------------------------------------------------------------
# Quick self-test  (run: python face_authenticator.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import pathlib
    import sys

    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

    # -- Unit test: compare_embeddings ---------------------------------
    logger.info("=== compare_embeddings unit test ===")

    rng = np.random.default_rng(42)
    v1 = rng.standard_normal(128).astype(np.float64)
    v1 /= np.linalg.norm(v1)

    v2 = v1 + rng.standard_normal(128) * 0.05   # very similar
    v2 /= np.linalg.norm(v2)

    v3 = rng.standard_normal(128).astype(np.float64)  # unrelated
    v3 /= np.linalg.norm(v3)

    assert compare_embeddings(v1, v2, threshold=0.6), "v1≈v2 should match"
    assert not compare_embeddings(v1, v3, threshold=0.6), "v1≠v3 should not match"
    logger.info("compare_embeddings: PASSED")

    # -- Live camera test: authenticate --------------------------------
    logger.info("=== Live authenticate test ===")
    logger.info(
        "No enrolled users → authenticate() should return None on every frame."
    )
    logger.info("Press 'q' to quit.")

    import cv2  # noqa: E402

    from modules.camera_handler import get_frame, release_camera  # noqa: E402
    from modules.face_detector import release_detector  # noqa: E402

    while True:
        bgr = get_frame()
        if bgr is None:
            logger.error("No frame — exiting.")
            break

        user = authenticate(bgr, db_path=DEFAULT_DB_PATH)

        status = f"Authenticated: {user}" if user else "Not recognised"
        colour = (0, 255, 0) if user else (0, 0, 255)

        cv2.putText(
            bgr, status, (10, 35),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2,
        )
        cv2.imshow("FaceLock — face_authenticator test", bgr)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    release_camera()
    release_detector()
    cv2.destroyAllWindows()
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
    logger.info("Self-test complete.")
