# store_password.py
# Run once as Administrator to store the Windows password
# Usage: python store_password.py [username] [password]
import ctypes
import ctypes.wintypes
import sys
import os


CRYPTPROTECT_LOCAL_MACHINE = 4  # any process on this machine can decrypt


def store_password_dpapi(username, password):
    """Store password encrypted with DPAPI in C:\\ProgramData\\FaceLock\\creds.bin"""
    DATA_DIR = r"C:\ProgramData\FaceLock"
    os.makedirs(DATA_DIR, exist_ok=True)

    crypt32 = ctypes.windll.crypt32

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    data = password.encode("utf-16-le")
    buf = (ctypes.c_ubyte * len(data))(*data)
    input_blob = DATA_BLOB(len(data), buf)
    output_blob = DATA_BLOB()

    result = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "FaceLock",
        None, None, None,
        CRYPTPROTECT_LOCAL_MACHINE,  # allows LocalSystem service to decrypt
        ctypes.byref(output_blob)
    )

    if result:
        encrypted = bytes(output_blob.pbData[:output_blob.cbData])
        cred_file = os.path.join(DATA_DIR, "creds.bin")
        username_bytes = username.encode("utf-8")
        with open(cred_file, "wb") as f:
            f.write(len(username_bytes).to_bytes(4, "little"))
            f.write(username_bytes)
            f.write(len(encrypted).to_bytes(4, "little"))
            f.write(encrypted)
        print(f"Password stored for user: {username}")
        print(f"Credential file: {cred_file}")
        return True
    else:
        err = ctypes.GetLastError()
        print(f"Failed to encrypt password (error {err})")
        return False


if __name__ == "__main__":
    print("FaceLock Password Store — run as Administrator")
    if len(sys.argv) == 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username = input("Enter Windows username: ").strip()
        password = input("Enter Windows password: ").strip()
    if not username or not password:
        print("Username and password are required.")
        sys.exit(1)
    ok = store_password_dpapi(username, password)
    sys.exit(0 if ok else 1)
