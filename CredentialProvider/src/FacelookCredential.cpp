// FacelookCredential.cpp - Credential tile implementation

#include "FacelookCredential.h"
#include "PipeClient.h"
#include "guid.h"
#include <windows.h>
#include <wincred.h>
#include <ntsecapi.h>
#include <sspi.h>
#include <sstream>
#include <cstring>

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "secur32.lib")

FacelookCredential::FacelookCredential()
    : _cRef(1)
    , _pcpce(nullptr)
    , _pipeClient(std::make_unique<PipeClient>())
    , _pwszUsername(nullptr)
    , _bSelected(FALSE)
{
}

FacelookCredential::~FacelookCredential()
{
    if (_pcpce)
    {
        _pcpce->Release();
    }
    if (_pwszUsername)
    {
        CoTaskMemFree(_pwszUsername);
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

    // Trigger face authentication
    AuthenticateWithFace();

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
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs)
{
    if (!pcpgsr || !pcpcs)
        return E_INVALIDARG;

    if (!_pwszUsername)
    {
        *pcpgsr = CPGSR_NO_CREDENTIAL_FINISHED;
        return S_OK;
    }

    // Build MSV1_0_INTERACTIVE_LOGON credential package
    // This is what Windows LSA expects for logon credential
    
    HANDLE hLsaHandle;
    LSA_OPERATIONAL_MODE mode;
    NTSTATUS ntsStatus;
    
    // Connect to LSA (requires LSA_STRING, not wide string)
    LSA_STRING processName;
    processName.Buffer = (CHAR*)"FaceLock";
    processName.Length = (USHORT)strlen("FaceLock");
    processName.MaximumLength = processName.Length + 1;

    ntsStatus = LsaRegisterLogonProcess(
        &processName,
        &hLsaHandle,
        &mode
    );
    if (!NT_SUCCESS(ntsStatus))
    {
        *pcpgsr = CPGSR_NO_CREDENTIAL_FINISHED;
        return S_OK;
    }

    // Look up MSV1_0 package
    LSA_STRING lsaString;
    lsaString.Buffer = (CHAR*)"MSV1_0";
    lsaString.Length = (USHORT)strlen("MSV1_0");
    lsaString.MaximumLength = lsaString.Length + 1;

    ULONG packageId;
    ntsStatus = LsaLookupAuthenticationPackage(hLsaHandle, &lsaString, &packageId);
    if (!NT_SUCCESS(ntsStatus))
    {
        LsaDeregisterLogonProcess(hLsaHandle);
        *pcpgsr = CPGSR_NO_CREDENTIAL_FINISHED;
        return S_OK;
    }

    // Build MSV1_0_INTERACTIVE_LOGON structure
    // Format: [UserName][Domain][Password] where each has length prefix
    
    // Get lengths
    int usernameLenBytes = (wcslen(_pwszUsername) + 1) * sizeof(wchar_t);
    int domainLenBytes = (wcslen(L".") + 1) * sizeof(wchar_t);  // "." for local machine
    int passwordLenBytes = 1 * sizeof(wchar_t);  // Empty password (just null terminator)

    // Calculate total size
    DWORD dwSize = sizeof(MSV1_0_INTERACTIVE_LOGON) +
                   usernameLenBytes +
                   domainLenBytes +
                   passwordLenBytes;

    // Allocate buffer
    LPBYTE pBuffer = (LPBYTE)CoTaskMemAlloc(dwSize);
    if (!pBuffer)
    {
        LsaDeregisterLogonProcess(hLsaHandle);
        *pcpgsr = CPGSR_NO_CREDENTIAL_FINISHED;
        return S_OK;
    }

    // Fill in the structure
    MSV1_0_INTERACTIVE_LOGON* pLogon = (MSV1_0_INTERACTIVE_LOGON*)pBuffer;
    pLogon->MessageType = MsV1_0InteractiveLogon;

    // Username
    pLogon->UserName.Length = (USHORT)(wcslen(_pwszUsername) * sizeof(wchar_t));
    pLogon->UserName.MaximumLength = (USHORT)usernameLenBytes;
    pLogon->UserName.Buffer = (wchar_t*)(pBuffer + sizeof(MSV1_0_INTERACTIVE_LOGON));
    wcscpy_s(pLogon->UserName.Buffer, wcslen(_pwszUsername) + 1, _pwszUsername);

    // Domain (use "." for local machine)
    LPBYTE pDomainOffset = pBuffer + sizeof(MSV1_0_INTERACTIVE_LOGON) + usernameLenBytes;
    pLogon->LogonDomainName.Length = sizeof(wchar_t);  // Just "."
    pLogon->LogonDomainName.MaximumLength = (USHORT)domainLenBytes;
    pLogon->LogonDomainName.Buffer = (wchar_t*)pDomainOffset;
    wcscpy_s(pLogon->LogonDomainName.Buffer, 2, L".");

    // Password (empty)
    LPBYTE pPasswordOffset = pDomainOffset + domainLenBytes;
    pLogon->Password.Length = 0;
    pLogon->Password.MaximumLength = (USHORT)passwordLenBytes;
    pLogon->Password.Buffer = (wchar_t*)pPasswordOffset;
    pLogon->Password.Buffer[0] = L'\0';

    // Fill in serialization response
    pcpcs->ulAuthenticationPackage = packageId;
    pcpcs->rgbSerialization = pBuffer;
    pcpcs->cbSerialization = dwSize;
    pcpcs->clsidCredentialProvider = CLSID_FacelookProvider;

    *pcpgsr = CPGSR_RETURN_CREDENTIAL_FINISHED;

    LsaDeregisterLogonProcess(hLsaHandle);
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

    // Return username or empty if not authenticated
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
    // Call the named pipe to authenticate
    std::string result = _pipeClient->Authenticate(15000);

    // Parse result
    if (result.find("AUTH_SUCCESS:") == 0)
    {
        std::string username = result.substr(13);  // Skip "AUTH_SUCCESS:"

        // Convert to wide char
        int len = MultiByteToWideChar(CP_UTF8, 0, username.c_str(), -1, NULL, 0);
        wchar_t* pwszUsername = (wchar_t*)CoTaskMemAlloc(len * sizeof(wchar_t));
        if (pwszUsername)
        {
            MultiByteToWideChar(CP_UTF8, 0, username.c_str(), -1, pwszUsername, len);
            _pwszUsername = pwszUsername;

            // Notify provider that authentication succeeded
            if (_pcpce)
            {
                _pcpce->SetFieldState(this, 0, CPFS_SHOW);
            }
        }
    }
    else
    {
        // Authentication failed - show error
        if (_pcpce)
        {
            _pcpce->SetFieldState(this, 0, CPFS_SHOW);
        }
    }
}
