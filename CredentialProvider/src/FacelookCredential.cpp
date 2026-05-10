// FacelookCredential.cpp - Credential tile implementation

#define SECURITY_WIN32
#include "FacelookCredential.h"
#include "PipeClient.h"
#include "guid.h"
#include <windows.h>
#include <wincred.h>
#include <ntsecapi.h>
#include <sspi.h>
#include <sstream>
#include <cstring>

// ---------------------------------------------------------------------------
// Debug logging — appends one formatted line to C:\FaceLock_debug.txt
// ---------------------------------------------------------------------------
static void DbgLog(const char* fmt, ...)
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
    int len = wsprintfA(buf, "[%02d:%02d:%02d] CRED %s\r\n",
        st.wHour, st.wMinute, st.wSecond, msg);
    DWORD written;
    WriteFile(hFile, buf, (DWORD)len, &written, NULL);
    CloseHandle(hFile);
}

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "secur32.lib")

#ifndef NT_SUCCESS
#define NT_SUCCESS(Status) ((NTSTATUS)(Status) >= 0)
#endif

#ifndef STATUS_UNSUCCESSFUL
#define STATUS_UNSUCCESSFUL ((NTSTATUS)0xC0000001L)
#endif

// __try/__except cannot be mixed with try/catch in the same function scope (C2712).
// These file-scope helpers isolate the SEH around each LSA call so the COM methods
// can use try/catch(...) freely.

static NTSTATUS SafeLsaRegisterLogonProcess(HANDLE* phLsaHandle)
{
    LSA_OPERATIONAL_MODE mode = 0;
    LSA_STRING processName;
    processName.Buffer    = (CHAR*)"FaceLock";
    processName.Length    = (USHORT)strlen("FaceLock");
    processName.MaximumLength = processName.Length + 1;
    *phLsaHandle = NULL;
    NTSTATUS status = STATUS_UNSUCCESSFUL;
    __try
    {
        status = LsaRegisterLogonProcess(&processName, phLsaHandle, &mode);
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        *phLsaHandle = NULL;
        status = STATUS_UNSUCCESSFUL;
    }
    return status;
}

static NTSTATUS SafeLsaLookupAuthenticationPackage(HANDLE hLsaHandle, ULONG* pPackageId)
{
    LSA_STRING lsaString;
    lsaString.Buffer    = (CHAR*)"MSV1_0";
    lsaString.Length    = (USHORT)strlen("MSV1_0");
    lsaString.MaximumLength = lsaString.Length + 1;
    *pPackageId = 0;
    NTSTATUS status = STATUS_UNSUCCESSFUL;
    __try
    {
        status = LsaLookupAuthenticationPackage(hLsaHandle, &lsaString, pPackageId);
    }
    __except (EXCEPTION_EXECUTE_HANDLER)
    {
        status = STATUS_UNSUCCESSFUL;
    }
    return status;
}

FacelookCredential::FacelookCredential()
    : _cRef(1)
    , _pcpce(nullptr)
    , _pipeClient(std::make_unique<PipeClient>())
    , _pwszUsername(nullptr)
    , _pwszPassword(nullptr)
    , _bSelected(FALSE)
{
}

FacelookCredential::~FacelookCredential()
{
    if (_pcpce)
        _pcpce->Release();
    if (_pwszUsername)
        CoTaskMemFree(_pwszUsername);
    if (_pwszPassword)
    {
        SecureZeroMemory(_pwszPassword, wcslen(_pwszPassword) * sizeof(wchar_t));
        CoTaskMemFree(_pwszPassword);
    }
}

STDMETHODIMP FacelookCredential::QueryInterface(REFIID riid, void** ppvObject)
{
    if (!ppvObject)
        return E_INVALIDARG;

    *ppvObject = nullptr;

    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICredentialProviderCredential) ||
        IsEqualIID(riid, IID_ICredentialProviderCredential2))
    {
        *ppvObject = this;
        AddRef();
        return S_OK;
    }

    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) FacelookCredential::AddRef()
{
    return ++_cRef;
}

