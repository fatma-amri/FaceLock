// FacelookProvider.cpp - Credential Provider implementation

#include "FacelookProvider.h"
#include "FacelookCredential.h"
#include "guid.h"
#include <windows.h>

FacelookProvider::FacelookProvider()
    : _cRef(1)
    , _cpus(CPUS_INVALID)
    , _pcpe(nullptr)
    , _upAdviseContext(0)
{
}

FacelookProvider::~FacelookProvider()
{
    if (_pcpe)
    {
        _pcpe->Release();
    }
}

STDMETHODIMP FacelookProvider::QueryInterface(REFIID riid, void** ppvObject)
{
    if (!ppvObject)
        return E_INVALIDARG;

    *ppvObject = nullptr;

    if (IsEqualIID(riid, IID_IUnknown) ||
        IsEqualIID(riid, IID_ICredentialProvider))
    {
        *ppvObject = this;
        AddRef();
        return S_OK;
    }

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
    _cpus = cpus;

    // Only enabled for logon and unlock scenarios
    if (cpus == CPUS_LOGON || cpus == CPUS_UNLOCK_WORKSTATION)
    {
        InitializeCredentials();
        return S_OK;
    }

    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::ConnectToCredentialServer(
    CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus,
    wchar_t const* pwszCredentialProviderFilter,
    wchar_t const* pwszCredentialProviderAccount,
    ICredentialProviderWindow* pcpw)
{
    return S_OK;
}

STDMETHODIMP FacelookProvider::SetSerialization(
    CREDENTIAL_SERIALIZATION const* pcps)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::Advise(
    ICredentialProviderEvents* pcpe,
    UINT_PTR upAdviseContext)
{
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
    if (!pdwCount)
        return E_INVALIDARG;

    *pdwCount = 1;  // Large tile with face icon
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetFieldDescriptors(
    DWORD dwCount,
    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd)
{
    if (dwCount != 1 || !ppcpfd)
        return E_INVALIDARG;

    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR* pcpfd =
        (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR));

    if (!pcpfd)
        return E_OUTOFMEMORY;

    pcpfd->dwFieldID = 0;
    pcpfd->cpft = CPFT_LARGE_TEXT;
    pcpfd->pszLabel = L"Sign in with Face";

    *ppcpfd = pcpfd;
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetCredentialCount(
    DWORD* pdwCount,
    DWORD* pdwDefault,
    BOOL* pbAutoLogonWithDefault)
{
    if (!pdwCount || !pdwDefault || !pbAutoLogonWithDefault)
        return E_INVALIDARG;

    *pdwCount = 1;
    *pdwDefault = 0;
    *pbAutoLogonWithDefault = FALSE;

    return S_OK;
}

STDMETHODIMP FacelookProvider::GetCredentialAt(
    DWORD dwIndex,
    ICredentialProviderCredential** ppcpc)
{
    if (dwIndex != 0 || !ppcpc)
        return E_INVALIDARG;

    if (!_credential)
        return E_FAIL;

    _credential->QueryInterface(IID_ICredentialProviderCredential, (void**)ppcpc);
    return S_OK;
}

STDMETHODIMP FacelookProvider::Filter(
    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR const* pcpfd,
    wchar_t const* pwszUnmarshalled,
    wchar_t** ppwszMarshalled)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::ResultsObtained(
    DWORD dwNumResults,
    CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE const* pcpgsr,
    CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION const* pcpcs,
    DWORD* pdwOptionalStatus,
    CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::GetSerialization(
    CREDENTIAL_SERIALIZATION* pcps)
{
    return E_NOTIMPL;
}

STDMETHODIMP FacelookProvider::IsLogonCredential(BOOL* pbIsLogonCredential)
{
    if (!pbIsLogonCredential)
        return E_INVALIDARG;

    *pbIsLogonCredential = (_cpus == CPUS_LOGON);
    return S_OK;
}

STDMETHODIMP FacelookProvider::GetSerialization(
    CREDENTIAL_SERIALIZATION** ppcps,
    DWORD* pcpcsCount)
{
    return E_NOTIMPL;
}

void FacelookProvider::InitializeCredentials()
{
    _credential = std::make_unique<FacelookCredential>();
}
