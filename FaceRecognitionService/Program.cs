using System;
using System.Diagnostics;
using System.ServiceProcess;

namespace FaceLock.Service
{
    /// <summary>
    /// FaceRecognitionService - Windows Service for FaceLock biometric authentication.
    /// 
    /// This service:
    /// - Runs as a Windows Service (auto-start, SYSTEM account)
    /// - Creates a named pipe server at \\.\pipe\FacelookBiometric
    /// - Listens for authentication requests from the Credential Provider DLL
    /// - Calls the Python AI pipeline via subprocess
    /// - Returns authentication results through the named pipe
    /// - Logs all events to Windows Event Log
    /// 
    /// Service name: FaceRecognitionService
    /// Display name: FaceLock Recognition Service
    /// </summary>
    public static class Program
    {
        private static FaceRecognitionService _service;

        [STAThread]
        public static void Main(string[] args)
        {
            _service = new FaceRecognitionService();

            if (args.Length > 0 && args[0] == "-console")
            {
                // Debug mode: run in console instead of as service
                Console.WriteLine("[FaceRecognitionService] Running in console mode...");
                _service.OnStart(args);
                Console.WriteLine("[FaceRecognitionService] Service started. Press any key to stop...");
                Console.ReadKey();
                _service.OnStop();
                Console.WriteLine("[FaceRecognitionService] Service stopped.");
            }
            else
            {
                // Normal service mode
                ServiceBase.Run(_service);
            }
        }
    }

    /// <summary>
    /// FaceRecognitionService implementation.
    /// Inherits from ServiceBase to become a Windows Service.
    /// </summary>
    public class FaceRecognitionService : ServiceBase
    {
        private PipeServer _pipeServer;
        private System.Timers.Timer _watchdogTimer;

        public FaceRecognitionService()
        {
            ServiceName = "FaceRecognitionService";
            DisplayName = "FaceLock Recognition Service";
            Description = "Biometric authentication service for FaceLock";
            
            CanStop = true;
            CanPauseAndContinue = false;
            AutoLog = true;
            
            // Log to Windows Event Log
            if (!EventLog.SourceExists(ServiceName))
            {
                EventLog.CreateEventSource(ServiceName, "Application");
            }
            EventLog.Source = ServiceName;
        }

        /// <summary>
        /// Called when the service starts.
        /// </summary>
        protected override void OnStart(string[] args)
        {
            try
            {
                EventLog.WriteEntry(
                    ServiceName,
                    "FaceRecognitionService is starting...",
                    EventLogEntryType.Information
                );

                // Initialize the named pipe server
                _pipeServer = new PipeServer();
                _pipeServer.Start();

                // Start watchdog timer to monitor service health (every 30 seconds)
                _watchdogTimer = new System.Timers.Timer(30000);
                _watchdogTimer.Elapsed += (s, e) => Watchdog_Tick();
                _watchdogTimer.Start();

                EventLog.WriteEntry(
                    ServiceName,
                    "FaceRecognitionService started successfully.",
                    EventLogEntryType.Information
                );
            }
            catch (Exception ex)
            {
                EventLog.WriteEntry(
                    ServiceName,
                    $"Failed to start service: {ex.Message}\n{ex.StackTrace}",
                    EventLogEntryType.Error
                );
                throw;
            }
        }

        /// <summary>
        /// Called when the service stops.
        /// </summary>
        protected override void OnStop()
        {
            try
            {
                EventLog.WriteEntry(
                    ServiceName,
                    "FaceRecognitionService is stopping...",
                    EventLogEntryType.Information
                );

                _watchdogTimer?.Stop();
                _watchdogTimer?.Dispose();

                _pipeServer?.Stop();

                EventLog.WriteEntry(
                    ServiceName,
                    "FaceRecognitionService stopped successfully.",
                    EventLogEntryType.Information
                );
            }
            catch (Exception ex)
            {
                EventLog.WriteEntry(
                    ServiceName,
                    $"Error stopping service: {ex.Message}",
                    EventLogEntryType.Error
                );
            }
        }

        /// <summary>
        /// Watchdog timer to ensure service health.
        /// </summary>
        private void Watchdog_Tick()
        {
            try
            {
                if (_pipeServer != null && !_pipeServer.IsRunning)
                {
                    EventLog.WriteEntry(
                        ServiceName,
                        "Pipe server is not running. Restarting...",
                        EventLogEntryType.Warning
                    );
                    _pipeServer.Start();
                }
            }
            catch (Exception ex)
            {
                EventLog.WriteEntry(
                    ServiceName,
                    $"Watchdog error: {ex.Message}",
                    EventLogEntryType.Error
                );
            }
        }
    }
}
