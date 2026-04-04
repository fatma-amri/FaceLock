"""
database.py
-----------
Local SQLite storage for FaceLock user embeddings.

Security model
--------------
- Embeddings are encrypted with AES-128-CBC + HMAC-SHA256 (Fernet) before
  being written to SQLite as BLOBs.
- The encryption key is **machine-bound**: derived at runtime from the
  machine's primary MAC address (via uuid.getnode) using PBKDF2-HMAC-SHA256.
- No plain-text embedding or photo is ever written to disk.
- The key exists **only in memory** during the process lifetime.

Schema
------
    users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT    NOT NULL UNIQUE,
        embedding    BLOB    NOT NULL,      -- Fernet-encrypted numpy bytes
        dtype        TEXT    NOT NULL,      -- original numpy dtype (e.g. float64)
        shape        TEXT    NOT NULL,      -- original numpy shape (e.g. "128")
        created_at   TEXT    NOT NULL       -- ISO-8601 UTC timestamp
    )

Dependencies
------------
    pip install cryptography numpy
    (sqlite3 is part of the Python standard library)
"""

import base64
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import numpy as np
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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

# PBKDF2 parameters — increasing iterations improves brute-force resistance
PBKDF2_ITERATIONS: Final[int] = 390_000
# Fixed application-level salt (not secret, but unique per app/project)
# Change this value if you want to invalidate all previously stored embeddings.
_APP_SALT: Final[bytes] = b"FaceLock-v1-salt-2024"

# Default database path (relative to project root)
DEFAULT_DB_PATH: str = "data/db/facelock.db"


# ---------------------------------------------------------------------------
# Key derivation (machine-bound, in-memory only)
# ---------------------------------------------------------------------------

def _derive_machine_key() -> bytes:
    """
    Derive a deterministic 32-byte key from the machine's primary MAC address
    using PBKDF2-HMAC-SHA256.  The key is reproduced identically on every
    run of the same machine without being stored anywhere.

    Returns
    -------
    bytes
        URL-safe base64-encoded 32-byte Fernet-compatible key.

    Notes
    -----
    - uuid.getnode() returns the MAC address as a 48-bit integer.  On rare
      systems where no real MAC is available it may return a random value
      (flagged by its multicast bit); a warning is logged in that case.
    - The derived key is **not** stored to disk.
    """
    mac_int: int = uuid.getnode()

    # Detect pseudo-random MAC (multicast bit set means it was generated)
    if (mac_int >> 40) & 0x01:
        logger.warning(
            "No real MAC address found — uuid.getnode() returned a pseudo-random "
            "value. The derived key may differ between runs on this machine."
        )

    # Encode MAC as ASCII string → bytes password for KDF
    password: bytes = str(mac_int).encode("ascii")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_APP_SALT,
        iterations=PBKDF2_ITERATIONS,
    )
    raw_key: bytes = kdf.derive(password)
    return base64.urlsafe_b64encode(raw_key)   # Fernet expects URL-safe b64


# Module-level Fernet cipher (initialised once per process)
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """
    Return the module-level Fernet instance, creating it lazily on first call.

    Returns
    -------
    Fernet
        Ready-to-use cipher backed by the machine-bound key.
    """
    global _fernet
    if _fernet is None:
        key = _derive_machine_key()
        _fernet = Fernet(key)
        logger.debug("Fernet cipher initialised (machine-bound key).")
    return _fernet


# ---------------------------------------------------------------------------
# Embedding ↔ bytes helpers
# ---------------------------------------------------------------------------

def _embedding_to_encrypted_blob(embedding: np.ndarray) -> bytes:
    """
    Serialise and encrypt a numpy embedding.

    Parameters
    ----------
    embedding : np.ndarray
        Facial embedding vector (e.g. shape=(128,), dtype=float64).

    Returns
    -------
    bytes
        Fernet-encrypted ciphertext of the raw numpy bytes.
    """
    raw: bytes = embedding.tobytes()          # lossless binary serialisation
    cipher = _get_fernet()
    return cipher.encrypt(raw)


