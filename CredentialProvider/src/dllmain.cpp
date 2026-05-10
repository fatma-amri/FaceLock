#define SECURITY_WIN32
#define INITGUID
#include <windows.h>
#include "guid.h"
#include "FacelookProvider.h"

HMODULE g_hModule = NULL;

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    if (ul_reason_for_call == DLL_PROCESS_ATTACH)
    {
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
    }
    return TRUE;
}

// ---------------------------------------------------------------------------
// ClassFactory — COM requires DllGetClassObject to return IClassFactory,
// not the credential provider directly. Windows then calls
// IClassFactory::CreateInstance to get the actual ICredentialProvider.
// ---------------------------------------------------------------------------
class ClassFactory : public IClassFactory
{
public:
    ClassFactory() : _cRef(1) {}

    // IUnknown
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override
    {
        if (!ppv) return E_INVALIDARG;
        *ppv = nullptr;
        if (IsEqualIID(riid, IID_IUnknown) ||
            IsEqualIID(riid, IID_IClassFactory))
        {
            *ppv = static_cast<IClassFactory*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef()  override { return ++_cRef; }
    STDMETHODIMP_(ULONG) Release() override
    {
        long c = --_cRef;
        if (c == 0) delete this;
        return c;
    }

    // IClassFactory
    STDMETHODIMP CreateInstance(IUnknown* pUnkOuter, REFIID riid, void** ppvObject) override
    {
        if (pUnkOuter)   return CLASS_E_NOAGGREGATION;
        if (!ppvObject)  return E_INVALIDARG;
        *ppvObject = nullptr;

        FacelookProvider* pProvider = new (std::nothrow) FacelookProvider();
        if (!pProvider) return E_OUTOFMEMORY;

        HRESULT hr = pProvider->QueryInterface(IID_ICredentialProvider, ppvObject);
        pProvider->Release();
        return hr;
    }
    STDMETHODIMP LockServer(BOOL fLock) override { return S_OK; }

private:
    long _cRef;
};

// ---------------------------------------------------------------------------

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv)
{
    if (!ppv) return E_INVALIDARG;
    *ppv = nullptr;

    if (!IsEqualCLSID(rclsid, CLSID_FacelookProvider))
        return CLASS_E_CLASSNOTAVAILABLE;

    // COM asks for IClassFactory (or IUnknown) — return the factory
    if (!IsEqualIID(riid, IID_IClassFactory) &&
        !IsEqualIID(riid, IID_IUnknown))
        return E_NOINTERFACE;

    ClassFactory* pFactory = new (std::nothrow) ClassFactory();
    if (!pFactory) return E_OUTOFMEMORY;

    *ppv = static_cast<IClassFactory*>(pFactory);
    return S_OK;
}

STDAPI DllCanUnloadNow()      { return S_OK; }
STDAPI DllRegisterServer()    { return S_OK; }
STDAPI DllUnregisterServer()  { return S_OK; }
