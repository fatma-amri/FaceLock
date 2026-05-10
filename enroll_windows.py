"""
Enroll a face as 'windows' using the confirmed-working MSMF+MJPG camera.
Run this script, look at the webcam, press Enter when ready.
"""
import os
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'

import sys
sys.path.insert(0, '.')

import cv2
import numpy as np
from modules.face_detector import detect_and_align, release_detector
from modules.face_encoder import encode_face
from modules.database import add_user, DEFAULT_DB_PATH

USERNAME = 'windows'
DB_PATH = DEFAULT_DB_PATH
ATTEMPTS = 10

def capture_frame():
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    frame = None
    for i in range(ATTEMPTS):
        ret, f = cap.read()
        if ret:
            frame = f
    cap.release()
    return frame

print(f"Enrolling face for user '{USERNAME}'")
print("Look at the webcam, then press Enter...")
input()

print("Capturing frame...")
frame = capture_frame()
if frame is None:
    print("ERROR: camera returned no frame")
    sys.exit(1)
print(f"Frame captured: {frame.shape}")

print("Detecting and aligning face...")
aligned = detect_and_align(frame)
if aligned is None:
    print("ERROR: no face detected in frame — make sure your face is visible")
    release_detector()
    sys.exit(1)
print(f"Face aligned: {aligned.shape}")

print("Encoding face...")
embedding = encode_face(aligned)
if embedding is None:
    print("ERROR: face encoding failed")
    release_detector()
    sys.exit(1)
print(f"Embedding shape: {np.array(embedding).shape}")

print(f"Storing in DB as '{USERNAME}'...")
add_user(USERNAME, embedding, db_path=DB_PATH)

release_detector()
print(f"Done! '{USERNAME}' enrolled successfully.")

# Verify
import sqlite3
con = sqlite3.connect(DB_PATH)
rows = con.execute("SELECT id, name, created_at FROM users").fetchall()
for r in rows:
    print(f"  DB: id={r[0]} name={r[1]!r} at={r[2]}")
con.close()
