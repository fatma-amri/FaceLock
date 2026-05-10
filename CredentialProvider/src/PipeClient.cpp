// PipeClient.cpp - Named Pipe communication with non-blocking OVERLAPPED I/O
//
// Hard 15-second timeout on every operation.
// Returns "AUTH_FAILED" on any error or timeout — never blocks LogonUI.

#include "PipeClient.h"
#include <windows.h>
#include <cstring>
#include <stdarg.h>

const wchar_t* PipeClient::PIPE_NAME   = L"\\\\.\\pipe\\FacelookBiometric";
const int      PipeClient::MAX_RETRIES    = 3;
const int      PipeClient::RETRY_DELAY_MS = 500;

// ---------------------------------------------------------------------------
// Debug logging — C:\FaceLock_debug.txt, timestamped
// ---------------------------------------------------------------------------
static void PipeDbgLog(const char* fmt, ...)
{
    HANDLE hFile = CreateFileA(
        "C:\\FaceLock_debug.txt",
        FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return;

    SYSTEMTIME st;
    GetLocalTime(&st);

    char msg[512];
    va_list args;
    va_start(args, fmt);
    wvsprintfA(msg, fmt, args);
    va_end(args);

    char buf[600];
    int len = wsprintfA(buf, "[%02d:%02d:%02d.%03d] PIPE %s\r\n",
        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, msg);
    DWORD written;
    WriteFile(hFile, buf, (DWORD)len, &written, NULL);
    CloseHandle(hFile);
}

// ---------------------------------------------------------------------------

PipeClient::PipeClient()  {}
PipeClient::~PipeClient() {}

// ---------------------------------------------------------------------------
// Authenticate — the only public method used by FacelookCredential.
//
// Ignores caller-supplied timeoutMs; always uses HARD_TIMEOUT_MS (15 s).
// Returns the raw response string (e.g. "AUTH_SUCCESS:user:pass") or
// "AUTH_FAILED" on any error, timeout, or unavailable service.
// ---------------------------------------------------------------------------
std::string PipeClient::Authenticate(int /*timeoutMs*/)
{
    const DWORD TIMEOUT_MS = 15000;

    PipeDbgLog("Authenticate: start");

    // ---- Step 1: Wait up to 15 s for the pipe to be available ----
    if (!WaitNamedPipeW(PIPE_NAME, TIMEOUT_MS))
    {
        PipeDbgLog("Authenticate: WaitNamedPipe failed err=%d -> AUTH_FAILED",
                   (int)GetLastError());
        return "AUTH_FAILED";
    }
    PipeDbgLog("Authenticate: WaitNamedPipe OK");

    // ---- Step 2: Open pipe with OVERLAPPED flag ----
    HANDLE hPipe = CreateFileW(
        PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE,
        0, NULL,
        OPEN_EXISTING,
        FILE_FLAG_OVERLAPPED,
        NULL);

    if (hPipe == INVALID_HANDLE_VALUE)
    {
        PipeDbgLog("Authenticate: CreateFile failed err=%d -> AUTH_FAILED",
                   (int)GetLastError());
        return "AUTH_FAILED";
    }
    PipeDbgLog("Authenticate: CreateFile OK hPipe=%p", (void*)hPipe);

    // Switch to message-read mode
    DWORD dwMode = PIPE_READMODE_MESSAGE;
    if (!SetNamedPipeHandleState(hPipe, &dwMode, NULL, NULL))
    {
        PipeDbgLog("Authenticate: SetPipeState failed err=%d -> AUTH_FAILED",
                   (int)GetLastError());
        CloseHandle(hPipe);
        return "AUTH_FAILED";
    }

    std::string result = "AUTH_FAILED";

    // ---- Step 3: Write "AUTH_REQUEST" via OVERLAPPED ----
    {
        OVERLAPPED ov = {};
        ov.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
        if (!ov.hEvent)
        {
            PipeDbgLog("Authenticate: CreateEvent(write) failed -> AUTH_FAILED");
            CloseHandle(hPipe);
            return "AUTH_FAILED";
        }

        const char request[] = "AUTH_REQUEST";
        DWORD cbReq = (DWORD)(sizeof(request) - 1); // exclude null terminator
        DWORD dwWritten = 0;

        BOOL ok = WriteFile(hPipe, request, cbReq, &dwWritten, &ov);
        if (!ok)
        {
            DWORD err = GetLastError();
            if (err == ERROR_IO_PENDING)
            {
                PipeDbgLog("Authenticate: WriteFile pending, waiting...");
                DWORD wr = WaitForSingleObject(ov.hEvent, TIMEOUT_MS);
                if (wr == WAIT_OBJECT_0)
                {
                    if (!GetOverlappedResult(hPipe, &ov, &dwWritten, FALSE))
                    {
                        PipeDbgLog("Authenticate: WriteFile GetOverlapped failed err=%d -> AUTH_FAILED",
                                   (int)GetLastError());
                        CancelIo(hPipe);
                        CloseHandle(ov.hEvent);
                        CloseHandle(hPipe);
                        return "AUTH_FAILED";
                    }
                }
                else
                {
                    PipeDbgLog("Authenticate: WriteFile timeout wr=%d -> AUTH_FAILED", (int)wr);
                    CancelIo(hPipe);
                    CloseHandle(ov.hEvent);
                    CloseHandle(hPipe);
                    return "AUTH_FAILED";
                }
            }
            else
            {
                PipeDbgLog("Authenticate: WriteFile failed err=%d -> AUTH_FAILED", (int)err);
                CloseHandle(ov.hEvent);
                CloseHandle(hPipe);
                return "AUTH_FAILED";
            }
        }

        PipeDbgLog("Authenticate: wrote %d bytes OK", (int)dwWritten);
        CloseHandle(ov.hEvent);
    }

    // ---- Step 4: Read response via OVERLAPPED ----
    {
        OVERLAPPED ov = {};
        ov.hEvent = CreateEventW(NULL, TRUE, FALSE, NULL);
        if (!ov.hEvent)
        {
            PipeDbgLog("Authenticate: CreateEvent(read) failed -> AUTH_FAILED");
            CloseHandle(hPipe);
            return "AUTH_FAILED";
        }

        char buf[1024] = {};
        DWORD dwRead = 0;

        BOOL ok = ReadFile(hPipe, buf, (DWORD)(sizeof(buf) - 1), &dwRead, &ov);
        if (!ok)
        {
            DWORD err = GetLastError();
            if (err == ERROR_IO_PENDING)
            {
                PipeDbgLog("Authenticate: ReadFile pending, waiting...");
                DWORD wr = WaitForSingleObject(ov.hEvent, TIMEOUT_MS);
                if (wr == WAIT_OBJECT_0)
                {
                    if (!GetOverlappedResult(hPipe, &ov, &dwRead, FALSE))
                    {
                        PipeDbgLog("Authenticate: ReadFile GetOverlapped failed err=%d -> AUTH_FAILED",
                                   (int)GetLastError());
                        CancelIo(hPipe);
                        CloseHandle(ov.hEvent);
                        CloseHandle(hPipe);
                        return "AUTH_FAILED";
                    }
                }
                else
                {
                    PipeDbgLog("Authenticate: ReadFile timeout wr=%d -> AUTH_FAILED", (int)wr);
                    CancelIo(hPipe);
                    CloseHandle(ov.hEvent);
                    CloseHandle(hPipe);
                    return "AUTH_FAILED";
                }
            }
            else
            {
                PipeDbgLog("Authenticate: ReadFile failed err=%d -> AUTH_FAILED", (int)err);
                CloseHandle(ov.hEvent);
                CloseHandle(hPipe);
                return "AUTH_FAILED";
            }
        }

        CloseHandle(ov.hEvent);

        if (dwRead > 0)
        {
            buf[dwRead] = '\0';
            result = std::string(buf, dwRead);
            // Trim trailing CR/LF added by StreamWriter on the C# side
            while (!result.empty() &&
                   (result.back() == '\r' || result.back() == '\n'))
                result.pop_back();
        }
        PipeDbgLog("Authenticate: read %d bytes result=%s", (int)dwRead, result.c_str());
    }

    CloseHandle(hPipe);
    PipeDbgLog("Authenticate: done returning=%s", result.c_str());
    return result;
}

// ---------------------------------------------------------------------------
// ConnectToPipe / SendRequest — kept for linker compatibility (private, unused)
// ---------------------------------------------------------------------------
HANDLE PipeClient::ConnectToPipe(int /*timeoutMs*/)
{
    return INVALID_HANDLE_VALUE;
}

std::string PipeClient::SendRequest(HANDLE /*hPipe*/,
                                    const std::string& /*request*/,
                                    int /*timeoutMs*/)
{
    return "AUTH_FAILED";
}