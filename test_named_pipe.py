"""Test the FacelookBiometric named pipe directly (synchronous I/O, no OVERLAPPED)."""
import ctypes, time, sys

PIPE_NAME = r'\\.\pipe\FacelookBiometric'
GENERIC_READ_WRITE = 0xC0000000
OPEN_EXISTING = 3

kernel32 = ctypes.windll.kernel32

print(f"Connecting to {PIPE_NAME!r}")
print("Waiting for pipe server (up to 10s)...")
ok = kernel32.WaitNamedPipeW(PIPE_NAME, 10000)
if not ok:
    print(f"WaitNamedPipeW failed: error={kernel32.GetLastError()}")
    sys.exit(1)

hPipe = kernel32.CreateFileW(PIPE_NAME, GENERIC_READ_WRITE, 0, None, OPEN_EXISTING, 0, None)
if ctypes.c_longlong(hPipe).value == -1:
    print(f"CreateFileW failed: error={kernel32.GetLastError()}")
    sys.exit(1)

print("Connected. Sending AUTH_REQUEST...")
msg = b'AUTH_REQUEST\n'
written = ctypes.c_ulong(0)
ret = kernel32.WriteFile(hPipe, msg, len(msg), ctypes.byref(written), None)
if not ret:
    print(f"WriteFile failed: error={kernel32.GetLastError()}")
    kernel32.CloseHandle(hPipe)
    sys.exit(1)
print(f"Wrote {written.value} bytes")

buf = ctypes.create_string_buffer(512)
nread = ctypes.c_ulong(0)

# Synchronous read — blocks until data arrives or pipe closes
t1 = time.time()
ret2 = kernel32.ReadFile(hPipe, buf, 512, ctypes.byref(nread), None)
elapsed = time.time() - t1

if ret2:
    resp = buf.raw[:nread.value].decode('utf-8', errors='replace').strip()
    print(f"Response after {elapsed:.2f}s ({nread.value} bytes): [{resp}]")
else:
    print(f"ReadFile failed after {elapsed:.2f}s: error={kernel32.GetLastError()}")

kernel32.CloseHandle(hPipe)
