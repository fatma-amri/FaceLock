import cv2, sys, numpy as np
sys.path.insert(0, '.')
img = cv2.imread('C:\\captured.jpg')
from modules.face_detector import detect_and_align
from modules.face_authenticator import encode_face, get_all_users
aligned = detect_and_align(img)
print('Aligned:', aligned.shape)
embedding = encode_face(aligned)
print('Embedding norm:', np.linalg.norm(embedding))
users = get_all_users('data/db/facelock.db')
print('Users:', [u[0] for u in users])
for name, known_emb in users:
    dist = float(np.linalg.norm(known_emb - embedding))
    print(f'Distance to {name}: {dist:.4f}')
