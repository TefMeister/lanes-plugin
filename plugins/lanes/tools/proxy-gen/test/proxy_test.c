/* proxy_test.c - load a built proxy dll by full path and call through it.
 *
 *   proxy_test <kind> <full path to proxy dll>
 *   kind: dxgi | d3d9 | d3d11 | fake | early
 *
 * early (64-bit only): calls one of the proxy's exports from a loader notification, i.e. after
 * the dll is mapped but BEFORE its DllMain has run - what Windows' app-compat shim did to a dxgi
 * proxy on 2026-09-17 and crashed the game. The call must not crash; then the normal fake tests run.
 *
 * Every export is called twice: the first call goes through the stub's
 * "log it once" path, the second through the plain jump. Exit code 0 = all passed.
 * No game is involved; this only proves the stubs forward correctly. */
#define COBJMACROS
#include <windows.h>
#include <stdio.h>
#include <math.h>
#include <d3d9.h>
#include <d3d11.h>
#include <dxgi.h>

#define CALLS_PER_EXPORT 2
#define D3D11_SDK_VERSION_VALUE 7
#define ORDINAL_ONLY_D3D9 16   /* first NONAME export of the system d3d9.dll */
#define ORDINAL_ONLY_FAKE 12   /* NONAME export of the fake dll */
#define FLOAT_TOLERANCE 1e-9
#define TEST_LAST_ERROR 0x1234

static int g_failures = 0;

