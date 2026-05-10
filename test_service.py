import sys, os
sys.path.insert(0, 'C:\\Users\\windows\\Desktop\\FaceLock')
os.chdir('C:\\Users\\windows\\Desktop\\FaceLock')
from modules.face_authenticator import get_all_users
users = get_all_users('C:\\Users\\windows\\Desktop\\FaceLock\\data\\db\\facelock.db')
print('Users:', [u[0] for u in users])
if users:
    import cv2
    os.environ['OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS'] = '0'
    cap = cv2.VideoCapture(0, cv2.CAP_MSMF)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    for i in range(5): ret, frame = cap.read()
    cap.release()
    from modules.face_authenticator import authenticate
    result = authenticate(frame, db_path='C:\\Users\\windows\\Desktop\\FaceLock\\data\\db\\facelock.db')
    print('Auth:', result)
