"""
enrollment_ui.py
----------------
FaceLock — interface graphique d'enrôlement des utilisateurs.

Fonctionnalités
---------------
- Aperçu en direct de la webcam (thread dédié)
- Capture d'un visage aligné et génération de son embedding
- Enregistrement chiffré dans la base SQLite
- Liste des utilisateurs enrôlés avec suppression

Dépendances
-----------
    pip install customtkinter opencv-python mediapipe face_recognition cryptography numpy

Usage
-----
    python enrollment_ui.py
    python enrollment_ui.py --db data/db/facelock.db
"""

import argparse
import logging
import threading
import time
from tkinter import messagebox
from typing import Optional

import cv2
import customtkinter as ctk
import numpy as np
from PIL import Image

from modules.camera_handler import get_frame, release_camera
from modules.database import (
    DEFAULT_DB_PATH,
    add_user,
    delete_user,
    list_user_names,
)
from modules.face_detector import detect_and_align, release_detector
from modules.face_encoder import encode_face

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("facelock.enrollment_ui")

# ---------------------------------------------------------------------------
# Thème global customtkinter
# ---------------------------------------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------------------
# Constantes UI
# ---------------------------------------------------------------------------
PREVIEW_WIDTH: int  = 480
PREVIEW_HEIGHT: int = 360

# Nombre de frames capturées puis moyennées pour stabiliser l'embedding
CAPTURE_SAMPLES: int = 5

# Délai (s) entre deux captures lors de l'enrôlement
CAPTURE_DELAY: float = 0.15

# Intervalle de rafraîchissement du flux webcam (ms)
PREVIEW_REFRESH_MS: int = 30


# ===========================================================================
# Fenêtre principale
# ===========================================================================

