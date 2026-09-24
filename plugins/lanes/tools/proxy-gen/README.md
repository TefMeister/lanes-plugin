# proxy-gen: the smallest possible "file of ours" next to an app

`/lm`'s first job on a new app is to check that it runs, then that it **still runs with our own file
added** (`commands/lm.md` §4b). This tool makes that file: a pass-through proxy DLL. It has the same
name as a system DLL the app loads (`dxgi.dll`, `d3d11.dll`, `d3d9.dll`, …) and sits next to the
app's exe, so Windows loads it first. It changes nothing about how the app runs. It forwards every
call to the real DLL and writes down which functions the app used.

## What it makes

`gen_proxy.py` reads the export table of the real system DLL (`C:\Windows\System32\<dll>.dll`, or
`SysWOW64` for `--arch x86`) and writes:

- `<dll>_proxy.c`: DllMain, logging, and one tiny assembly stub per export.
- `<dll>.def`: the **same export names and the same ordinals** as the original, including
  ordinal-only (`NONAME`) exports.

At run time the proxy:

1. opens `<short>_proxy_log.txt` next to the host exe (or `--log-name`; falls back to `%TEMP%`);
2. loads the real DLL by its full system path and records every export's address;
3. logs `first call: <name>` the first time each export is used. Every later call is a plain jump;
4. logs a line when it is unloaded.

Each log line goes straight to disk, so a crash never loses the last lines.

## Use

```
python gen_proxy.py --dll dxgi --short mygame --arch x64 --out src
x86_64-w64-mingw32-clang -shared -O2 -Wall -o build/dxgi.dll src/dxgi_proxy.c src/dxgi.def -lkernel32 -luser32
python verify_exports.py build/dxgi.dll C:/Windows/System32/dxgi.dll
```

Needs Python with `pefile` and llvm-mingw clang. Regenerate on every build: edit the generator,
never its output.

**Which DLL to proxy:** read the exe's import table first. If the renderer is loaded at run time
instead (no `d3d*`/`dxgi` import), `dxgi.dll` usually catches DirectX 10–12, and `d3d9.dll` catches
DirectX 9. **Then read the log.** An app can import one renderer and draw with another; one 64-bit
Unreal Engine 3 game imported `d3d9.dll` but drew with Direct3D 11 `[verified-live 2026-09-17, n=1]`.

## ⚠️ Windows traps this already handles, so do not "simplify" them away

### 1. An export can be called BEFORE the proxy's DllMain runs

Windows' application-compatibility engine (`AcGenral.dll`) calls `dxgi.dll`'s
`SetAppCompatStringPointer` as soon as the DLL is mapped, before its `DllMain` runs
`[verified-live 2026-09-17, n=2 apps]` (seen in a debugger: the return address was inside AcGenral,
and the jump went to address 0).

What went wrong on the way to the current design:

| Version | Result |
| --- | --- |
| Fill the address table in `DllMain` only | **The app crashed at start-up**: the stub jumped through an empty table to address 0 |
| Load the real DLL from inside that early call | Fails with **error 1168**; the loader is busy with us |
| Guard the load with a lock | **The app hung.** Loading the real `dxgi.dll` calls straight back into our export, and the lock was already held |
| **Current** | Set up the log once. **Retry** the real load on every early call and in `DllMain`, holding no lock. An export that arrives before the real DLL exists gets **0**, and is not marked as seen, so the next call retries and forwards properly |

The "return 0" stand-in is **64-bit only**. A 32-bit `stdcall` export must pop its own arguments,
so a generic stand-in would corrupt the caller's stack. The 32-bit early case is therefore still
unhandled `[hypothesis]`; it was not seen on the one 32-bit app tested.

### 2. The first call must not disturb the call

- **64-bit:** the logging path saves `rcx rdx r8 r9` and `xmm0–xmm3`, keeps the stack 16-byte
  aligned around the C call, restores them, then jumps. Stack arguments are never touched.
- **32-bit:** saves `eax ecx edx`, logs, restores them, and reaches the real function with a `ret`,
  so the stack is exactly as the caller left it (stdcall, cdecl, fastcall and thiscall all work).
- `GetLastError` is preserved.

## Self-test (no app involved)

```
bash test/run_tests.sh [LIST_FILE]
```

- A fake "real" DLL checks integer, float, mixed, fastcall, stack and ordinal-only arguments through
  a generated proxy, 64- and 32-bit, on the logging call and on the plain-jump call.
- **`early` (64-bit)** calls an export from a loader notification, before `DllMain`, the same way
  the compatibility engine does. With the fix removed, this test crashes
  `[verified-numerically 2026-09-17]`.
- `LIST_FILE` adds your own built proxies (`<kind> <arch> <short> <dll path>`; kinds `dxgi`,
  `d3d9`, `d3d11`). Each is loaded, a harmless real export is called, and its log is checked.
- Exit `77` means skipped because Python/pefile or llvm-mingw is missing, and it says which.
  `LLVM_MINGW_BIN` can point at llvm-mingw's `bin` folder when it is not on `PATH`.
  The plugin's `smoke-test.sh` runs this and reports a skip rather than failing.

## Limits

- Data exports cannot be forwarded by a jump stub; the generator warns if it meets one. `dxgi`,
  `d3d9` and `d3d11` have none (checked 2026-09-17).
- The generated `.c` is long only because of the per-export stub list (dxgi about 450 lines, d3d11
  about 790), and its header says it is generated, so `code-shape-scan.py` skips it.
