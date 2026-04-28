// PipeClient.cpp - Named Pipe communication implementation

#include "PipeClient.h"
#include <windows.h>
#include <cstring>
#include <sstream>

const wchar_t* PipeClient::PIPE_NAME = L"\\\\.\\pipe\\FacelookBiometric";
const int PipeClient::MAX_RETRIES = 3;
const int PipeClient::RETRY_DELAY_MS = 500;

PipeClient::PipeClient() {}

PipeClient::~PipeClient() {}

std::string PipeClient::Authenticate(int timeoutMs)
{
    HANDLE hPipe = ConnectToPipe(timeoutMs);
    if (hPipe == INVALID_HANDLE_VALUE)
        return "";

    std::string result = SendRequest(hPipe, "AUTH_REQUEST", timeoutMs);
    CloseHandle(hPipe);

    return result;
}

HANDLE PipeClient::ConnectToPipe(int timeoutMs)
{
    // Try multiple times to connect (service might be starting)
    for (int i = 0; i < MAX_RETRIES; ++i)
    {
        HANDLE hPipe = CreateFileW(
            PIPE_NAME,
            GENERIC_READ | GENERIC_WRITE,
            0,
            NULL,
            OPEN_EXISTING,
            FILE_FLAG_OVERLAPPED,
            NULL
        );

        if (hPipe != INVALID_HANDLE_VALUE)
        {
            // Set to message mode
            DWORD dwMode = PIPE_READMODE_MESSAGE;
            if (SetNamedPipeHandleState(hPipe, &dwMode, NULL, NULL))
            {
                return hPipe;
            }
            CloseHandle(hPipe);
        }

        if (i < MAX_RETRIES - 1)
        {
            Sleep(RETRY_DELAY_MS);
        }
    }

    return INVALID_HANDLE_VALUE;
}

std::string PipeClient::SendRequest(HANDLE hPipe, const std::string& request, int timeoutMs)
{
    // Send request
    DWORD dwBytesWritten = 0;
    if (!WriteFile(hPipe, request.c_str(), (DWORD)request.length(), &dwBytesWritten, NULL))
    {
        return "";
    }

    // Read response with timeout
    OVERLAPPED overlapped = {};
    overlapped.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);

    if (!overlapped.hEvent)
        return "";

    char buffer[256] = {};
    DWORD dwBytesRead = 0;

    if (ReadFile(hPipe, buffer, sizeof(buffer) - 1, &dwBytesRead, &overlapped))
    {
        // Data available immediately
        CloseHandle(overlapped.hEvent);
        return std::string(buffer, dwBytesRead);
    }

    // Wait for data with timeout
    DWORD dwResult = WaitForSingleObject(overlapped.hEvent, timeoutMs);

    if (dwResult == WAIT_OBJECT_0)
    {
        if (GetOverlappedResult(hPipe, &overlapped, &dwBytesRead, FALSE))
        {
            CloseHandle(overlapped.hEvent);
            return std::string(buffer, dwBytesRead);
        }
    }

    CloseHandle(overlapped.hEvent);
    return "";
}
