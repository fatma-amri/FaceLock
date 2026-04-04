"""
main.py
-------
FaceLock — point d'entrée principal.

Boucle de surveillance :
    1. Capture une frame (camera_handler)
    2. Authentifie le visage détecté (face_authenticator)
    3. Verrouille la session si absence prolongée (system_controller)

Machine d'états
---------------
    MONITORING  ──(absence > seuil)──►  LOCKING  ──►  LOCKED
    LOCKED      ──(auth OK)──────────►  MONITORING

Usage
-----
    python main.py
    python main.py --no-lock            # dry-run, ne verrouille pas
    python main.py --timeout 10.0       # seuil d'absence en secondes
    python main.py --interval 0.3       # intervalle entre les frames (s)
"""

import argparse
import logging
import signal
import sys
import time
from enum import Enum, auto
from typing import Optional

from modules.camera_handler import get_frame, release_camera
from modules.face_authenticator import authenticate
from modules.system_controller import lock_session

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("facelock.main")

# ---------------------------------------------------------------------------
# Constantes configurables
# ---------------------------------------------------------------------------

# Durée d'absence (en secondes) avant de verrouiller la session
DEFAULT_ABSENCE_TIMEOUT: float = 5.0

# Intervalle de capture entre deux frames (secondes)
DEFAULT_FRAME_INTERVAL: float = 0.2

# Nombre de confirmations consécutives avant de déverrouiller
AUTH_CONFIRM_REQUIRED: int = 2


# ---------------------------------------------------------------------------
# Machine d'états
# ---------------------------------------------------------------------------

class State(Enum):
    MONITORING = auto()   # Utilisateur présent et reconnu
    LOCKING    = auto()   # Seuil d'absence dépassé → verrouillage imminent
    LOCKED     = auto()   # Session verrouillée, attente d'authentification


# ---------------------------------------------------------------------------
# Application principale
# ---------------------------------------------------------------------------

