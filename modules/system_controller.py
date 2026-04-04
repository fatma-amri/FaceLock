"""
system_controller.py
--------------------
Handles OS-level actions: session locking and sleep prevention.

Platform support
----------------
    Windows  : LockWorkStation()  via ctypes.windll, SetThreadExecutionState
    macOS    : screensaver / pmset via subprocess  (development / testing)
    Linux    : loginctl lock-session via subprocess (bonus)

Dependencies
------------
    Standard library only (ctypes, subprocess, platform).

Notes
-----
- On Windows (production target), ctypes calls are used directly.
- On macOS/Linux, subprocess fallbacks are used so the module stays
  importable and testable during development.
"""

import ctypes
import logging
import platform
import subprocess

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
_OS: str = platform.system()   # "Windows" | "Darwin" | "Linux"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lock_session() -> None:
    """
    Lock the current user session immediately.

    - Windows : calls ``LockWorkStation()`` from user32.dll via ctypes.
    - macOS   : activates the screensaver via AppleScript (development proxy).
    - Linux   : calls ``loginctl lock-session`` via subprocess.

    Returns
    -------
    None

    Notes
    -----
    On Windows, LockWorkStation() requires the calling process to have an
    interactive desktop (works fine for a foreground or tray application).
    """
    logger.info("Locking session (OS=%s)…", _OS)

    try:
        if _OS == "Windows":
            result: int = ctypes.windll.user32.LockWorkStation()  # type: ignore[attr-defined]
            if result == 0:
                err = ctypes.GetLastError()  # type: ignore[attr-defined]
                logger.error("LockWorkStation() failed — error code %d.", err)
            else:
                logger.info("Session locked via LockWorkStation().")

        elif _OS == "Darwin":
            # Activate the macOS screen saver (acts as a lock if password is required)
            script = (
                'tell application "System Events" to '
                'start current screen saver'
            )
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=5,
            )
            logger.info("Screen saver activated (macOS lock proxy).")

        else:
            # Linux / other POSIX
            subprocess.run(
                ["loginctl", "lock-session"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            logger.info("Session locked via loginctl.")

    except subprocess.TimeoutExpired:
        logger.error("lock_session(): subprocess timed out.")
    except subprocess.CalledProcessError as exc:
        logger.error("lock_session(): subprocess error — %s", exc)
    except AttributeError:
        # windll not available outside Windows
        logger.warning(
            "lock_session(): ctypes.windll unavailable on %s — "
            "lock skipped (development mode).", _OS
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("lock_session(): unexpected error — %s", exc, exc_info=True)


def prevent_sleep() -> None:
    """
    Prevent the operating system from entering sleep / screen-off state.

    This is useful to keep the camera active while FaceLock is running and
    waiting for the user to return after a session lock.

    - Windows : sets ``ES_CONTINUOUS | ES_SYSTEM_REQUIRED`` via
                ``SetThreadExecutionState``.
    - macOS   : no-op (the monitoring loop itself keeps the process alive;
                ``caffeinate`` can be launched externally if needed).
    - Linux   : calls ``xdg-screensaver reset`` if available.

    Returns
    -------
    None

    Notes
    -----
    On Windows, the effect is **thread-scoped** and reset when
    ``allow_sleep()`` is called or the process exits.
    """
    logger.info("Requesting sleep prevention (OS=%s)…", _OS)

    try:
        if _OS == "Windows":
            # ES_CONTINUOUS = 0x80000000
            # ES_SYSTEM_REQUIRED = 0x00000001
            ES_CONTINUOUS: int      = 0x80000000
            ES_SYSTEM_REQUIRED: int = 0x00000001
            flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(flags)  # type: ignore[attr-defined]
            logger.info("SetThreadExecutionState: sleep prevented.")

        elif _OS == "Darwin":
            logger.info(
                "prevent_sleep(): macOS — no-op "
                "(run `caffeinate -i -w %d` externally if needed).",
                __import__("os").getpid(),
            )

        else:
            subprocess.run(
                ["xdg-screensaver", "reset"],
                check=False,
                capture_output=True,
                timeout=3,
            )
            logger.info("xdg-screensaver reset called.")

    except AttributeError:
        logger.warning(
            "prevent_sleep(): ctypes.windll unavailable on %s — skipped.",
            _OS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("prevent_sleep(): unexpected error — %s", exc, exc_info=True)


def allow_sleep() -> None:
    """
    Restore normal OS sleep behaviour (Windows only).

    Call this on application exit to reset the execution-state flag set by
    ``prevent_sleep()``.

    Returns
    -------
    None
    """
    if _OS != "Windows":
        return

    try:
        ES_CONTINUOUS: int = 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)  # type: ignore[attr-defined]
        logger.info("SetThreadExecutionState: sleep restored.")
    except AttributeError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.error("allow_sleep(): %s", exc)


# ---------------------------------------------------------------------------
# Quick self-test  (run: python -m modules.system_controller)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import time

    logger.info("=== system_controller self-test ===")
    logger.info("OS detected: %s", _OS)

    prevent_sleep()
    logger.info("Waiting 2 s before triggering lock…")
    time.sleep(2)

    lock_session()
    allow_sleep()
    logger.info("Self-test complete.")
