#!/usr/bin/env python3
"""
gen_proxy.py - generate a "forward everything, log each export once" proxy DLL.

It reads the export table of a real Windows DLL (for example
C:\\Windows\\System32\\dxgi.dll) and writes two files:

    <out>/<dll>_proxy.c   C source: DllMain, logging, and one tiny assembly stub per export
    <out>/<dll>.def       export list with the SAME names and SAME ordinals as the original

Build the result with llvm-mingw clang, e.g.
    x86_64-w64-mingw32-clang -shared -O2 -Wall -o dxgi.dll dxgi_proxy.c dxgi.def -lkernel32 -luser32

How the proxy works (plain English):
  * On load, it opens a log file next to the host exe (<short>_proxy_log.txt by default,
    falling back to %TEMP%), loads the REAL dll by its full system path, and fills a
    table with the real address of every export.
  * Every export is a few machine instructions. If that export has already been
    called once, it just jumps to the real function - no logging, no cost.
  * The very first time an export is called it takes a "slow path": it saves the
    argument registers, calls a C function that writes the export's name to the log,
    restores the registers, and then jumps to the real function. The caller cannot
    tell the difference.

Usage:
    python gen_proxy.py --dll dxgi --short mygame --arch x64 --out src
    python gen_proxy.py --dll d3d11 --short oldgame --arch x86 --out src

Options:
    --source PATH   read exports from this file instead of the system copy
    --log-name NAME log file name written next to the exe (default: <short>_proxy_log.txt)
    --real-path P   load the real dll from this exact path at run time instead of the
                    system directory (used by the self-test; games never need it)
"""
import argparse
import os
import sys

import pefile

ARCH_X64 = "x64"
ARCH_X86 = "x86"
MACHINE_FOR_ARCH = {ARCH_X64: 0x8664, ARCH_X86: 0x014C}
# Where the export table is read from when --source is not given.
DEFAULT_SOURCE_DIR = {ARCH_X64: r"C:\Windows\System32", ARCH_X86: r"C:\Windows\SysWOW64"}