class FaceLockApp:
    """
    Boucle principale de FaceLock.

    Attributes
    ----------
    absence_timeout : float
        Secondes sans reconnaissance avant verrouillage.
    frame_interval : float
        Délai entre deux captures de frame.
    dry_run : bool
        Si True, lock_session() n'est jamais appelée.
    """

    def __init__(
        self,
        absence_timeout: float = DEFAULT_ABSENCE_TIMEOUT,
        frame_interval: float = DEFAULT_FRAME_INTERVAL,
        dry_run: bool = False,
    ) -> None:
        self.absence_timeout: float = absence_timeout
        self.frame_interval: float  = frame_interval
        self.dry_run: bool          = dry_run

        self._state: State    = State.MONITORING
        self._running: bool   = False

        # Horodatage de la dernière reconnaissance réussie
        self._last_seen: float = time.monotonic()

        # Compteur de confirmations avant déverrouillage
        self._auth_confirm: int = 0

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Démarre la boucle de surveillance FaceLock."""
        logger.info(
            "FaceLock démarré — timeout=%.1fs  interval=%.2fs  dry_run=%s",
            self.absence_timeout, self.frame_interval, self.dry_run,
        )

        self._running = True
        self._last_seen = time.monotonic()

        try:
            while self._running:
                self._tick()
                time.sleep(self.frame_interval)

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur (Ctrl-C).")
        except Exception as exc:  # noqa: BLE001
            logger.critical("Erreur fatale dans la boucle principale : %s", exc, exc_info=True)
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Demande un arrêt propre (utilisable depuis un signal ou un autre thread)."""
        logger.info("Arrêt demandé.")
        self._running = False

    # ------------------------------------------------------------------
    # Logique d'un cycle
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """Exécute un cycle complet : capture → authentification → état."""
        # 1. Capture de la frame
        frame = self._capture_frame()
        if frame is None:
            return  # Erreur caméra — on réessaie au prochain cycle

        now: float = time.monotonic()
        absence_s: float = now - self._last_seen

        # 2. Tentative d'authentification
        auth_name: Optional[str] = self._try_authenticate(frame)

        # 3. Mise à jour de la machine d'états
        if self._state == State.MONITORING:
            self._handle_monitoring(auth_name, absence_s)

        elif self._state == State.LOCKING:
            self._handle_locking()

        elif self._state == State.LOCKED:
            self._handle_locked(auth_name, now)

    # ------------------------------------------------------------------
    # Étapes internes
    # ------------------------------------------------------------------

    def _capture_frame(self):  # type: ignore[return]
        """
        Capture une frame depuis la caméra.

        Returns
        -------
        numpy.ndarray | None
            Frame BGR, ou None en cas d'échec.
        """
        try:
            frame = get_frame()
            if frame is None:
                logger.warning("Lecture caméra échouée — aucune frame reçue.")
            return frame
        except Exception as exc:
            logger.error("Exception lors de la capture caméra : %s", exc)
            return None

    def _try_authenticate(self, frame) -> Optional[str]:
        """
        Tente d'authentifier le visage présent dans la frame.

        Returns
        -------
        str | None
            Nom de l'utilisateur reconnu, ou None.
        """
        try:
            return authenticate(frame)
        except Exception as exc:
            logger.error("Exception lors de l'authentification : %s", exc)
            return None

    # ------------------------------------------------------------------
    # Gestionnaires d'états
    # ------------------------------------------------------------------

    def _handle_monitoring(self, auth_name: Optional[str], absence_s: float) -> None:
        """Gère l'état MONITORING."""
        if auth_name:
            # Utilisateur reconnu — réinitialise le compteur d'absence
            self._last_seen = time.monotonic()
            logger.debug("Utilisateur présent : %s", auth_name)
        else:
            logger.debug("Aucun visage reconnu — absence : %.1f s", absence_s)
            if absence_s >= self.absence_timeout:
                logger.info(
                    "Absence de %.1f s détectée (seuil=%.1f s) → verrouillage.",
                    absence_s, self.absence_timeout,
                )
                self._state = State.LOCKING

    def _handle_locking(self) -> None:
        """Gère l'état LOCKING : déclenche le verrouillage et passe à LOCKED."""
        if self.dry_run:
            logger.warning("[DRY-RUN] lock_session() non appelée.")
        else:
            try:
                lock_session()
                logger.info("Session verrouillée.")
            except Exception as exc:
                logger.error("Échec du verrouillage de session : %s", exc)

        self._state = State.LOCKED
        self._auth_confirm = 0

    def _handle_locked(self, auth_name: Optional[str], now: float) -> None:
        """Gère l'état LOCKED : attend une authentification réussie pour déverrouiller."""
        if auth_name:
            self._auth_confirm += 1
            logger.info(
                "Authentification candidate '%s' (%d/%d).",
                auth_name, self._auth_confirm, AUTH_CONFIRM_REQUIRED,
            )
            if self._auth_confirm >= AUTH_CONFIRM_REQUIRED:
                logger.info("Utilisateur '%s' confirmé — session déverrouillée.", auth_name)
                self._state = State.MONITORING
                self._last_seen = now
                self._auth_confirm = 0
        else:
            # Réinitialise si l'authentification échoue
            if self._auth_confirm > 0:
                logger.debug("Authentification échouée — réinitialisation du compteur.")
            self._auth_confirm = 0

    # ------------------------------------------------------------------
    # Arrêt propre
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        """Libère toutes les ressources."""
        logger.info("Arrêt de FaceLock en cours…")
        try:
            release_camera()
        except Exception as exc:
            logger.warning("Erreur lors de la libération de la caméra : %s", exc)
        logger.info("FaceLock arrêté.")


# ---------------------------------------------------------------------------
# Interface en ligne de commande
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        prog="facelock",
        description="FaceLock — verrouillage de session par reconnaissance faciale.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_ABSENCE_TIMEOUT,
        metavar="SECONDES",
        help="Durée d'absence (s) avant verrouillage.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_FRAME_INTERVAL,
        metavar="SECONDES",
        help="Intervalle entre deux captures de frame.",
    )
    parser.add_argument(
        "--no-lock",
        dest="dry_run",
        action="store_true",
        help="Mode dry-run : détecte mais ne verrouille jamais la session.",
    )
    return parser.parse_args()


def main() -> None:
    """Configure et lance FaceLock."""
    args = _parse_args()

    app = FaceLockApp(
        absence_timeout=args.timeout,
        frame_interval=args.interval,
        dry_run=args.dry_run,
    )

    # Gestion propre de SIGTERM (systemd, Task Scheduler…)
    def _on_sigterm(sig: int, frame) -> None:  # type: ignore[type-arg]
        logger.info("SIGTERM reçu.")
        app.stop()

    signal.signal(signal.SIGTERM, _on_sigterm)

    app.run()


if __name__ == "__main__":
    sys.exit(main())
