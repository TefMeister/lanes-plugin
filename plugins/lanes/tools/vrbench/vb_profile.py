"""vb_profile - what this PC is, for VR Bench: specs, the OpenXR runtimes, whether a headset can be worn, the tier.

The TIER sets how hard VR Bench works a game: `light` (fewer hand positions, shorter clips) on a PC that would
struggle with a VR game plus the simulator, `full` otherwise. Chosen from the specs; `bench_tier =` in lanes.conf
overrides it. `bench_headset = real | none` (set by setup) says whether a real headset can be worn here; nothing
on the PC can tell that reliably, so it is asked once rather than guessed.

    collect(conf, probes) -> dict     probes: the real Probes() below, or a fake in tests
"""
import ctypes
import glob
import json
import os
import platform
import re
import subprocess
import time

import vb_settings as S

# full: NVIDIA GeForce 2000-series and newer, AMD Radeon RX 6000/7000/9000, Intel Arc; a GTX 1660 (the dev PC) and
# older stay light. Matched by model number, so a card name never has to be spelled out here.
GPU_FULL_RE = re.compile(r"GeForce \w+ [2-9]\d{3}\b|Radeon RX [679]\d{3}\b|\bArc\b", re.I)
RAM_FULL_GB = 24
RUNTIME_KEYS = {64: r"SOFTWARE\Khronos\OpenXR\1", 32: r"SOFTWARE\WOW6432Node\Khronos\OpenXR\1"}
PROBE_TIMEOUT_S = 60


def tier(gpus, ram_gb):
    if ram_gb < RAM_FULL_GB:
        return "light"
    return "full" if any(GPU_FULL_RE.search(g) for g in gpus) else "light"


class Probes:
    """the real PC; every probe answers something even when it cannot look (empty, 0, or 'unknown')"""

    def cpu(self):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
        except Exception:
            return platform.processor() or "unknown"

    def gpus(self):
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-CimInstance Win32_VideoController).Name"],
                               capture_output=True, text=True, timeout=PROBE_TIMEOUT_S)
            return [line.strip() for line in r.stdout.splitlines() if line.strip()]
        except Exception:
            return []

    def ram_gb(self):
        class MemStatus(ctypes.Structure):
            _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong),
                        ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("vx", ctypes.c_ulonglong)]
        try:
            m = MemStatus()
            m.len = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.total / 2 ** 30)
        except Exception:
            return 0

    def windows(self):
        return f"{platform.system()} {platform.release()} ({platform.version()})"

    def runtime(self, bits):
        """the active OpenXR runtime's file NAME (not its folder: profiles stay free of paths)"""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, RUNTIME_KEYS[bits]) as k:
                return os.path.basename(winreg.QueryValueEx(k, "ActiveRuntime")[0])
        except Exception:
            return None

    def games(self):
        """Steam's own list of fully installed games, by name (a folder listing lies; manifests do not)"""
        names = []
        for lib in _steam_libraries():
            for acf in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
                try:
                    text = open(acf, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                name = re.search(r'"name"\s+"([^"]+)"', text)
                if name:
                    names.append(name.group(1))
        return sorted(set(names))


def _steam_libraries():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            steam = winreg.QueryValueEx(k, "SteamPath")[0]
    except Exception:
        return []
    libs = [steam]
    try:
        vdf = open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace").read()
        libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
    except OSError:
        pass
    return sorted({os.path.normcase(os.path.normpath(p)) for p in libs})


def collect(conf, probes):
    gpus, ram = probes.gpus(), probes.ram_gb()
    t = conf.get("bench_tier") if conf.get("bench_tier") in ("light", "full") else tier(gpus, ram)
    return {"cpu": probes.cpu(), "gpus": gpus, "ram_gb": ram, "windows": probes.windows(),
            "runtime64": probes.runtime(64), "runtime32": probes.runtime(32),
            "headset": conf.get("bench_headset") if conf.get("bench_headset") in ("real", "none") else "none",
            "tier": t, "games": probes.games(), "written": time.strftime("%Y-%m-%d %H:%M:%S")}


def write(profile):
    os.makedirs(S.STATE_DIR, exist_ok=True)
    tmp = S.PROFILE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=1)
    os.replace(tmp, S.PROFILE_FILE)
    return S.PROFILE_FILE


def read():
    try:
        with open(S.PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
