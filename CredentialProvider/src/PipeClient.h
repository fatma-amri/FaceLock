// PipeClient.h - Named Pipe communication with FaceRecognitionService

#pragma once

#include <string>

class PipeClient
{
public:
    PipeClient();
    ~PipeClient();

    // Connect to named pipe and send authentication request
    // Returns: username if AUTH_SUCCESS, empty string if AUTH_FAILED
    std::string Authenticate(int timeoutMs = 15000);

private:
    static const wchar_t* PIPE_NAME;
    static const int MAX_RETRIES;
    static const int RETRY_DELAY_MS;

    // Helper to connect to pipe with retries
    HANDLE ConnectToPipe(int timeoutMs);

    // Helper to send request and read response
    std::string SendRequest(HANDLE hPipe, const std::string& request, int timeoutMs);
};
