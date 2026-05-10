"""Quick end-to-end test: start face_authenticator_pipe.py as subprocess, send AUTH_REQUEST."""
import subprocess, sys, time, threading

py = r"C:\Users\windows\Desktop\FaceLock\.venv\Scripts\python.exe"
script = r"C:\Users\windows\Desktop\FaceLock\face_authenticator_pipe.py"

proc = subprocess.Popen(
    [py, script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace",
    cwd=r"C:\Users\windows\Desktop\FaceLock",
)

stderr_lines = []
def drain_stderr():
    for line in proc.stderr:
        stderr_lines.append(line.rstrip())
        print(f"  [stderr] {line.rstrip()}", flush=True)
t = threading.Thread(target=drain_stderr, daemon=True)
t.start()

print("Waiting for READY (up to 60s)...", flush=True)
t0 = time.time()
ready_line = proc.stdout.readline().strip()
elapsed = time.time() - t0
print(f"Got stdout after {elapsed:.1f}s: {ready_line!r}", flush=True)

if ready_line == "READY":
    print("Sending AUTH_REQUEST...", flush=True)
    proc.stdin.write("AUTH_REQUEST\n")
    proc.stdin.flush()
    t1 = time.time()
    resp = proc.stdout.readline().strip()
    elapsed2 = time.time() - t1
    print(f"Auth response after {elapsed2:.2f}s: {resp!r}", flush=True)

    proc.stdin.write("SHUTDOWN\n")
    proc.stdin.flush()
else:
    print(f"ERROR: expected READY, got {ready_line!r}", flush=True)
    proc.kill()

proc.wait(timeout=10)
print(f"Exit code: {proc.returncode}", flush=True)
