// FacelookProvider.h - Main Credential Provider implementation

#ifndef FACELOCK_PROVIDER_H
#define FACELOCK_PROVIDER_H

#include <credentialprovider.h>
#include <memory>

class FacelookCredential;

class FacelookProvider : public ICredentialProvider
{
public:
    FacelookProvider();
    ~FacelookProvider();

    // IUnknown
    STDMETHOD(QueryInterface)(REFIID riid, void** ppvObject) override;
    STDMETHOD_(ULONG, AddRef)(void) override;
    STDMETHOD_(ULONG, Release)(void) override;

    // ICredentialProvider
    STDMETHOD(SetUsageScenario)(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD dwFlags) override;
    STDMETHOD(ConnectToCredentialServer)(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, wchar_t const* pwszCredentialProviderFilter,
        wchar_t const* pwszCredentialProviderAccount, ICredentialProviderWindow* pcpw) override;
    STDMETHOD(SetSerialization)(CREDENTIAL_SERIALIZATION const* pcps) override;
    STDMETHOD(Advise)(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) override;
    STDMETHOD(UnAdvise)(void) override;
    STDMETHOD(GetFieldDescriptorCount)(DWORD* pdwCount) override;
    STDMETHOD(GetFieldDescriptors)(DWORD dwCount, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) override;
    STDMETHOD(GetCredentialCount)(DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault) override;
    STDMETHOD(GetCredentialAt)(DWORD dwIndex, ICredentialProviderCredential** ppcpc) override;
    STDMETHOD(Filter)(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR const* pcpfd, wchar_t const* pwszUnmarshalled, wchar_t** ppwszMarshalled) override;
    STDMETHOD(ResultsObtained)(DWORD dwNumResults, CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE const* pcpgsr,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION const* pcpcs, DWORD* pdwOptionalStatus,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;
    STDMETHOD(GetSerialization)(CREDENTIAL_SERIALIZATION* pcps) override;
    STDMETHOD(IsLogoncredential)(BOOL* pbIsLogonCredential) override;
    STDMETHOD(GetSerialization)(CREDENTIAL_SERIALIZATION** ppcps, DWORD* pcpcsCount) override;

private:
    long _cRef;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderEvents* _pcpe;
    UINT_PTR _upAdviseContext;
    std::unique_ptr<FacelookCredential> _credential;

    void InitializeCredentials();
};

#endif // FACELOCK_PROVIDER_H