def _blob_to_embedding(
    blob: bytes,
    dtype: str,
    shape_str: str,
) -> np.ndarray | None:
    """
    Decrypt and deserialise an encrypted embedding blob.

    Parameters
    ----------
    blob : bytes
        Fernet-encrypted ciphertext as stored in SQLite.
    dtype : str
        Numpy dtype string (e.g. "float64").
    shape_str : str
        Comma-separated shape string (e.g. "128" or "128,1").

    Returns
    -------
    np.ndarray | None
        Decrypted embedding vector, or None if decryption fails.
    """
    try:
        cipher = _get_fernet()
        raw: bytes = cipher.decrypt(blob)
        shape: tuple[int, ...] = tuple(int(s) for s in shape_str.split(","))
        return np.frombuffer(raw, dtype=np.dtype(dtype)).reshape(shape)
    except InvalidToken:
        logger.error(
            "Decryption failed: InvalidToken. "
            "The blob may have been encrypted on a different machine or "
            "the data is corrupted."
        )
        return None
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error during blob decryption: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def _ensure_db(db_path: str) -> None:
    """
    Create the database file and the *users* table if they do not exist.

    Parameters
    ----------
    db_path : str
        Absolute or relative path to the SQLite database file.
        Parent directories are created automatically.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                embedding   BLOB    NOT NULL,
                dtype       TEXT    NOT NULL,
                shape       TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            )
        """)
        conn.commit()
    logger.debug("Database ready at '%s'.", db_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def add_user(name: str, embedding: np.ndarray, db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Encrypt and persist a user's facial embedding in the local database.

    If a user with the same *name* already exists, their embedding is
    **replaced** (upsert semantics) so that re-enrolment works seamlessly.

    Parameters
    ----------
    name : str
        Unique display name / identifier for the user (e.g. "Alice").
    embedding : np.ndarray
        Facial embedding vector as produced by face_encoder.encode_face().
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If *name* is empty or *embedding* is not a 1-D float numpy array.
    """
    if not name or not name.strip():
        raise ValueError("User name must be a non-empty string.")
    if embedding is None or not isinstance(embedding, np.ndarray):
        raise ValueError("embedding must be a numpy ndarray.")
    if embedding.ndim != 1:
        raise ValueError(
            f"embedding must be 1-D, got shape {embedding.shape}."
        )

    try:
        _ensure_db(db_path)

        blob: bytes = _embedding_to_encrypted_blob(embedding)
        dtype_str: str = str(embedding.dtype)
        shape_str: str = ",".join(str(d) for d in embedding.shape)
        now: str = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO users (name, embedding, dtype, shape, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    embedding  = excluded.embedding,
                    dtype      = excluded.dtype,
                    shape      = excluded.shape,
                    created_at = excluded.created_at
                """,
                (name.strip(), blob, dtype_str, shape_str, now),
            )
            conn.commit()

        logger.info("User '%s' saved to database ('%s').", name, db_path)

    except sqlite3.Error as exc:
        logger.error("SQLite error in add_user(): %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in add_user(): %s", exc, exc_info=True)


def get_all_users(db_path: str = DEFAULT_DB_PATH) -> list[tuple[str, np.ndarray]]:
    """
    Retrieve and decrypt all stored (name, embedding) pairs from the database.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    list[tuple[str, np.ndarray]]
        A list of (name, embedding) pairs.  Rows whose decryption fails are
        silently skipped (logged at ERROR level).  Returns an empty list if
        the database does not exist or is empty.
    """
    if not Path(db_path).exists():
        logger.debug("Database '%s' does not exist yet.", db_path)
        return []

    results: list[tuple[str, np.ndarray]] = []

    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name, embedding, dtype, shape FROM users ORDER BY id"
            ).fetchall()

        for name, blob, dtype_str, shape_str in rows:
            embedding = _blob_to_embedding(blob, dtype_str, shape_str)
            if embedding is not None:
                results.append((name, embedding))
            else:
                logger.error(
                    "Skipping user '%s': embedding could not be decrypted.", name
                )

        logger.debug(
            "Loaded %d user(s) from '%s'.", len(results), db_path
        )

    except sqlite3.Error as exc:
        logger.error("SQLite error in get_all_users(): %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in get_all_users(): %s", exc, exc_info=True)

    return results


