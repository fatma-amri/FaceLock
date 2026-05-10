using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace FaceLock.Service
{
    /// <summary>
    /// PipeServer - Named Pipe server for credential provider communication.
    ///
    /// Protocol:
    ///   Client sends:    AUTH_REQUEST
    ///   Server responds: AUTH_SUCCESS:&lt;username&gt;:&lt;password&gt;  or  AUTH_FAILED
    ///
    /// Pipe name: \\.\pipe\FacelookBiometric
    ///
    /// Python process is started ONCE at service startup.  Models are loaded
    /// during warmup so each AUTH_REQUEST is served in &lt; 1 second.
    /// C++ DLL enforces a 4-second end-to-end timeout; this class enforces
    /// a 3-second timeout on the Python response so the DLL always gets an
    /// answer before its deadline.
    /// </summary>
    public class PipeServer
    {
        private const string PipeName = "FacelookBiometric";
        private const int MaxConnections = 10;
        private const string CredFile = @"C:\ProgramData\FaceLock\creds.bin";

        private volatile bool _isRunning;
        private NamedPipeServerStream _pipeServer;
        private Thread _pipeThread;

        // Persistent Python process
        private Process      _pythonProcess;
        private StreamWriter _pythonWriter;
        private StreamReader _pythonReader;
        private volatile bool _pythonReady;
        private readonly object _pythonLock = new object();

        public bool IsRunning => _isRunning;

        // ------------------------------------------------------------------ //
        //  Start / Stop
        // ------------------------------------------------------------------ //

        public void Start()
        {
            if (_isRunning)
                return;

            _isRunning = true;

            // Launch Python in the background so OnStart() returns quickly.
            // AUTH_REQUESTs that arrive before _pythonReady is true will get
            // AUTH_FAILED — the DLL falls back to password gracefully.
            Task.Run(() => LaunchPythonProcess());

            _pipeThread = new Thread(PipeServerLoop)
            {
                IsBackground = true,
                Name = "PipeServerThread"
            };
            _pipeThread.Start();

            Debug.WriteLine($"[PipeServer] Started on \\\\.\\pipe\\{PipeName}");
        }

        public void Stop()
        {
            _isRunning = false;

            // Ask Python to exit cleanly
            try
            {
                lock (_pythonLock)
                {
                    if (_pythonProcess != null && !_pythonProcess.HasExited)
                    {
                        _pythonWriter?.WriteLine("SHUTDOWN");
                        _pythonWriter?.Flush();
                    }
                }
                _pythonProcess?.WaitForExit(3000);
                if (_pythonProcess != null && !_pythonProcess.HasExited)
                    _pythonProcess.Kill();
            }
            catch { /* best-effort */ }

            _pipeServer?.Close();
            _pipeServer?.Dispose();
            _pipeThread?.Join(5000);

            Debug.WriteLine("[PipeServer] Stopped");
        }

        // ------------------------------------------------------------------ //
        //  Python process lifecycle
        // ------------------------------------------------------------------ //

        private void LaunchPythonProcess()
        {
            try
            {
                string pythonExe  = @"C:\Users\windows\Desktop\FaceLock\.venv\Scripts\python.exe";
                string scriptPath = @"C:\Users\windows\Desktop\FaceLock\face_authenticator_pipe.py";

                if (!File.Exists(pythonExe))
                    pythonExe = "python";

                var psi = new ProcessStartInfo
                {
                    FileName               = pythonExe,
                    Arguments              = $"\"{scriptPath}\"",
                    UseShellExecute        = false,
                    RedirectStandardInput  = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError  = true,
                    CreateNoWindow         = true,
                    WorkingDirectory       = @"C:\Users\windows\Desktop\FaceLock",
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding  = Encoding.UTF8,
                };

                var proc = Process.Start(psi);

                // Assign fields before starting background readers
                lock (_pythonLock)
                {
                    _pythonProcess = proc;
                    _pythonWriter  = proc.StandardInput;
                    _pythonReader  = proc.StandardOutput;
                    _pythonReady   = false;
                }

                Debug.WriteLine("[PipeServer] Python process started, waiting for READY...");

                // Drain stderr so the Python process never blocks on it
                Task.Run(() =>
                {
                    try
                    {
                        string line;
                        while ((line = proc.StandardError.ReadLine()) != null)
                            Debug.WriteLine($"[Python] {line}");
                    }
                    catch { /* process ended */ }
                });

                // Wait for "READY" — Python prints this after loading models
                // (can take up to ~20 s on first run with cold disk cache)
                var readTask = Task.Run(() =>
                {
                    try { return proc.StandardOutput.ReadLine(); }
                    catch { return null; }
                });

                if (readTask.Wait(25000) && readTask.Result == "READY")
                {
                    lock (_pythonLock)
                        _pythonReady = true;

                    Debug.WriteLine("[PipeServer] Python models ready — authentication enabled.");
                }
                else
                {
                    Debug.WriteLine($"[PipeServer] Python warmup timed out or returned: '{readTask.Result}'");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] LaunchPythonProcess error: {ex.Message}");
            }
        }

        // ------------------------------------------------------------------ //
        //  Named-pipe server loop
        // ------------------------------------------------------------------ //

        private void PipeServerLoop()
        {
            try
            {
                while (_isRunning)
                {
                    try
                    {
                        var pipe = new NamedPipeServerStream(
                            PipeName,
                            PipeDirection.InOut,
                            MaxConnections,
                            PipeTransmissionMode.Message
                        );
                        _pipeServer = pipe;  // stored for Stop()

                        Debug.WriteLine("[PipeServer] Waiting for client connection...");
                        pipe.WaitForConnection();

                        if (_isRunning)
                            Task.Run(() => HandleClientConnection(pipe));
                        else
                            pipe.Dispose();
                    }
                    catch (IOException ex)
                    {
                        Debug.WriteLine($"[PipeServer] Client disconnected: {ex.Message}");
                    }
                    catch (ObjectDisposedException)
                    {
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] Error in pipe loop: {ex.Message}");
            }
        }

        // ------------------------------------------------------------------ //
        //  Handle one client connection
        // ------------------------------------------------------------------ //

        private void HandleClientConnection(NamedPipeServerStream pipeStream)
        {
            try
            {
                // UTF8Encoding(false) = no BOM preamble.
                // Encoding.UTF8 writes the BOM as a separate pipe message in
                // message-mode, which confuses the C++ DLL's ReadFile call.
                using (var reader = new StreamReader(pipeStream, new UTF8Encoding(false)))
                using (var writer = new StreamWriter(pipeStream, new UTF8Encoding(false)))
                {
                    string request = reader.ReadLine();
                    Debug.WriteLine($"[PipeServer] Received: {request}");

                    string response = "AUTH_FAILED";

                    if (request == "AUTH_REQUEST")
                    {
                        string pythonResult = CallPythonAuthenticator();
                        Debug.WriteLine($"[PipeServer] Python result: {pythonResult}");

                        if (pythonResult != null && pythonResult.StartsWith("AUTH_SUCCESS:"))
                        {
                            string username = pythonResult.Substring(13).Trim();
                            string password = ReadStoredPassword(username);

                            if (password != null)
                            {
                                response = $"AUTH_SUCCESS:{username}:{password}";
                                Debug.WriteLine($"[PipeServer] Auth success for user: {username}");
                            }
                            else
                            {
                                Debug.WriteLine($"[PipeServer] No stored password for: {username}");
                            }
                        }
                    }

                    writer.WriteLine(response);
                    writer.Flush();
                    Debug.WriteLine($"[PipeServer] Sent: {response.Substring(0, Math.Min(response.Length, 60))}");
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] HandleClientConnection error: {ex.Message}");
            }
        }

        // ------------------------------------------------------------------ //
        //  Call the persistent Python process
        // ------------------------------------------------------------------ //

        private string CallPythonAuthenticator()
        {
            lock (_pythonLock)
            {
                try
                {
                    // Restart Python if it has died
                    if (_pythonProcess == null || _pythonProcess.HasExited)
                    {
                        Debug.WriteLine("[PipeServer] Python process not running — restarting in background");
                        // Release the lock before the blocking LaunchPythonProcess call
                        // by scheduling it asynchronously and returning AUTH_FAILED now.
                        Task.Run(() => LaunchPythonProcess());
                        return "AUTH_FAILED";
                    }

                    if (!_pythonReady)
                    {
                        Debug.WriteLine("[PipeServer] Python not ready yet — returning AUTH_FAILED");
                        return "AUTH_FAILED";
                    }

                    // Send request to persistent Python process
                    _pythonWriter.WriteLine("AUTH_REQUEST");
                    _pythonWriter.Flush();

                    // Read response with 6-second timeout.
                    // Python tries camera for up to 2s then returns.  The C++ DLL
                    // has a 4-second end-to-end deadline; if it fires first, that is
                    // fine — we still get the Python response and don't kill Python.
                    var responseTask = Task.Run(() =>
                    {
                        try { return _pythonReader.ReadLine(); }
                        catch { return null; }
                    });

                    if (responseTask.Wait(6000) && responseTask.Result != null)
                    {
                        string result = responseTask.Result.Trim();
                        Debug.WriteLine($"[PipeServer] Python response: {result}");
                        return result;
                    }
                    else
                    {
                        Debug.WriteLine("[PipeServer] Python response timeout — killing and restarting");
                        try { _pythonProcess?.Kill(); } catch { }
                        _pythonProcess = null;
                        _pythonReady   = false;
                        Task.Run(() => LaunchPythonProcess());
                        return "AUTH_FAILED";
                    }
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"[PipeServer] CallPythonAuthenticator error: {ex.Message}");
                    return "AUTH_FAILED";
                }
            }
        }

        // ------------------------------------------------------------------ //
        //  Credential storage (unchanged)
        // ------------------------------------------------------------------ //

        /// <summary>
        /// Reads and DPAPI-decrypts the stored password from creds.bin.
        /// File layout: [4b username-len][username UTF-8][4b encrypted-len][encrypted data]
        /// Encrypted with CRYPTPROTECT_LOCAL_MACHINE so LocalSystem can decrypt.
        /// </summary>
        private string ReadStoredPassword(string username)
        {
            try
            {
                if (!File.Exists(CredFile))
                {
                    Debug.WriteLine($"[PipeServer] Credential file not found: {CredFile}");
                    return null;
                }

                byte[] data = File.ReadAllBytes(CredFile);
                if (data.Length < 8)
                    return null;

                int userLen = BitConverter.ToInt32(data, 0);
                if (userLen < 0 || 4 + userLen + 4 > data.Length)
                    return null;

                string storedUser = Encoding.UTF8.GetString(data, 4, userLen);
                if (!string.Equals(storedUser, username, StringComparison.Ordinal))
                {
                    Debug.WriteLine($"[PipeServer] Username mismatch: stored='{storedUser}' requested='{username}'");
                    return null;
                }

                int encOffset = 4 + userLen;
                int encLen    = BitConverter.ToInt32(data, encOffset);
                if (encLen <= 0 || encOffset + 4 + encLen > data.Length)
                    return null;

                byte[] encrypted = new byte[encLen];
                Array.Copy(data, encOffset + 4, encrypted, 0, encLen);

                byte[] decrypted = ProtectedData.Unprotect(
                    encrypted, null, DataProtectionScope.LocalMachine);

                return Encoding.Unicode.GetString(decrypted);
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] ReadStoredPassword error: {ex.Message}");
                return null;
            }
        }
    }
}
