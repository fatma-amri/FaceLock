import os, sys, datetime

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S.%f')
    print(f'[{ts}] {msg}', flush=True)

log('START')
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'
import cv2
log('cv2 imported')

cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
log(f'Camera opened: {cap.isOpened()}')

frame = None
for i in range(5):
    ret, f = cap.read()
    log(f'Read {i}: ret={ret}')
    if ret:
        frame = f
        break
cap.release()

if frame is None:
    log('FAILED: no frame')
    sys.exit()

log(f'Frame OK: {frame.shape}')
from modules.face_authenticator import authenticate
result = authenticate(frame, db_path='data/db/facelock.db')
log(f'Auth result: {result}')