STDMETHODIMP_(ULONG) FacelookCredential::Release()
{
    long cRef = --_cRef;
    if (cRef == 0)
    {
        delete this;
    }
    return cRef;
}

STDMETHODIMP FacelookCredential::Advise(ICredentialProviderCredentialEvents* pcpce)
{
    if (_pcpce)
    {
        _pcpce->Release();
    }
    _pcpce = pcpce;
    if (_pcpce)
    {
        _pcpce->AddRef();
    }
    return S_OK;
}

STDMETHODIMP FacelookCredential::UnAdvise()
{
    if (_pcpce)
    {
        _pcpce->Release();
        _pcpce = nullptr;
    }
    return S_OK;
}

STDMETHODIMP FacelookCredential::SetSelected(BOOL* pbAutoLogon)
{
    if (!pbAutoLogon)
        return E_INVALIDARG;

    _bSelected = TRUE;
    *pbAutoLogon = FALSE;

    DbgLog("SetSelected - starting face auth");

    // Free any credentials from a prior attempt
    if (_pwszUsername) { CoTaskMemFree(_pwszUsername); _pwszUsername = nullptr; }
    if (_pwszPassword)
    {
        SecureZeroMemory(_pwszPassword, wcslen(_pwszPassword) * sizeof(wchar_t));
        CoTaskMemFree(_pwszPassword);
        _pwszPassword = nullptr;
    }

    try
    {
        AuthenticateWithFace();
    }
    catch (...)
    {
        DbgLog("SetSelected - exception from AuthenticateWithFace");
    }

    if (_pwszUsername)
    {
        DbgLog("SetSelected - auth succeeded, setting pbAutoLogon=TRUE");
        *pbAutoLogon = TRUE;
    }
    else
    {
        DbgLog("SetSelected - auth failed, pbAutoLogon=FALSE");
    }

    return S_OK;
}

STDMETHODIMP FacelookCredential::SetDeselected()
{
    _bSelected = FALSE;
    return S_OK;
}

STDMETHODIMP FacelookCredential::GetFieldState(
    DWORD dwFieldID,
    CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
    CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis)
{
    if (!pcpfs || !pcpfis)
        return E_INVALIDARG;

    if (dwFieldID != 0)
        return E_INVALIDARG;

    *pcpfs = CPFS_HIDDEN;
    *pcpfis = CPFIS_FOCUSED;

    return S_OK;
}

STDMETHODIMP FacelookCredential::GetStringValue(DWORD dwFieldID, wchar_t** ppwsz)
{
    if (!ppwsz)
        return E_INVALIDARG;

    if (dwFieldID == 0)
    {
        *ppwsz = (wchar_t*)CoTaskMemAlloc(sizeof(wchar_t) * 256);
        if (*ppwsz)
        {
            wcscpy_s(*ppwsz, 256, L"Face Authentication");
            return S_OK;
        }
    }

    return E_INVALIDARG;
}