def delete_user(name: str, db_path: str = DEFAULT_DB_PATH) -> None:
    """
    Remove a user and their encrypted embedding from the database.

    If no user with *name* exists, the call is a no-op (logged at WARNING).

    Parameters
    ----------
    name : str
        The display name of the user to delete.
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    None
    """
    if not name or not name.strip():
        logger.warning("delete_user(): received an empty name — ignoring.")
        return

    if not Path(db_path).exists():
        logger.warning(
            "delete_user(): database '%s' does not exist.", db_path
        )
        return

    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM users WHERE name = ?", (name.strip(),)
            )
            conn.commit()

        if cursor.rowcount == 0:
            logger.warning(
                "delete_user(): user '%s' not found in '%s'.", name, db_path
            )
        else:
            logger.info(
                "User '%s' deleted from database ('%s').", name, db_path
            )

    except sqlite3.Error as exc:
        logger.error("SQLite error in delete_user(): %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in delete_user(): %s", exc, exc_info=True)


def list_user_names(db_path: str = DEFAULT_DB_PATH) -> list[str]:
    """
    Return only the names of all stored users (no embedding decryption).

    Useful for lightweight UI display without triggering crypto operations.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    list[str]
        Sorted list of user names, or an empty list if none exist.
    """
    if not Path(db_path).exists():
        return []

    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM users ORDER BY name"
            ).fetchall()
        return [row[0] for row in rows]

    except sqlite3.Error as exc:
        logger.error("SQLite error in list_user_names(): %s", exc)
        return []


# ---------------------------------------------------------------------------
# Quick self-test  (run: python database.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import tempfile

    TEST_DB = os.path.join(tempfile.gettempdir(), "facelock_test.db")
    logger.info("=== database.py self-test ===")
    logger.info("Test DB: %s", TEST_DB)

    # Cleanup previous run
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

    # -- Add two users with dummy 128-d embeddings --------------------
    alice_emb = np.random.randn(128).astype(np.float64)
    alice_emb /= np.linalg.norm(alice_emb)

    bob_emb = np.random.randn(128).astype(np.float64)
    bob_emb /= np.linalg.norm(bob_emb)

    add_user("Alice", alice_emb, TEST_DB)
    add_user("Bob",   bob_emb,   TEST_DB)

    # -- Verify retrieval ---------------------------------------------
    users = get_all_users(TEST_DB)
    assert len(users) == 2, f"Expected 2 users, got {len(users)}"

    for u_name, u_emb in users:
        logger.info(
            "  Retrieved: name='%s'  shape=%s  norm=%.4f",
            u_name, u_emb.shape, float(np.linalg.norm(u_emb)),
        )

    # Verify round-trip fidelity (tolerance for float precision)
    alice_rt = next(e for n, e in users if n == "Alice")
    assert np.allclose(alice_emb, alice_rt), "Alice embedding mismatch!"
    logger.info("  Round-trip embedding verification: PASSED")

    # -- Re-enrolment (upsert) ----------------------------------------
    alice_emb2 = np.random.randn(128).astype(np.float64)
    alice_emb2 /= np.linalg.norm(alice_emb2)
    add_user("Alice", alice_emb2, TEST_DB)
    users2 = get_all_users(TEST_DB)
    assert len(users2) == 2, "User count should still be 2 after upsert"
    logger.info("  Upsert test: PASSED")

    # -- Delete Bob ---------------------------------------------------
    delete_user("Bob", TEST_DB)
    names = list_user_names(TEST_DB)
    assert names == ["Alice"], f"Expected ['Alice'], got {names}"
    logger.info("  Delete test: PASSED")

    # Cleanup
    os.remove(TEST_DB)
    logger.info("=== All tests PASSED ===")
