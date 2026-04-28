// dllmain.cpp - DLL entry point and COM factory

#include <windows.h>
#include <ole2.h>
#include "guid.h"
#include "FacelookProvider.h"

// Module handle
HMODULE g_hModule = NULL;

// COM class factory
class ClassFactory : public IClassFactory
{
public:
    ClassFactory() : _cRef(1) {}

    STDMETHOD(QueryInterface)(REFIID riid, void** ppv) override
    {
        if (IsEqualIID(riid, IID_IUnknown) || IsEqualIID(riid, IID_IClassFactory))
        {
            *ppv = this;
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }

    STDMETHOD_(ULONG, AddRef)() override { return ++_cRef; }

    STDMETHOD_(ULONG, Release)() override
    {
        if (--_cRef == 0)
        {
            delete this;
            return 0;
        }
        return _cRef;
    }

    STDMETHOD(CreateInstance)(IUnknown* pUnkOuter, REFIID riid, void** ppvObject) override
    {
        if (pUnkOuter)
            return CLASS_E_NOAGGREGATION;

        FacelookProvider* pProvider = new (std::nothrow) FacelookProvider();
        if (!pProvider)
            return E_OUTOFMEMORY;

        HRESULT hr = pProvider->QueryInterface(riid, ppvObject);
        pProvider->Release();
        return hr;
    }

    STDMETHOD(LockServer)(BOOL fLock) override
    {
        return S_OK;
    }

private:
    long _cRef;
};

// DLL entry point
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved)
{
    switch (ul_reason_for_call)
    {
    case DLL_PROCESS_ATTACH:
        g_hModule = hModule;
        DisableThreadLibraryCalls(hModule);
        break;
    case DLL_PROCESS_DETACH:
        break;
    }
    return TRUE;
}

// COM entry points
STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void** ppv)
{
    if (!IsEqualCLSID(rclsid, CLSID_FacelookProvider))
        return CLASS_E_CLASSNOTAVAILABLE;

    ClassFactory* pFactory = new (std::nothrow) ClassFactory();
    if (!pFactory)
        return E_OUTOFMEMORY;

    HRESULT hr = pFactory->QueryInterface(riid, ppv);
    pFactory->Release();
    return hr;
}

STDAPI DllCanUnloadNow()
{
    return S_OK;
}

// Registry functions for COM registration
STDAPI DllRegisterServer()
{
    // This would normally register the COM class in registry
    // In practice, use the register.reg file
    return S_OK;
}

STDAPI DllUnregisterServer()
{
    return S_OK;
}