static void check(int ok, const char *what) {
    printf("  %s: %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) g_failures++;
}

static FARPROC need(HMODULE dll, const char *name) {
    FARPROC p = GetProcAddress(dll, name);
    if (!p) { printf("  FAIL: export %s not found\n", name); g_failures++; }
    return p;
}

static void test_dxgi(HMODULE dll) {
    typedef HRESULT (WINAPI *CreateFactoryFn)(REFIID, void **);
    CreateFactoryFn create1 = (CreateFactoryFn)need(dll, "CreateDXGIFactory1");
    CreateFactoryFn create0 = (CreateFactoryFn)need(dll, "CreateDXGIFactory");
    if (!create1 || !create0) return;
    for (int i = 0; i < CALLS_PER_EXPORT; i++) {
        IDXGIFactory1 *factory = NULL;
        HRESULT hr = create1(&IID_IDXGIFactory1, (void **)&factory);
        printf("  CreateDXGIFactory1 call %d: hr=0x%08lX factory=%p\n", i + 1, hr, (void *)factory);
        check(SUCCEEDED(hr) && factory, "CreateDXGIFactory1 returned a factory");
        if (factory) {
            IDXGIAdapter1 *adapter = NULL;
            if (SUCCEEDED(IDXGIFactory1_EnumAdapters1(factory, 0, &adapter))) {
                DXGI_ADAPTER_DESC1 desc;
                IDXGIAdapter1_GetDesc1(adapter, &desc);
                printf("  adapter 0: %ls\n", desc.Description);
                IDXGIAdapter1_Release(adapter);
            }
            IDXGIFactory1_Release(factory);
        }
        IDXGIFactory *old = NULL;
        hr = create0(&IID_IDXGIFactory, (void **)&old);
        check(SUCCEEDED(hr) && old, "CreateDXGIFactory returned a factory");
        if (old) IDXGIFactory_Release(old);
    }
}

static void test_d3d9(HMODULE dll) {
    typedef IDirect3D9 *(WINAPI *Create9Fn)(UINT);
    typedef DWORD (WINAPI *GetStatusFn)(void);
    Create9Fn create = (Create9Fn)need(dll, "Direct3DCreate9");
    GetStatusFn status = (GetStatusFn)need(dll, "D3DPERF_GetStatus");
    if (!create || !status) return;
    for (int i = 0; i < CALLS_PER_EXPORT; i++) {
        IDirect3D9 *d3d = create(D3D_SDK_VERSION);
        printf("  Direct3DCreate9 call %d: %p\n", i + 1, (void *)d3d);
        check(d3d != NULL, "Direct3DCreate9 returned an object");
        if (d3d) {
            printf("  adapters: %u\n", IDirect3D9_GetAdapterCount(d3d));
            IDirect3D9_Release(d3d);
        }
        printf("  D3DPERF_GetStatus: %lu\n", status());
    }
    check(GetProcAddress(dll, MAKEINTRESOURCEA(ORDINAL_ONLY_D3D9)) != NULL,
          "ordinal-only export #16 is present (not called)");
}

static void test_d3d11(HMODULE dll) {
    typedef HRESULT (WINAPI *CreateDeviceFn)(IDXGIAdapter *, D3D_DRIVER_TYPE, HMODULE, UINT,
        const D3D_FEATURE_LEVEL *, UINT, UINT, ID3D11Device **, D3D_FEATURE_LEVEL *,
        ID3D11DeviceContext **);
    CreateDeviceFn create = (CreateDeviceFn)need(dll, "D3D11CreateDevice");
    if (!create) return;
    for (int i = 0; i < CALLS_PER_EXPORT; i++) {
        ID3D11Device *device = NULL;
        ID3D11DeviceContext *context = NULL;
        D3D_FEATURE_LEVEL level = 0;
        HRESULT hr = create(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0, NULL, 0,
                            D3D11_SDK_VERSION_VALUE, &device, &level, &context);
        printf("  D3D11CreateDevice call %d: hr=0x%08lX device=%p level=0x%X\n",
               i + 1, hr, (void *)device, level);
        check(SUCCEEDED(hr) && device && context, "D3D11CreateDevice returned a device");
        if (context) ID3D11DeviceContext_Release(context);
        if (device) ID3D11Device_Release(device);
    }
}

static void test_fake(HMODULE dll) {
    typedef long long (WINAPI *IntsFn)(long long, long long, long long, long long, long long, long long);
    typedef double (WINAPI *FloatsFn)(double, double, double, double, double);
    typedef double (WINAPI *MixedFn)(int, double, int, float);
    typedef int (__fastcall *FastFn)(int, int, int);
    typedef DWORD (WINAPI *LastErrFn)(void);
    IntsFn ints = (IntsFn)need(dll, "fake_ints");
    FloatsFn floats = (FloatsFn)need(dll, "fake_floats");
    MixedFn mixed = (MixedFn)need(dll, "fake_mixed");
    FastFn fast = (FastFn)need(dll, "fake_fastcall");
    LastErrFn lasterr = (LastErrFn)need(dll, "fake_lasterror");
    IntsFn hidden = (IntsFn)GetProcAddress(dll, MAKEINTRESOURCEA(ORDINAL_ONLY_FAKE));
    check(hidden != NULL, "ordinal-only export #12 is present");
    if (!ints || !floats || !mixed || !fast || !lasterr || !hidden) return;
    for (int i = 0; i < CALLS_PER_EXPORT; i++) {
        printf(" pass %d (%s path)\n", i + 1, i == 0 ? "first-call logging" : "plain jump");
        check(ints(1, 10, 100, 1000, 10000, 100000) == 1 + 20 + 300 + 4000 + 50000 + 600000,
              "six integer arguments arrive intact");
        check(fabs(floats(0.5, 1.25, 2.125, 3.0625, 4.5) - (0.5 + 2.5 + 6.375 + 12.25 + 22.5)) < FLOAT_TOLERANCE,
              "five double arguments arrive intact");
        check(fabs(mixed(7, 1.5, 11, 2.25f) - (7 + 3.0 + 33 + 9.0)) < FLOAT_TOLERANCE,
              "mixed int/float arguments arrive intact");
        check(fast(3, 5, 7) == 3 + 10 + 21, "fastcall register arguments arrive intact");
        check(hidden(1, 1, 1, 1, 1, 1) == 21, "ordinal-only export forwards");
    }
    /* First call of fake_lasterror goes through the logging path, which writes a file. */
    SetLastError(TEST_LAST_ERROR);
    check(lasterr() == TEST_LAST_ERROR, "GetLastError survives the first-call logging");
}

/* ---- early: an export called before DllMain ------------------------------- */
typedef struct { USHORT Length, MaximumLength; PWSTR Buffer; } TEST_USTR;
typedef struct { ULONG Flags; TEST_USTR *FullDllName; TEST_USTR *BaseDllName; PVOID DllBase; ULONG SizeOfImage; } TEST_LDR_DATA;
typedef VOID (NTAPI *TEST_LDR_CB)(ULONG reason, TEST_LDR_DATA *data, PVOID context);
#define LDR_REASON_LOADED 1

static WCHAR g_early_path[MAX_PATH];
static int g_early_called = 0;
static long long g_early_result = -1;

static void *export_by_hand(BYTE *base, const char *name) {
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (!dir.VirtualAddress) return NULL;
    IMAGE_EXPORT_DIRECTORY *exp = (IMAGE_EXPORT_DIRECTORY *)(base + dir.VirtualAddress);
    DWORD *names = (DWORD *)(base + exp->AddressOfNames);
    WORD *ordinals = (WORD *)(base + exp->AddressOfNameOrdinals);
    DWORD *functions = (DWORD *)(base + exp->AddressOfFunctions);
    for (DWORD i = 0; i < exp->NumberOfNames; i++)
        if (!strcmp((char *)(base + names[i]), name)) return base + functions[ordinals[i]];
    return NULL;
}

static VOID NTAPI early_notify(ULONG reason, TEST_LDR_DATA *data, PVOID context) {
    (void)context;
    if (getenv("EARLY_DEBUG")) printf("  notify reason=%lu %.*ls\n", reason, (int)(data->FullDllName->Length / sizeof(WCHAR)), data->FullDllName->Buffer);
    if (reason != LDR_REASON_LOADED || g_early_called) return;
    if (_wcsnicmp(data->FullDllName->Buffer, g_early_path, data->FullDllName->Length / sizeof(WCHAR)) != 0) return;
    typedef long long (WINAPI *IntsFn)(long long, long long, long long, long long, long long, long long);
    /* GetProcAddress refuses a module the loader has not finished, so read the export table by hand. */
    IntsFn ints = (IntsFn)export_by_hand((BYTE *)data->DllBase, "fake_ints");
    if (!ints) return;
    g_early_called = 1;
    g_early_result = ints(1, 10, 100, 1000, 10000, 100000); /* would jump to address 0 without the fix */
}

static int load_with_early_call(const char *path, HMODULE *out) {
    WCHAR given[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, path, -1, given, MAX_PATH);
    GetFullPathNameW(given, MAX_PATH, g_early_path, NULL); /* separate buffers: in and out may not overlap */
    typedef LONG (NTAPI *RegFn)(ULONG, TEST_LDR_CB, PVOID, PVOID *);
    RegFn reg = (RegFn)GetProcAddress(GetModuleHandleA("ntdll.dll"), "LdrRegisterDllNotification");
    PVOID cookie = NULL;
    if (!reg || reg(0, early_notify, NULL, &cookie) != 0) { printf("  FAIL: LdrRegisterDllNotification\n"); return 0; }
    *out = LoadLibraryA(path);
    printf("  early call made: %s, result %lld (0 = answered before the real dll loaded, other = forwarded)\n",
           g_early_called ? "yes" : "no", g_early_result);
    check(g_early_called, "an export was called before DllMain ran");
    check(*out != NULL, "the process survived the early call and the dll loaded");
    return *out != NULL;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: %s dxgi|d3d9|d3d11|fake|early <full path to proxy dll>\n", argv[0]);
        return 2;
    }
    printf("[%s-bit] loading %s\n", sizeof(void *) == 8 ? "64" : "32", argv[2]);
    HMODULE dll = NULL;
    if (!strcmp(argv[1], "early")) {
        if (sizeof(void *) != 8) { printf("  SKIP: the early-call fallback is 64-bit only\n"); return 0; }
        if (!load_with_early_call(argv[2], &dll)) return 1;
    } else {
        dll = LoadLibraryA(argv[2]);
    }
    if (!dll) { printf("  FAIL: LoadLibrary error %lu\n", GetLastError()); return 1; }
    char loaded[MAX_PATH];
    GetModuleFileNameA(dll, loaded, MAX_PATH);
    printf("  loaded as %s\n", loaded);

    if (!strcmp(argv[1], "dxgi")) test_dxgi(dll);
    else if (!strcmp(argv[1], "d3d9")) test_d3d9(dll);
    else if (!strcmp(argv[1], "d3d11")) test_d3d11(dll);
    else if (!strcmp(argv[1], "fake") || !strcmp(argv[1], "early")) test_fake(dll);
    else { fprintf(stderr, "unknown kind %s\n", argv[1]); return 2; }

    FreeLibrary(dll); /* exercises the detach line */
    printf("%s (%d failure(s))\n", g_failures ? "RESULT: FAIL" : "RESULT: PASS", g_failures);
    return g_failures ? 1 : 0;
}
