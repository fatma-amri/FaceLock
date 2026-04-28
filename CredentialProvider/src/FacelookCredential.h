// FacelookCredential.h - Credential tile implementation

#ifndef FACELOCK_CREDENTIAL_H
#define FACELOCK_CREDENTIAL_H

#include <credentialprovider.h>
#include <memory>

class PipeClient;

class FacelookCredential : public ICredentialProviderCredential2
{
public:
    FacelookCredential();
    ~FacelookCredential();

    // IUnknown
    STDMETHOD(QueryInterface)(REFIID riid, void** ppvObject) override;
    STDMETHOD_(ULONG, AddRef)(void) override;
    STDMETHOD_(ULONG, Release)(void) override;

    // ICredentialProviderCredential
    STDMETHOD(Advise)(ICredentialProviderCredentialEvents* pcpce) override;
    STDMETHOD(UnAdvise)(void) override;
    STDMETHOD(SetSelected)(BOOL* pbAutoLogon) override;
    STDMETHOD(SetDeselected)(void) override;
    STDMETHOD(GetFieldState)(DWORD dwFieldID, CREDENTIAL_PROVIDER_FIELD_STATE* pcpfs,
        CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE* pcpfis) override;
    STDMETHOD(GetStringValue)(DWORD dwFieldID, wchar_t** ppwsz) override;
    STDMETHOD(GetBitmapValue)(DWORD dwFieldID, HBITMAP* phbmp) override;
    STDMETHOD(GetCheckboxValue)(DWORD dwFieldID, BOOL* pbChecked, wchar_t** ppwszLabel) override;
    STDMETHOD(GetSubmitButtonValue)(DWORD dwFieldID, DWORD* pdwAdjacentTo) override;
    STDMETHOD(GetComboBoxValueCount)(DWORD dwFieldID, DWORD* pcItems, DWORD* pdwSelectedItem) override;
    STDMETHOD(GetComboBoxValueAt)(DWORD dwFieldID, DWORD dwItem, wchar_t** ppwsz) override;
    STDMETHOD(SetStringValue)(DWORD dwFieldID, wchar_t const* pwsz) override;
    STDMETHOD(SetCheckboxValue)(DWORD dwFieldID, BOOL bChecked) override;
    STDMETHOD(SetComboBoxSelectedValue)(DWORD dwFieldID, DWORD dwSelectedItem) override;
    STDMETHOD(CommandLinkClicked)(DWORD dwFieldID) override;
    STDMETHOD(GetSerialization)(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE* pcpgsr,
        CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION* pcpcs) override;
    STDMETHOD(ReportResult)(NTSTATUS ntsStatus, NTSTATUS ntsSubstatus,
        wchar_t** ppwszOptionalStatusText,
        CREDENTIAL_PROVIDER_STATUS_ICON* pcpsiOptionalStatusIcon) override;

    // ICredentialProviderCredential2
    STDMETHOD(GetUserSid)(wchar_t** ppwszUserSid) override;

private:
    long _cRef;
    ICredentialProviderCredentialEvents* _pcpce;
    std::unique_ptr<PipeClient> _pipeClient;
    wchar_t* _pwszUsername;
    BOOL _bSelected;

    void AuthenticateWithFace();
};

#endif // FACELOCK_CREDENTIAL_H
