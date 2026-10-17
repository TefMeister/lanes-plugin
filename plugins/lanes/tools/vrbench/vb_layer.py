"""vb_layer - switches the VR Bench layer on for one run, registered for the game's bitness only.

Why per bitness: the per-user OpenXR layer list is read by 32-bit and 64-bit games alike. Hand Freeze registers both
copies at once, and a stale list on the dev PC stopped a 32-bit game from starting on 2026-10-16. VR Bench registers
only the copy that matches the game, for the length of a run, and takes it off again at `stop`.

Two separate things are switched: the REGISTRATION (does the game load the layer at all) and the ENABLED file (does
the loaded layer act). `start` does both, `stop` undoes both. Nobody else's layers are ever touched.
LANES_VRBENCH_FAKEREG=<json file> stands in for the registry in tests.
"""
import json
import os
import re

import vb_settings as S

REG_KEY = r"Software\Khronos\OpenXR\1\ApiLayers\Implicit"
PE_OFFSET_AT = 0x3c
MACHINE_BITS = {0x14c: 32, 0x8664: 64}
OURS = {S.LAYER_JSON64.lower(), S.LAYER_JSON32.lower()}


# ---- the registry, behind one small shim ------------------------------------------------------------------------
def _fake():
    return os.environ.get("LANES_VRBENCH_FAKEREG")


def _reg_values():
    if _fake():
        try:
            with open(_fake(), encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            return {}
    import winreg
    out = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            i = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = data
                i += 1
    except FileNotFoundError:
        pass
    return out


def _reg_set(name):
    if _fake():
        vals = _reg_values()
        vals[name] = 0
        with open(_fake(), "w", encoding="utf-8") as f:
            json.dump(vals, f)
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, 0)   # 0 = enabled, in the loader's terms


def _reg_delete(name):
    if _fake():
        vals = _reg_values()
        vals.pop(name, None)
        with open(_fake(), "w", encoding="utf-8") as f:
            json.dump(vals, f)
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


# ---- the switch -------------------------------------------------------------------------------------------------
def exe_bits(path):
    """32 or 64, from the exe's PE header; ValueError when it is not a Windows program"""
    with open(path, "rb") as f:
        head = f.read(PE_OFFSET_AT + 4)
        if head[:2] != b"MZ" or len(head) < PE_OFFSET_AT + 4:
            raise ValueError(f"{os.path.basename(path)} is not a Windows program")
        f.seek(int.from_bytes(head[PE_OFFSET_AT:PE_OFFSET_AT + 4], "little"))
        pe = f.read(6)
    if pe[:4] != b"PE\0\0" or int.from_bytes(pe[4:6], "little") not in MACHINE_BITS:
        raise ValueError(f"{os.path.basename(path)}: unknown program type")
    return MACHINE_BITS[int.from_bytes(pe[4:6], "little")]


def manifest_for(bits):
    return os.path.join(S.LAYER_DIR, S.LAYER_JSON32 if bits == 32 else S.LAYER_JSON64)


def _is_ours(name):
    return os.path.basename(name).lower() in OURS


def registered():
    return sorted(n for n in _reg_values() if _is_ours(n))


def register(bits):
    m = manifest_for(bits)
    if not os.path.isfile(m):
        raise FileNotFoundError(f"the VR Bench layer is not installed ({bits}-bit manifest missing); run its install.ps1")
    _reg_set(m)


def unregister_all():
    """every VR Bench manifest, wherever it lives (an old install folder too); nobody else's"""
    for n in registered():
        _reg_delete(n)


def enable():
    os.makedirs(S.STATE_DIR, exist_ok=True)
    with open(S.ENABLED_FILE, "w", encoding="utf-8") as f:
        f.write("on\n")


def disable():
    try:
        os.remove(S.ENABLED_FILE)
    except FileNotFoundError:
        pass


def start(exe):
    bits = exe_bits(exe)
    unregister_all()
    register(bits)
    enable()
    return bits


def stop():
    disable()
    unregister_all()


# ---- which exe a game name means ---------------------------------------------------------------------------------
def _conf_files():
    if os.environ.get("LANES_CONFIG"):
        return [os.environ["LANES_CONFIG"]]
    home = os.path.expanduser("~")
    return [os.path.join(home, ".claude", "lanes.conf"), os.path.join(home, ".config", "lanes", "lanes.conf")]


def _conf_get(key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*(?:\s#.*)?$")
    for path in _conf_files():
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = pat.match(line.rstrip("\r\n"))
                    if m and not line.lstrip().startswith("#"):
                        return m.group(1).strip().strip('"').strip("'")
        except OSError:
            pass
    return ""


def resolve_exe(target):
    """an exe path as given; else `vrbench_exe.<game>` in lanes.conf; else the only exe in `builds_app.<game>`"""
    if os.path.isfile(target):
        return target
    exe = _conf_get(f"vrbench_exe.{target}")
    if exe and os.path.isfile(exe):
        return exe
    folder = _conf_get(f"builds_app.{target}")
    if folder and os.path.isdir(folder):
        exes = [f for f in os.listdir(folder) if f.lower().endswith(".exe")]
        if len(exes) == 1:
            return os.path.join(folder, exes[0])
        raise LookupError(f"{target}: {len(exes)} programs in its folder; name the game's with "
                          f"`vrbench_exe.{target} = <path>` in lanes.conf")
    raise LookupError(f"{target}: not a program, and lanes.conf has no vrbench_exe.{target} or builds_app.{target}")
