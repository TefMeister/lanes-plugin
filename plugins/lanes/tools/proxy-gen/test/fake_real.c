/* fake_real.c - a stand-in "real" dll for the proxy self-test.
 * Its functions check that every argument arrives intact, so a proxy stub that
 * damaged a register, a float register or the stack would make them return a
 * wrong answer (or crash). */
#include <windows.h>

/* Six integer arguments: four in registers on 64-bit, the rest on the stack. */
__declspec(dllexport) long long WINAPI fake_ints(long long a, long long b, long long c,
                                                 long long d, long long e, long long f) {
    return a + 2 * b + 3 * c + 4 * d + 5 * e + 6 * f;
}

/* Floats: on 64-bit the first four travel in xmm0..xmm3. */
__declspec(dllexport) double WINAPI fake_floats(double a, double b, double c, double d, double e) {
    return a + 2 * b + 3 * c + 4 * d + 5 * e;
}

/* Mixed: 64-bit puts the int in rcx and the float in xmm1. */
__declspec(dllexport) double WINAPI fake_mixed(int a, double b, int c, float d) {
    return a + 2 * b + 3 * c + 4 * d;
}

/* 32-bit only matters: fastcall passes the first two arguments in ecx and edx. */
__declspec(dllexport) int __fastcall fake_fastcall(int a, int b, int c) {
    return a + 2 * b + 3 * c;
}

/* Returns GetLastError so the test can confirm the proxy kept it intact. */
__declspec(dllexport) DWORD WINAPI fake_lasterror(void) {
    return GetLastError();
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID v) { (void)h; (void)r; (void)v; return TRUE; }
