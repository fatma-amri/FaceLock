#pragma once
#define SECURITY_WIN32
#include <windows.h>
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
    STDMETHOD(SetSerialization)(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcps) override;
    STDMETHOD(Advise)(ICredentialProviderEvents* pcpe, UINT_PTR upAdviseContext) override;
    STDMETHOD(UnAdvise)(void) override;
    STDMETHOD(GetFieldDescriptorCount)(DWORD* pdwCount) override;
    STDMETHOD(GetFieldDescriptorAt)(DWORD dwIndex, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR** ppcpfd) override;
    STDMETHOD(GetCredentialCount)(DWORD* pdwCount, DWORD* pdwDefault, BOOL* pbAutoLogonWithDefault) override;
    STDMETHOD(GetCredentialAt)(DWORD dwIndex, ICredentialProviderCredential** ppcpc) override;

private:
    long _cRef;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    ICredentialProviderEvents* _pcpe;
    UINT_PTR _upAdviseContext;
    std::unique_ptr<FacelookCredential> _credential;
    void InitializeCredentials();
};
