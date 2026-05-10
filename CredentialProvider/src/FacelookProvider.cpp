// FacelookProvider.cpp - Credential Provider implementation

#define SECURITY_WIN32
#include "FacelookProvider.h"
#include "FacelookCredential.h"
#include "guid.h"
#include <windows.h>
#include <strsafe.h>

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
    int len = wsprintfA(buf, "[%02d:%02d:%02d] %s\r\n",
        st.wHour, st.wMinute, st.wSecond, msg);
    DWORD written;
    WriteFile(hFile, buf, (DWORD)len, &written, NULL);
    CloseHandle(hFile);
}

// ---------------------------------------------------------------------------

FacelookProvider::FacelookProvider()
    : _cRef(1)
    , _cpus(CPUS_INVALID)
    , _pcpe(nullptr)
    , _upAdviseContext(0)
{
    DbgLog("FacelookProvider::ctor");
    try {
        _credential.reset(new FacelookCredential());
        DbgLog("FacelookProvider::ctor - credential created OK");
    } catch (...) {
        _credential = nullptr;
        DbgLog("FacelookProvider::ctor - credential creation FAILED");
    }
}

FacelookProvider::~FacelookProvider()
{
    DbgLog("FacelookProvider::dtor");
    if (_pcpe)
    {
        _pcpe->Release();
    }
}

STDMETHODIMP FacelookProvider::QueryInterface(REFIID riid, void** ppvObject)
{
    if (!ppvObject) return E_INVALIDARG;
    *ppvObject = nullptr;

    OLECHAR szIID[40] = {};
    StringFromGUID2(riid, szIID, 40);
    char szNarrow[80] = {};
    WideCharToMultiByte(CP_ACP, 0, szIID, -1, szNarrow, 80, nullptr, nullptr);
    DbgLog("QueryInterface - IID: %s", szNarrow);

    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICredentialProvider))
    {
        DbgLog("QueryInterface - returning ICredentialProvider");
        *ppvObject = static_cast<ICredentialProvider*>(this);
        AddRef();
        return S_OK;
    }

    DbgLog("QueryInterface - E_NOINTERFACE for above IID");
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) FacelookProvider::AddRef()
{
    return ++_cRef;
}

STDMETHODIMP_(ULONG) FacelookProvider::Release()
{
    long cRef = --_cRef;
    if (cRef == 0)
    {
        delete this;
    }
    return cRef;
}

STDMETHODIMP FacelookProvider::SetUsageScenario(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    DWORD dwFlags)
{
    DbgLog("SetUsageScenario called: cpus=%d dwFlags=%d", (int)cpus, (int)dwFlags);

    _cpus = cpus;

    switch (cpus)
    {
    case CPUS_LOGON:
    case CPUS_UNLOCK_WORKSTATION:
        DbgLog("SetUsageScenario - supported scenario, calling InitializeCredentials");
        InitializeCredentials();
        DbgLog("SetUsageScenario - returning S_OK");
        return S_OK;

    case CPUS_CREDUI:
    case CPUS_CHANGE_PASSWORD:
        DbgLog("SetUsageScenario - unsupported scenario, returning E_NOTIMPL");
        return E_NOTIMPL;

    default:
        DbgLog("SetUsageScenario - unknown scenario %d, returning E_NOTIMPL", (int)cpus);
        return E_NOTIMPL;
    }
}

STDMETHODIMP FacelookProvider::SetSerialization(
    const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcps)
{
    DbgLog("SetSerialization");
    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::Advise(
    ICredentialProviderEvents* pcpe,
    UINT_PTR upAdviseContext)
{
    DbgLog("Advise");
    if (_pcpe)
    {
        _pcpe->Release();
    }
    _pcpe = pcpe;
    _upAdviseContext = upAdviseContext;
    if (_pcpe)
    {
        _pcpe->AddRef();
    }
    return S_OK;
}

STDMETHODIMP FacelookProvider::UnAdvise()
{
    DbgLog("UnAdvise");
    if (_pcpe)
    {
        _pcpe->Release();
        _pcpe = nullptr;
    }
    _upAdviseContext = 0;
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetFieldDescriptorCount(DWORD* pdwCount)
{
    DbgLog("GetFieldDescriptorCount");
    if (!pdwCount)
        return E_INVALIDARG;

    *pdwCount = 1;
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetFieldDescriptorAt(
    DWORD dwIndex,
    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd)
{
    DbgLog("GetFieldDescriptorAt dwIndex=%d", (int)dwIndex);

    if (dwIndex != 0 || !ppcpfd)
        return E_INVALIDARG;

    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR* pcpfd =
        (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(
            sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR));

    if (!pcpfd)
        return E_OUTOFMEMORY;

    ZeroMemory(pcpfd, sizeof(*pcpfd));

    pcpfd->dwFieldID     = 0;
    pcpfd->cpft          = CPFT_LARGE_TEXT;
    pcpfd->guidFieldType = GUID_NULL;

    const wchar_t* label = L"Sign in with Face";
    SIZE_T labelBytes = (wcslen(label) + 1) * sizeof(wchar_t);
    pcpfd->pszLabel = (PWSTR)CoTaskMemAlloc(labelBytes);
    if (!pcpfd->pszLabel)
    {
        CoTaskMemFree(pcpfd);
        return E_OUTOFMEMORY;
    }
    StringCbCopyW(pcpfd->pszLabel, labelBytes, label);

    *ppcpfd = pcpfd;
    DbgLog("GetFieldDescriptorAt - returning S_OK");
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetCredentialCount(
    DWORD* pdwCount,
    DWORD* pdwDefault,
    BOOL*  pbAutoLogonWithDefault)
{
    DbgLog("GetCredentialCount");
    if (!pdwCount || !pdwDefault || !pbAutoLogonWithDefault)
        return E_INVALIDARG;

    *pdwCount              = 1;
    *pdwDefault            = 0;
    *pbAutoLogonWithDefault = FALSE;

    return S_OK;
}

STDMETHODIMP FacelookProvider::GetCredentialAt(
    DWORD dwIndex,
    ICredentialProviderCredential** ppcpc)
{
    DbgLog("GetCredentialAt dwIndex=%d credential=%p", (int)dwIndex, (void*)_credential.get());

    if (dwIndex != 0 || !ppcpc)
        return E_INVALIDARG;

    if (!_credential)
    {
        DbgLog("GetCredentialAt - _credential is null, E_FAIL");
        return E_FAIL;
    }

    HRESULT hr = _credential->QueryInterface(IID_ICredentialProviderCredential, (void**)ppcpc);
    DbgLog("GetCredentialAt - QI hr=0x%08X", (unsigned)hr);
    return hr;
}

void FacelookProvider::InitializeCredentials()
{
    DbgLog("InitializeCredentials");
    if (_credential)
    {
        DbgLog("InitializeCredentials - already initialized, skipping");
        return;
    }
    try {
        _credential.reset(new FacelookCredential());
        DbgLog("InitializeCredentials - credential created OK");
    } catch (...) {
        _credential = nullptr;
        DbgLog("InitializeCredentials - credential creation FAILED");
    }
}
