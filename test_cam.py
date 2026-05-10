import os, cv2
os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'
cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
for i in range(10):
    ret, frame = cap.read()
    print(f'read {i}: ret={ret}')
cap.release()
if ret:
    cv2.imwrite('C:\\\\captured.jpg', frame)
    print('Saved to C:\\\\captured.jpg')