def read_exports(path, arch):
    """Return a list of (ordinal, name-or-None) for every code export of `path`."""
    pe = pefile.PE(path, fast_load=True)
    if pe.FILE_HEADER.Machine != MACHINE_FOR_ARCH[arch]:
        sys.exit(f"error: {path} is machine 0x{pe.FILE_HEADER.Machine:X}, not {arch}")
    pe.parse_data_directories(
        directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
    if not hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        sys.exit(f"error: {path} has no export table")
    exports = []
    for sym in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if sym.address == 0 and not sym.forwarder:
            continue  # empty slot in the ordinal range, not a real export
        if not sym.forwarder:
            section = pe.get_section_by_rva(sym.address)
            is_code = section is not None and (section.Characteristics & 0x20000000)
            if not is_code:
                # A data export cannot be forwarded with a jump stub.
                print(f"warning: export #{sym.ordinal} {sym.name} points at data; "
                      "it is proxied as code and must never be called", file=sys.stderr)
        exports.append((sym.ordinal, sym.name.decode() if sym.name else None))
    exports.sort()
    return exports


def c_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def emit_stubs_x64(exports):
    lines = []
    for i, (ordinal, name) in enumerate(exports):
        label = name or f"ordinal {ordinal}"
        lines += [
            f'"  /* [{i}] {label} */\\n"',
            f'"  .globl proxy_stub_{i}\\n"',
            f'"  .p2align 4\\n"',
            f'"proxy_stub_{i}:\\n"',
            f'"  cmpb $0, proxy_seen+{i}(%rip)\\n"',
            f'"  je proxy_slow_{i}\\n"',
            f'"  jmp *proxy_real+{i}*PTR_SIZE(%rip)\\n"',
            f'"proxy_slow_{i}:\\n"',
            f'"  movl ${i}, %eax\\n"',
            f'"  jmp proxy_slow_path\\n"',
        ]
    return "\n".join(lines)


def emit_stubs_x86(exports):
    lines = []
    for i, (ordinal, name) in enumerate(exports):
        label = name or f"ordinal {ordinal}"
        lines += [
            f'"  /* [{i}] {label} */\\n"',
            f'"  .globl _proxy_stub_{i}\\n"',
            f'"  .p2align 4\\n"',
            f'"_proxy_stub_{i}:\\n"',
            f'"  cmpb $0, _proxy_seen+{i}\\n"',
            f'"  je proxy_slow_{i}\\n"',
            f'"  jmp *_proxy_real+{i}*PTR_SIZE\\n"',
            f'"proxy_slow_{i}:\\n"',
            f'"  pushl ${i}\\n"',
            f'"  jmp proxy_slow_path\\n"',
        ]
    return "\n".join(lines)


SLOW_PATH_X64 = r'''
/* Shared first-call path (64-bit).
 * On entry: eax = export index; the stack is exactly as the game left it
 * (return address on top, so rsp is 8 past a 16-byte boundary).
 * Windows x64 passes the first four arguments in rcx, rdx, r8, r9 (integers)
 * or xmm0..xmm3 (floats); everything past that is already on the stack and we
 * leave it untouched. rax, r10 and r11 carry no arguments, so we may use them. */
__asm__(
"  .text\n"
"  .set PTR_SIZE, 8\n"
"  .set SHADOW_SPACE, 0x20\n"     /* 4 x 8 bytes the callee may use, required by Windows x64 */
"  .set XMM_SAVE, 0x40\n"         /* 4 x 16 bytes for xmm0..xmm3 */
"  .set INDEX_SLOT, 0x60\n"       /* where the export index is kept across the call */
"  .set FRAME_SIZE, 0x68\n"       /* 0x20 + 0x40 + 8; with the 4 pushes below this re-aligns rsp to 16 */
"  .p2align 4\n"
"proxy_slow_path:\n"
"  pushq %rcx\n"
"  pushq %rdx\n"
"  pushq %r8\n"
"  pushq %r9\n"
"  subq $FRAME_SIZE, %rsp\n"
"  movdqu %xmm0, SHADOW_SPACE+0x00(%rsp)\n"
"  movdqu %xmm1, SHADOW_SPACE+0x10(%rsp)\n"
"  movdqu %xmm2, SHADOW_SPACE+0x20(%rsp)\n"
"  movdqu %xmm3, SHADOW_SPACE+0x30(%rsp)\n"
"  movq %rax, INDEX_SLOT(%rsp)\n"
"  movl %eax, %ecx\n"
"  call proxy_first_call\n"
"  movdqu SHADOW_SPACE+0x00(%rsp), %xmm0\n"
"  movdqu SHADOW_SPACE+0x10(%rsp), %xmm1\n"
"  movdqu SHADOW_SPACE+0x20(%rsp), %xmm2\n"
"  movdqu SHADOW_SPACE+0x30(%rsp), %xmm3\n"
"  movq INDEX_SLOT(%rsp), %rax\n"
"  addq $FRAME_SIZE, %rsp\n"
"  popq %r9\n"
"  popq %r8\n"
"  popq %rdx\n"
"  popq %rcx\n"
"  leaq proxy_real(%rip), %r11\n"
"  jmp *(%r11,%rax,PTR_SIZE)\n"
);
'''

SLOW_PATH_X86 = r'''
/* Shared first-call path (32-bit).
 * On entry the stub has pushed the export index, so the stack is:
 *   [esp] = index, [esp+4] = the game's return address, then the game's arguments.
 * eax, ecx and edx are saved because some calling conventions pass values in them.
 * At the end the index slot is overwritten with the real function's address and
 * "ret" jumps there - leaving the stack exactly as the game's call left it. */
__asm__(
"  .text\n"
"  .set PTR_SIZE, 4\n"
"  .set SAVED_REGS, 12\n"         /* eax + ecx + edx */
"  .p2align 4\n"
"proxy_slow_path:\n"
"  pushl %eax\n"
"  pushl %ecx\n"
"  pushl %edx\n"
"  pushl SAVED_REGS(%esp)\n"      /* argument: export index */
"  call _proxy_first_call\n"
"  addl $PTR_SIZE, %esp\n"
"  popl %edx\n"
"  popl %ecx\n"
"  movl PTR_SIZE(%esp), %eax\n"   /* eax = index (eax itself is still saved at [esp]) */
"  movl _proxy_real(,%eax,PTR_SIZE), %eax\n"
"  movl %eax, PTR_SIZE(%esp)\n"   /* replace index with target address */
"  popl %eax\n"
"  ret\n"                         /* 'returns' into the real function */
);
'''

C_TEMPLATE = r'''/* ==========================================================================
 * GENERATED FILE - do not edit by hand. Re-run gen_proxy.py instead.
 * Generator: lanes plugin, tools/proxy-gen/gen_proxy.py
 * Source export table: @SOURCE@
 * Architecture: @ARCH@   Exports: @COUNT@
 *
 * A pass-through proxy for @DLLNAME@. Every export of the real dll is
 * re-exported with the same name and ordinal. The first call of each export is
 * written to the log; after that the stub is a plain jump to the real function.
 * This file is long only because of the one-stub-per-export list at the bottom.
 * ========================================================================== */
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

/* ---- Settings ------------------------------------------------------------ */
#define PROXY_DLL_FILE    L"@DLLNAME@"                 /* dll we stand in for     */
#define REAL_DLL_OVERRIDE @REAL_OVERRIDE@              /* NULL = system directory */
#define LOG_FILE_NAME     L"@LOGNAME@"  /* written next to the exe */
#define LOG_TAG           "@SHORT@ @DLLNAME@ proxy"
#define EXPORT_COUNT      @COUNT@
#define LOG_LINE_MAX      2048
#define PATH_CHARS        (MAX_PATH * 2)

/* ---- Export list (index order matches the stubs and the .def file) ------ */
typedef struct {
    WORD ordinal;
    const char *name;   /* NULL for an ordinal-only (NONAME) export */
} ExportInfo;

static const ExportInfo EXPORTS[EXPORT_COUNT] = {
@EXPORT_TABLE@
};

/* Shared with the assembly stubs, so they must not be 'static'. */
__attribute__((used)) void *proxy_real[EXPORT_COUNT];        /* real addresses       */
__attribute__((used)) char proxy_seen[EXPORT_COUNT]; /* 1 = already logged */

static HMODULE g_real_dll = NULL;
static HANDLE g_log = INVALID_HANDLE_VALUE;

/* ---- Logging -------------------------------------------------------------- */

/* Open "<exe folder>\<log name>" for appending, or %TEMP% if that fails. */
static void log_open(void) {
    WCHAR path[PATH_CHARS];
    DWORD len = GetModuleFileNameW(NULL, path, PATH_CHARS);
    if (len > 0 && len < PATH_CHARS) {
        WCHAR *slash = wcsrchr(path, L'\\');
        if (slash && (size_t)(slash + 1 - path) + wcslen(LOG_FILE_NAME) < PATH_CHARS) {
            wcscpy(slash + 1, LOG_FILE_NAME);
            g_log = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        }
    }
    if (g_log == INVALID_HANDLE_VALUE) {
        len = GetTempPathW(PATH_CHARS, path);
        if (len > 0 && len + wcslen(LOG_FILE_NAME) < PATH_CHARS) {
            wcscat(path, LOG_FILE_NAME);
            g_log = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        }
    }
}

/* Write one timestamped line. Each line is a single unbuffered WriteFile, so it
 * is on disk immediately (the equivalent of fflush after every line) and lines
 * from different threads never interleave. */
static void log_line(const char *fmt, ...) {
    if (g_log == INVALID_HANDLE_VALUE) return;
    char line[LOG_LINE_MAX];
    SYSTEMTIME now;
    GetLocalTime(&now);
    int used = snprintf(line, sizeof line, "[%04u-%02u-%02u %02u:%02u:%02u.%03u] ",
                        now.wYear, now.wMonth, now.wDay,
                        now.wHour, now.wMinute, now.wSecond, now.wMilliseconds);
    if (used < 0) return;
    va_list args;
    va_start(args, fmt);
    int body = vsnprintf(line + used, sizeof line - used, fmt, args);
    va_end(args);
    if (body < 0) return;
    used += body;
    if (used > (int)sizeof line - 3) used = (int)sizeof line - 3; /* truncated: keep room for CRLF */
    line[used++] = '\r';
    line[used++] = '\n';
    DWORD written;
    WriteFile(g_log, line, (DWORD)used, &written, NULL);
}

static void to_utf8(const WCHAR *wide, char *out, int out_size) {
    if (!WideCharToMultiByte(CP_UTF8, 0, wide, -1, out, out_size, NULL, NULL))
        strcpy(out, "?");
}

/* ---- Called by the assembly stubs on the first call of an export --------- */
static void proxy_init(void);

#ifdef _WIN64
/* Stand-in for an export called before the real dll could be loaded. */
static INT_PTR proxy_early_return_zero(void) { return 0; }
#endif

__attribute__((used)) void proxy_first_call(unsigned index) {
    if (index >= EXPORT_COUNT) return;
    /* An export can be called BEFORE our DllMain has run: on 2026-09-17 Windows' app-compat
     * shim (AcGenral.dll) called dxgi's SetAppCompatStringPointer while a game was still loading
     * us, found an empty address table and jumped to 0. So make sure we are set up first.
     * The "seen" flag is set only after that, so no other thread can take the fast path
     * through an empty table. */
    proxy_init();
    if (!proxy_real[index]) {
#ifdef _WIN64
        /* Too early for the real dll (loading it inside the loader fails with error 1168).
         * Answer this one call with 0 instead of jumping to address 0, and do NOT mark the
         * export as seen, so the next call retries. x64 only: a 32-bit stdcall export must
         * pop its own arguments, so a generic "return 0" would corrupt the caller's stack. */
        proxy_real[index] = (void *)proxy_early_return_zero;
        log_line("early call to export #%u before the real dll could load: returned 0",
                 EXPORTS[index].ordinal);
        return;
#endif
    }
    if (__sync_lock_test_and_set(&proxy_seen[index], 1) != 0) /* atomic test-and-set */
        return; /* another thread logged it a moment ago */
    const ExportInfo *e = &EXPORTS[index];
    DWORD err = GetLastError(); /* keep the game's last-error value intact */
    if (e->name)
        log_line("first call: %s (ordinal %u) thread %lu", e->name, e->ordinal,
                 GetCurrentThreadId());
    else
        log_line("first call: ordinal-only export #%u thread %lu", e->ordinal,
                 GetCurrentThreadId());
    if (!proxy_real[index])
        log_line("  ERROR: no real address for this export - the call will crash");
    SetLastError(err);
}

/* ---- Load the real dll and fill the address table ----------------------- */
static void load_real_dll(void) {
    WCHAR path[PATH_CHARS];
    const WCHAR *override = REAL_DLL_OVERRIDE;
    if (override) {
        wcsncpy(path, override, PATH_CHARS - 1);
        path[PATH_CHARS - 1] = 0;
    } else {
        UINT n = GetSystemDirectoryW(path, PATH_CHARS);
        if (n == 0 || n + 1 + wcslen(PROXY_DLL_FILE) >= PATH_CHARS) {
            log_line("FATAL: GetSystemDirectoryW failed (error %lu)", GetLastError());
            return;
        }
        wcscat(path, L"\\");
        wcscat(path, PROXY_DLL_FILE);
    }
    char path_utf8[PATH_CHARS];
    to_utf8(path, path_utf8, sizeof path_utf8);

    g_real_dll = LoadLibraryW(path);
    if (!g_real_dll) {
        log_line("FATAL: could not load real dll %s (error %lu)", path_utf8, GetLastError());
        return;
    }
    int missing = 0;
    for (int i = 0; i < EXPORT_COUNT; i++) {
        const char *lookup = EXPORTS[i].name ? EXPORTS[i].name
                                             : (const char *)MAKEINTRESOURCEA(EXPORTS[i].ordinal);
        proxy_real[i] = (void *)GetProcAddress(g_real_dll, lookup);
        if (!proxy_real[i]) {
            missing++;
            if (EXPORTS[i].name)
                log_line("WARNING: real dll has no export %s", EXPORTS[i].name);
            else
                log_line("WARNING: real dll has no ordinal #%u", EXPORTS[i].ordinal);
        }
    }
    log_line("real dll: %s (loaded at %p), %d of %d exports resolved",
             path_utf8, (void *)g_real_dll, EXPORT_COUNT - missing, EXPORT_COUNT);
}

/* Open the log and load the real dll exactly once, from whichever comes first:
 * DllMain, or an export being called early (see proxy_first_call). */
static INIT_ONCE g_init_once = INIT_ONCE_STATIC_INIT;

static volatile LONG g_loading = 0; /* 1 while some thread is inside load_real_dll */

static BOOL CALLBACK proxy_log_once(PINIT_ONCE once, PVOID param, PVOID *context) {
    (void)once; (void)param; (void)context;
    log_open();
    WCHAR exe[PATH_CHARS];
    char exe_utf8[PATH_CHARS];
    if (!GetModuleFileNameW(NULL, exe, PATH_CHARS)) exe[0] = 0;
    to_utf8(exe, exe_utf8, sizeof exe_utf8);
    log_line("=== %s attached, PID %lu, exe %s ===", LOG_TAG,
             GetCurrentProcessId(), exe_utf8);
    return TRUE;
}

/* The log opens once. Loading the real dll is RETRIED until it works, because the
 * very first attempt can come too early (inside the loader) and fail with error 1168. */
static void proxy_init(void) {
    DWORD err = GetLastError();
    InitOnceExecuteOnce(&g_init_once, proxy_log_once, NULL, NULL);
    /* No lock is held while loading: loading the real dll can call straight back into
     * one of OUR exports (the app-compat shim does exactly that for dxgi), and a lock
     * here deadlocked a game on 2026-09-17. A caller that finds a load already in progress
     * simply goes on without the real dll for that one call. */
    if (!g_real_dll && InterlockedCompareExchange(&g_loading, 1, 0) == 0) {
        if (!g_real_dll) load_real_dll();
        InterlockedExchange(&g_loading, 0);
    }
    SetLastError(err);
}

BOOL WINAPI DllMain(HINSTANCE self, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(self);
        proxy_init();
    } else if (reason == DLL_PROCESS_DETACH) {
        /* reserved != NULL means the whole process is exiting: do not unload anything. */
        log_line("=== %s detached (%s) ===", LOG_TAG,
                 reserved ? "process exit" : "FreeLibrary");
        if (!reserved && g_real_dll) FreeLibrary(g_real_dll);
        if (g_log != INVALID_HANDLE_VALUE) {
            CloseHandle(g_log);
            g_log = INVALID_HANDLE_VALUE;
        }
    }
    return TRUE;
}

/* ---- Assembly ------------------------------------------------------------- */
@SLOW_PATH@
/* One stub per export: already seen -> jump to the real function; otherwise
 * put the index where the shared first-call path expects it and go there. */
__asm__(
"  .text\n"
@STUBS@
);
'''


def main():
    ap = argparse.ArgumentParser(description="Generate a logging forwarding proxy DLL source.")
    ap.add_argument("--dll", required=True, help="base name of the dll, e.g. dxgi")
    ap.add_argument("--short", required=True, help="short app name, used in the log file name and log lines, e.g. mygame")
    ap.add_argument("--arch", choices=[ARCH_X64, ARCH_X86], default=ARCH_X64)
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--source", help="read exports from this file (default: system copy)")
    ap.add_argument("--log-name", help="log file name next to the exe (default: <short>_proxy_log.txt)")
    ap.add_argument("--real-path", help="load the real dll from this path at run time")
    args = ap.parse_args()

    dll_base = args.dll[:-4] if args.dll.lower().endswith(".dll") else args.dll
    dll_file = dll_base + ".dll"
    source = args.source or os.path.join(DEFAULT_SOURCE_DIR[args.arch], dll_file)
    exports = read_exports(source, args.arch)
    if not exports:
        sys.exit("error: no exports found")

    table = []
    for i, (ordinal, name) in enumerate(exports):
        shown = c_string(name) if name else "NULL"
        table.append(f"    /* {i:3} */ {{ {ordinal:4}, {shown} }},")

    stubs = emit_stubs_x64(exports) if args.arch == ARCH_X64 else emit_stubs_x86(exports)
    real_override = ("L" + c_string(args.real_path)) if args.real_path else "NULL"

    source_c = (C_TEMPLATE
                .replace("@SOURCE@", source)
                .replace("@ARCH@", args.arch)
                .replace("@COUNT@", str(len(exports)))
                .replace("@DLLNAME@", dll_file)
                .replace("@LOGNAME@", args.log_name or f"{args.short}_proxy_log.txt")
                .replace("@SHORT@", args.short)
                .replace("@REAL_OVERRIDE@", real_override)
                .replace("@EXPORT_TABLE@", "\n".join(table))
                .replace("@SLOW_PATH@", SLOW_PATH_X64 if args.arch == ARCH_X64 else SLOW_PATH_X86)
                .replace("@STUBS@", stubs))

    # .def: "<name> = <stub> @<ordinal>"; ordinal-only exports get a placeholder
    # name that NONAME keeps out of the dll's name table.
    # Stub names are written without the 32-bit leading underscore; the linker adds it.
    def_lines = [f"LIBRARY {dll_file}", "EXPORTS"]
    for i, (ordinal, name) in enumerate(exports):
        if name:
            def_lines.append(f"    {name} = proxy_stub_{i} @{ordinal}")
        else:
            def_lines.append(f"    ordinal_{ordinal} = proxy_stub_{i} @{ordinal} NONAME")

    os.makedirs(args.out, exist_ok=True)
    c_path = os.path.join(args.out, f"{dll_base}_proxy.c")
    def_path = os.path.join(args.out, f"{dll_base}.def")
    with open(c_path, "w", newline="\n") as f:
        f.write(source_c)
    with open(def_path, "w", newline="\n") as f:
        f.write("\n".join(def_lines) + "\n")
    named = sum(1 for _, n in exports if n)
    print(f"{c_path}: {len(exports)} exports ({named} named, {len(exports) - named} ordinal-only), {args.arch}")
    print(f"{def_path}")


if __name__ == "__main__":
    main()
