#pragma once
#include <windows.h>
#include <string>

class PipeClient
{
public:
    PipeClient();
    ~PipeClient();
    std::string Authenticate(int timeoutMs = 15000);

private:
    static const wchar_t* PIPE_NAME;
    static const int MAX_RETRIES;
    static const int RETRY_DELAY_MS;
    HANDLE ConnectToPipe(int timeoutMs);
    std::string SendRequest(HANDLE hPipe, const std::string& request, int timeoutMs);
};
