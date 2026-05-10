import cv2, sys
sys.path.insert(0, '.')
img = cv2.imread('C:\\captured.jpg')
print('Image shape:', img.shape)
from modules.face_detector import detect_and_align
result = detect_and_align(img)
print('Face detected:', result is not None)
if result is not None:
    print('Aligned shape:', result.shape)
else:
    print('NO FACE DETECTED in captured image')