class EnrollmentApp(ctk.CTk):
    """Interface graphique d'enrôlement FaceLock."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        super().__init__()

        self.db_path: str = db_path

        # ------------------------------------------------------------------ #
        # Fenêtre                                                             #
        # ------------------------------------------------------------------ #
        self.title("FaceLock — Enrôlement")
        self.geometry("900x560")
        self.resizable(False, False)

        # ------------------------------------------------------------------ #
        # État interne                                                        #
        # ------------------------------------------------------------------ #
        self._current_frame: Optional[np.ndarray] = None
        self._frame_lock: threading.Lock = threading.Lock()
        self._preview_running: bool = False
        self._enroll_in_progress: bool = False

        # ------------------------------------------------------------------ #
        # Construction de l'interface                                         #
        # ------------------------------------------------------------------ #
        self._build_ui()
        self._refresh_user_list()

        # ------------------------------------------------------------------ #
        # Démarrage du flux webcam                                           #
        # ------------------------------------------------------------------ #
        self._preview_running = True
        self._preview_thread = threading.Thread(
            target=self._preview_loop, daemon=True
        )
        self._preview_thread.start()
        self._schedule_preview_update()

        # ------------------------------------------------------------------ #
        # Nettoyage à la fermeture                                           #
        # ------------------------------------------------------------------ #
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------------- #
    # Construction de l'interface                                             #
    # ---------------------------------------------------------------------- #

    def _build_ui(self) -> None:
        """Crée et positionne tous les widgets."""

        # Layout : colonne gauche (preview) | colonne droite (contrôles)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Panneau gauche — aperçu webcam ────────────────────────────────
        left_frame = ctk.CTkFrame(self, corner_radius=12)
        left_frame.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="nsew")

        ctk.CTkLabel(
            left_frame,
            text="Aperçu webcam",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(12, 6))

        self._preview_label = ctk.CTkLabel(left_frame, text="")
        self._preview_label.pack(padx=12, pady=(0, 8))

        # Indicateur de statut de détection
        self._detection_badge = ctk.CTkLabel(
            left_frame,
            text="● En attente…",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self._detection_badge.pack(pady=(0, 12))

        # ── Panneau droit — contrôles ──────────────────────────────────────
        right_frame = ctk.CTkFrame(self, corner_radius=12)
        right_frame.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)

        # — Section : Ajouter un utilisateur —
        ctk.CTkLabel(
            right_frame,
            text="➕  Ajouter un utilisateur",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(20, 6), sticky="w")

        ctk.CTkLabel(
            right_frame,
            text="Nom complet :",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, padx=20, pady=(4, 2), sticky="w")

        self._name_entry = ctk.CTkEntry(
            right_frame,
            placeholder_text="ex : Alice Dupont",
            height=38,
            font=ctk.CTkFont(size=13),
        )
        self._name_entry.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew")

        self._enroll_btn = ctk.CTkButton(
            right_frame,
            text="📸  Capturer et enrôler",
            height=42,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_enroll,
        )
        self._enroll_btn.grid(row=3, column=0, padx=20, pady=(0, 6), sticky="ew")

        self._status_label = ctk.CTkLabel(
            right_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=340,
        )
        self._status_label.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="w")

        # Séparateur
        ctk.CTkFrame(right_frame, height=2, fg_color=("gray80", "gray30")).grid(
            row=5, column=0, padx=20, pady=4, sticky="ew"
        )

        # — Section : Utilisateurs enrôlés —
        ctk.CTkLabel(
            right_frame,
            text="👤  Utilisateurs enrôlés",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=6, column=0, padx=20, pady=(16, 6), sticky="w")

        self._user_listbox = ctk.CTkScrollableFrame(
            right_frame, height=140, corner_radius=8
        )
        self._user_listbox.grid(row=7, column=0, padx=20, pady=(0, 10), sticky="ew")
        self._user_listbox.grid_columnconfigure(0, weight=1)

        self._delete_btn = ctk.CTkButton(
            right_frame,
            text="🗑  Supprimer l'utilisateur sélectionné",
            height=38,
            font=ctk.CTkFont(size=12),
            fg_color="#c0392b",
            hover_color="#922b21",
            command=self._on_delete,
        )
        self._delete_btn.grid(row=8, column=0, padx=20, pady=(0, 20), sticky="ew")

        # Variable pour la sélection dans la liste
        self._selected_user: Optional[str] = None

    # ---------------------------------------------------------------------- #
    # Flux webcam (thread dédié + mise à jour Tkinter)                        #
    # ---------------------------------------------------------------------- #

    def _preview_loop(self) -> None:
        """
        Thread de capture : lit les frames en continu et les stocke dans
        `_current_frame` (accès protégé par `_frame_lock`).
        """
        while self._preview_running:
            try:
                frame = get_frame()
                if frame is not None:
                    with self._frame_lock:
                        self._current_frame = frame
            except Exception as exc:
                logger.error("Erreur dans _preview_loop : %s", exc)
            time.sleep(PREVIEW_REFRESH_MS / 1000.0)

    def _schedule_preview_update(self) -> None:
        """Planifie la mise à jour du widget d'aperçu dans la boucle Tkinter."""
        self._update_preview_widget()
        self.after(PREVIEW_REFRESH_MS, self._schedule_preview_update)

    def _update_preview_widget(self) -> None:
        """Affiche la dernière frame capturée et met à jour l'indicateur de détection."""
        with self._frame_lock:
            frame = self._current_frame.copy() if self._current_frame is not None else None

        if frame is None:
            return

        # Détection en temps réel pour le badge
        face = detect_and_align(frame)
        if face is not None:
            self._detection_badge.configure(
                text="● Visage détecté", text_color="#2ecc71"
            )
        else:
            self._detection_badge.configure(
                text="● Aucun visage", text_color="#e74c3c"
            )

        # Conversion BGR → PIL → CTkImage
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).resize(
            (PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.LANCZOS
        )
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img,
                               size=(PREVIEW_WIDTH, PREVIEW_HEIGHT))
        self._preview_label.configure(image=ctk_img)
        self._preview_label.image = ctk_img  # type: ignore[attr-defined]

    # ---------------------------------------------------------------------- #
    # Enrôlement                                                              #
    # ---------------------------------------------------------------------- #

    def _on_enroll(self) -> None:
        """Appelé lors du clic sur 'Capturer et enrôler'."""
        name: str = self._name_entry.get().strip()

        if not name:
            messagebox.showwarning(
                "Nom manquant",
                "Veuillez saisir un nom avant de capturer.",
                parent=self,
            )
            return

        if self._enroll_in_progress:
            return

        # Lance l'enrôlement dans un thread pour ne pas bloquer l'UI
        self._enroll_in_progress = True
        self._enroll_btn.configure(state="disabled", text="⏳  Capture en cours…")
        self._set_status("Capture du visage en cours…", color="gray")

        thread = threading.Thread(
            target=self._enroll_worker,
            args=(name,),
            daemon=True,
        )
        thread.start()

    def _enroll_worker(self, name: str) -> None:
        """
        Thread d'enrôlement :
        1. Capture CAPTURE_SAMPLES frames avec un face aligné
        2. Génère les embeddings et les moyenne
        3. Enregistre dans la base de données
        """
        embeddings: list[np.ndarray] = []
        attempts: int = 0
        max_attempts: int = CAPTURE_SAMPLES * 10  # évite une boucle infinie

        self.after(0, lambda: self._set_status(
            f"Alignement du visage… (0/{CAPTURE_SAMPLES} captures)",
            color="gray",
        ))

        while len(embeddings) < CAPTURE_SAMPLES and attempts < max_attempts:
            attempts += 1

            with self._frame_lock:
                frame = self._current_frame.copy() if self._current_frame is not None else None

            if frame is None:
                time.sleep(CAPTURE_DELAY)
                continue

            try:
                face_img = detect_and_align(frame)
                if face_img is None:
                    time.sleep(CAPTURE_DELAY)
                    continue

                embedding = encode_face(face_img)
                if embedding is None:
                    time.sleep(CAPTURE_DELAY)
                    continue

                embeddings.append(embedding)
                count = len(embeddings)
                self.after(0, lambda c=count: self._set_status(
                    f"Alignement du visage… ({c}/{CAPTURE_SAMPLES} captures)",
                    color="gray",
                ))
                time.sleep(CAPTURE_DELAY)

            except Exception as exc:
                logger.error("Erreur pendant l'enrôlement : %s", exc)
                time.sleep(CAPTURE_DELAY)

        # ── Résultat ──────────────────────────────────────────────────────
        if len(embeddings) < CAPTURE_SAMPLES:
            self.after(0, lambda: self._enroll_failed(
                "Impossible de détecter un visage.\n"
                "Assurez-vous d'être bien face à la caméra et dans un endroit éclairé."
            ))
            return

        try:
            # Moyenne des embeddings capturés puis re-normalisation
            mean_embedding: np.ndarray = np.mean(np.stack(embeddings), axis=0)
            norm = np.linalg.norm(mean_embedding)
            if norm > 1e-10:
                mean_embedding /= norm

            add_user(name, mean_embedding, db_path=self.db_path)
            logger.info("Utilisateur '%s' enrôlé avec succès.", name)

            self.after(0, lambda: self._enroll_success(name))

        except Exception as exc:
            logger.error("Erreur lors de l'enregistrement en base : %s", exc)
            self.after(0, lambda: self._enroll_failed(
                f"Échec de l'enregistrement : {exc}"
            ))

    def _enroll_success(self, name: str) -> None:
        """Callback UI : enrôlement réussi."""
        self._enroll_in_progress = False
        self._enroll_btn.configure(state="normal", text="📸  Capturer et enrôler")
        self._name_entry.delete(0, "end")
        self._set_status(
            f"✅  '{name}' enrôlé avec succès.", color="#2ecc71"
        )
        self._refresh_user_list()
        messagebox.showinfo(
            "Enrôlement réussi",
            f"L'utilisateur « {name} » a été enrôlé avec succès.",
            parent=self,
        )

    def _enroll_failed(self, reason: str) -> None:
        """Callback UI : échec de l'enrôlement."""
        self._enroll_in_progress = False
        self._enroll_btn.configure(state="normal", text="📸  Capturer et enrôler")
        self._set_status(f"❌  {reason}", color="#e74c3c")
        messagebox.showerror("Échec de l'enrôlement", reason, parent=self)

    # ---------------------------------------------------------------------- #
    # Suppression                                                             #
    # ---------------------------------------------------------------------- #

    def _on_delete(self) -> None:
        """Appelé lors du clic sur 'Supprimer'."""
        if not self._selected_user:
            messagebox.showwarning(
                "Aucun utilisateur sélectionné",
                "Veuillez sélectionner un utilisateur dans la liste.",
                parent=self,
            )
            return

        confirmed = messagebox.askyesno(
            "Confirmation",
            f"Supprimer définitivement « {self._selected_user} » ?",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        try:
            delete_user(self._selected_user, db_path=self.db_path)
            logger.info("Utilisateur '%s' supprimé.", self._selected_user)
            self._set_status(
                f"🗑  '{self._selected_user}' supprimé.", color="#e67e22"
            )
            self._selected_user = None
            self._refresh_user_list()
        except Exception as exc:
            logger.error("Erreur lors de la suppression : %s", exc)
            messagebox.showerror(
                "Erreur", f"Impossible de supprimer l'utilisateur : {exc}",
                parent=self,
            )

    # ---------------------------------------------------------------------- #
    # Liste des utilisateurs                                                  #
    # ---------------------------------------------------------------------- #

    def _refresh_user_list(self) -> None:
        """Recharge et affiche la liste des utilisateurs enrôlés."""
        # Supprime les anciens widgets
        for widget in self._user_listbox.winfo_children():
            widget.destroy()

        try:
            names: list[str] = list_user_names(db_path=self.db_path)
        except Exception as exc:
            logger.error("Impossible de charger la liste : %s", exc)
            names = []

        if not names:
            ctk.CTkLabel(
                self._user_listbox,
                text="Aucun utilisateur enrôlé.",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).grid(row=0, column=0, padx=10, pady=8, sticky="w")
            return

        for idx, name in enumerate(names):
            btn = ctk.CTkButton(
                self._user_listbox,
                text=f"  👤  {name}",
                font=ctk.CTkFont(size=13),
                height=36,
                anchor="w",
                fg_color="transparent",
                hover_color=("gray85", "gray25"),
                text_color=("gray10", "gray90"),
                command=lambda n=name: self._select_user(n),
            )
            btn.grid(row=idx, column=0, padx=4, pady=2, sticky="ew")

    def _select_user(self, name: str) -> None:
        """Met en surbrillance l'utilisateur sélectionné."""
        self._selected_user = name
        self._set_status(f"Sélectionné : {name}", color="gray")
        logger.debug("Utilisateur sélectionné : %s", name)

    # ---------------------------------------------------------------------- #
    # Helpers                                                                 #
    # ---------------------------------------------------------------------- #

    def _set_status(self, message: str, color: str = "gray") -> None:
        """Met à jour le label de statut."""
        self._status_label.configure(text=message, text_color=color)

    # ---------------------------------------------------------------------- #
    # Fermeture propre                                                        #
    # ---------------------------------------------------------------------- #

    def _on_close(self) -> None:
        """Libère les ressources avant de fermer la fenêtre."""
        logger.info("Fermeture de l'interface d'enrôlement…")
        self._preview_running = False
        release_detector()
        release_camera()
        self.destroy()


# ===========================================================================
# CLI + point d'entrée
# ===========================================================================

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="enrollment_ui",
        description="FaceLock — interface graphique d'enrôlement.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        metavar="CHEMIN",
        help="Chemin vers la base SQLite des embeddings.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logger.info("Lancement de l'interface d'enrôlement (db='%s').", args.db)
    app = EnrollmentApp(db_path=args.db)
    app.mainloop()


if __name__ == "__main__":
    main()