STDMETHODIMP FacelookCredential::GetBitmapValue(DWORD dwFieldID, HBITMAP* phbmp)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetCheckboxValue(DWORD dwFieldID, BOOL* pbChecked, wchar_t** ppwszLabel)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetSubmitButtonValue(DWORD dwFieldID, DWORD* pdwAdjacentTo)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetComboBoxValueCount(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetComboBoxValueAt(DWORD dwFieldID, DWORD dwItem, wchar_t** ppwsz)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::SetStringValue(DWORD dwFieldID, wchar_t const* pwsz)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::SetCheckboxValue(DWORD dwFieldID, BOOL bChecked)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::SetComboBoxSelectedValue(DWORD dwFieldID, DWORD dwSelectedItem)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::CommandLinkClicked(DWORD dwFieldID)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetSerialization(
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs,
    PWSTR* ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    if (!pcpgsr || !pcpcs)
        return E_INVALIDARG;

    DbgLog("GetSerialization - username=%p password=%p", (void*)_pwszUsername, (void*)_pwszPassword);

    auto fail = [&]() {
        *pcpgsr = CPGSR_NO_CREDENTIAL_FINISHED;
        pcpcs->ulAuthenticationPackage = 0;
        pcpcs->rgbSerialization = nullptr;
        pcpcs->cbSerialization = 0;
    };

    if (!_pwszUsername || !_pwszPassword)
    {
        DbgLog("GetSerialization - missing credentials, NO_CREDENTIAL_FINISHED");
        fail();
        return S_OK;
    }

    // Look up the MSV1_0 authentication package ID
    HANDLE hLsa = NULL;
    ULONG packageId = 0;

    NTSTATUS status = SafeLsaRegisterLogonProcess(&hLsa);
    if (!NT_SUCCESS(status))
    {
        DbgLog("GetSerialization - LsaRegisterLogonProcess failed 0x%08X", (unsigned)status);
        fail();
        return S_OK;
    }

    status = SafeLsaLookupAuthenticationPackage(hLsa, &packageId);
    LsaDeregisterLogonProcess(hLsa);

    if (!NT_SUCCESS(status))
    {
        DbgLog("GetSerialization - LsaLookupAuthPackage failed 0x%08X", (unsigned)status);
        fail();
        return S_OK;
    }

    // Build a packed MSV1_0_INTERACTIVE_LOGON buffer.
    // The UNICODE_STRING.Buffer fields are set to byte offsets from the start
    // of the buffer (self-relative / packed format) — LSA interprets them as offsets.
    const wchar_t* domain   = L"."; // "." = local machine
    const wchar_t* username = _pwszUsername;
    const wchar_t* password = _pwszPassword;

    DWORD cbDomain   = (DWORD)(wcslen(domain)   * sizeof(wchar_t));
    DWORD cbUsername = (DWORD)(wcslen(username)  * sizeof(wchar_t));
    DWORD cbPassword = (DWORD)(wcslen(password)  * sizeof(wchar_t));
    DWORD cbTotal    = sizeof(MSV1_0_INTERACTIVE_LOGON) + cbDomain + cbUsername + cbPassword;

    BYTE* pBuffer = (BYTE*)CoTaskMemAlloc(cbTotal);
    if (!pBuffer)
    {
        DbgLog("GetSerialization - CoTaskMemAlloc failed");
        fail();
        return E_OUTOFMEMORY;
    }
    ZeroMemory(pBuffer, cbTotal);

    MSV1_0_INTERACTIVE_LOGON* pLogon = (MSV1_0_INTERACTIVE_LOGON*)pBuffer;
    pLogon->MessageType = MsV1_0InteractiveLogon;

    BYTE* pData = pBuffer + sizeof(MSV1_0_INTERACTIVE_LOGON);

    // Domain
    pLogon->LogonDomainName.Length        = (USHORT)cbDomain;
    pLogon->LogonDomainName.MaximumLength = (USHORT)cbDomain;
    pLogon->LogonDomainName.Buffer        = (PWSTR)(pData - pBuffer); // byte offset
    CopyMemory(pData, domain, cbDomain);
    pData += cbDomain;

    // Username
    pLogon->UserName.Length        = (USHORT)cbUsername;
    pLogon->UserName.MaximumLength = (USHORT)cbUsername;
    pLogon->UserName.Buffer        = (PWSTR)(pData - pBuffer);
    CopyMemory(pData, username, cbUsername);
    pData += cbUsername;

    // Password
    pLogon->Password.Length        = (USHORT)cbPassword;
    pLogon->Password.MaximumLength = (USHORT)cbPassword;
    pLogon->Password.Buffer        = (PWSTR)(pData - pBuffer);
    CopyMemory(pData, password, cbPassword);

    DbgLog("GetSerialization - pkgId=%d bufSize=%d domain=. user=%s", (int)packageId, (int)cbTotal, "ok");

    pcpcs->ulAuthenticationPackage = packageId;
    pcpcs->rgbSerialization        = pBuffer;
    pcpcs->cbSerialization         = cbTotal;
    pcpcs->clsidCredentialProvider = CLSID_FacelookProvider;

    *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;
    return S_OK;
}

STDMETHODIMP FacelookCredential::ReportResult(
    NTSTATUS ntsStatus,
    NTSTATUS ntsSubstatus,
    wchar_t** ppwszOptionalStatusText,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookCredential::GetUserSid(wchar_t** ppwszUserSid)
{
    if (!ppwszUserSid)
        return E_INVALIDARG;

    if (_pwszUsername)
    {
        *ppwszUserSid = (wchar_t*)CoTaskMemAlloc((wcslen(_pwszUsername) + 1) * sizeof(wchar_t));
        if (*ppwszUserSid)
        {
            wcscpy_s(*ppwszUserSid, wcslen(_pwszUsername) + 1, _pwszUsername);
            return S_OK;
        }
    }

    return E_FAIL;
}

void FacelookCredential::AuthenticateWithFace()
{
    try
    {
        DbgLog("AuthenticateWithFace - connecting to pipe (4s hard timeout)");
        std::string result = _pipeClient->Authenticate(4000);

        // Trim trailing CR/LF
        while (!result.empty() && (result.back() == '\r' || result.back() == '\n'))
            result.pop_back();

        DbgLog("AuthenticateWithFace - result length: %d", (int)result.size());

        // Expected format: AUTH_SUCCESS:<username>:<password>
        if (result.find("AUTH_SUCCESS:") != 0)
        {
            DbgLog("AuthenticateWithFace - FAILED (no AUTH_SUCCESS prefix)");
            return;
        }

        std::string rest = result.substr(13); // after "AUTH_SUCCESS:"
        size_t colon = rest.find(':');
        if (colon == std::string::npos)
        {
            DbgLog("AuthenticateWithFace - FAILED (missing password separator)");
            return;
        }

        std::string username = rest.substr(0, colon);
        std::string password = rest.substr(colon + 1);

        if (username.empty() || password.empty())
        {
            DbgLog("AuthenticateWithFace - FAILED (empty username or password)");
            return;
        }

        // Convert username to wide
        int uLen = MultiByteToWideChar(CP_UTF8, 0, username.c_str(), -1, NULL, 0);
        _pwszUsername = (wchar_t*)CoTaskMemAlloc(uLen * sizeof(wchar_t));
        if (_pwszUsername)
            MultiByteToWideChar(CP_UTF8, 0, username.c_str(), -1, _pwszUsername, uLen);

        // Convert password to wide
        int pLen = MultiByteToWideChar(CP_UTF8, 0, password.c_str(), -1, NULL, 0);
        _pwszPassword = (wchar_t*)CoTaskMemAlloc(pLen * sizeof(wchar_t));
        if (_pwszPassword)
            MultiByteToWideChar(CP_UTF8, 0, password.c_str(), -1, _pwszPassword, pLen);

        if (_pwszUsername && _pwszPassword)
        {
            DbgLog("AuthenticateWithFace - SUCCESS user: %s", username.c_str());
        }
        else
        {
            // Allocation failure — clean up so SetSelected sees no auth
            if (_pwszUsername) { CoTaskMemFree(_pwszUsername); _pwszUsername = nullptr; }
            if (_pwszPassword) { CoTaskMemFree(_pwszPassword); _pwszPassword = nullptr; }
            DbgLog("AuthenticateWithFace - FAILED (allocation error)");
        }
    }
    catch (...)
    {
        DbgLog("AuthenticateWithFace - exception caught");
        _pwszUsername = nullptr;
        _pwszPassword = nullptr;
    }
}
