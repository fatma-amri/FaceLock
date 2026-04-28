using System;
using System.Diagnostics;
using System.IO.Pipes;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace FaceLock.Service
{
    /// <summary>
    /// PipeServer - Named Pipe server for credential provider communication.
    /// 
    /// Protocol:
    /// - Client sends: AUTH_REQUEST
    /// - Server responds: AUTH_SUCCESS:<username> or AUTH_FAILED
    /// 
    /// Pipe name: \\.\pipe\FacelookBiometric
    /// </summary>
    public class PipeServer
    {
        private const string PipeName = "FacelookBiometric";
        private const int MaxConnections = 10;
        private volatile bool _isRunning;
        private NamedPipeServerStream _pipeServer;
        private Thread _pipeThread;

        public bool IsRunning => _isRunning;

        public void Start()
        {
            if (_isRunning)
                return;

            _isRunning = true;
            _pipeThread = new Thread(PipeServerLoop)
            {
                IsBackground = true,
                Name = "PipeServerThread"
            };
            _pipeThread.Start();

            Debug.WriteLine($"[PipeServer] Started listening on \\\\.\pipe\\{PipeName}");
        }

        public void Stop()
        {
            _isRunning = false;
            _pipeServer?.Close();
            _pipeServer?.Dispose();
            _pipeThread?.Join(5000);

            Debug.WriteLine("[PipeServer] Stopped");
        }

        /// <summary>
        /// Main pipe server loop - listens for client connections.
        /// </summary>
        private void PipeServerLoop()
        {
            try
            {
                while (_isRunning)
                {
                    try
                    {
                        _pipeServer = new NamedPipeServerStream(
                            PipeName,
                            PipeDirection.InOut,
                            MaxConnections,
                            PipeTransmissionMode.Message
                        );

                        Debug.WriteLine("[PipeServer] Waiting for client connection...");
                        _pipeServer.WaitForConnection();

                        if (_isRunning)
                        {
                            Task.Run(() => HandleClientConnection(_pipeServer));
                        }
                    }
                    catch (IOException ex)
                    {
                        // Pipe closed - this is normal
                        Debug.WriteLine($"[PipeServer] Client disconnected: {ex.Message}");
                    }
                    catch (ObjectDisposedException)
                    {
                        // Service is stopping
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] Error in pipe loop: {ex.Message}");
            }
        }

        /// <summary>
        /// Handle a single client connection.
        /// </summary>
        private void HandleClientConnection(NamedPipeServerStream pipeServer)
        {
            try
            {
                using (var reader = new StreamReader(pipeServer, Encoding.UTF8))
                using (var writer = new StreamWriter(pipeServer, Encoding.UTF8))
                {
                    // Read request from client
                    string request = reader.ReadLine();
                    Debug.WriteLine($"[PipeServer] Received: {request}");

                    if (request == "AUTH_REQUEST")
                    {
                        // Call Python AI pipeline
                        string result = CallPythonAuthenticator();
                        
                        // Send response
                        writer.WriteLine(result);
                        writer.Flush();
                        
                        Debug.WriteLine($"[PipeServer] Sent: {result}");
                    }
                    else
                    {
                        writer.WriteLine("AUTH_FAILED");
                        writer.Flush();
                    }
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] Error handling client: {ex.Message}");
            }
        }

        /// <summary>
        /// Call the Python face_authenticator_pipe.py subprocess.
        /// </summary>
        private string CallPythonAuthenticator()
        {
            try
            {
                // Path to Python executable and script
                // Assumes FaceLock is installed in C:\Program Files\FaceLock
                string pythonExe = @"C:\Program Files\FaceLock\.venv\Scripts\python.exe";
                string scriptPath = @"C:\Program Files\FaceLock\face_authenticator_pipe.py";

                if (!File.Exists(pythonExe))
                {
                    pythonExe = "python";  // Fallback to system Python
                }

                var processInfo = new ProcessStartInfo
                {
                    FileName = pythonExe,
                    Arguments = $"\"{scriptPath}\"",
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                    CreateNoWindow = true,
                    StandardOutputEncoding = Encoding.UTF8,
                    StandardErrorEncoding = Encoding.UTF8,
                };

                using (var process = Process.Start(processInfo))
                {
                    // Wait max 12 seconds for Python subprocess
                    if (!process.WaitForExit(12000))
                    {
                        process.Kill();
                        return "AUTH_FAILED";
                    }

                    string output = process.StandardOutput.ReadToEnd().Trim();
                    string error = process.StandardError.ReadToEnd();

                    if (!string.IsNullOrEmpty(error))
                    {
                        Debug.WriteLine($"[PipeServer] Python stderr: {error}");
                    }

                    return string.IsNullOrEmpty(output) ? "AUTH_FAILED" : output;
                }
            }
            catch (Exception ex)
            {
                Debug.WriteLine($"[PipeServer] Error calling Python: {ex.Message}");
                return "AUTH_FAILED";
            }
        }
    }
}
