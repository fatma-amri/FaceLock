import sys
sys.path.insert(0, '.')
from modules.face_authenticator import get_all_users
users = get_all_users('data/db/facelock.db')
print('Users visible to service:', [u[0] for u in users])
