"""guard_runner.py -- runs several of this folder's guard hooks inside ONE Python process (0.105.0, 2026-11-06).

Not a hook itself: tool-guards.py (PreToolUse) and prompt-guards.py (UserPromptSubmit) call run() with their list.

Why: the 2026-11-06 audit measured six Lanes guard programs starting for every shell command (plus RTK), about 2.5 s
per command on the low-powered dev PC, roughly eight hours over four weeks. Most of that is starting Python six times.
Here each guard file runs exactly as it would on its own (runpy, as __main__, with the same hook input on its stdin),
one after another, and its answer is read the same way Claude Code would read it:

  * exit 2              -> the guard refused; its reason is already on stderr; stop and exit 2.
  * JSON "deny"/"block" -> stop and pass that answer on unchanged.
  * JSON "ask"          -> remembered; the later guards still run (a later refusal wins); "ask" is passed on at the end.
  * additionalContext / systemMessage -> gathered and passed on as one answer.
  * anything else (exit 0 or 1, an exception inside a guard) -> that guard lets the call through; the next one runs.

The guard files stay as they are and are still run one by one by the tests. Never fails closed: an error in the
runner itself lets the call through (exit 0), like every guard here.
"""
import io
import json
import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _one(path, args, raw):
    """(exit code, text the guard printed) for one guard file run in this process."""
    out = io.BytesIO()
    outw = io.TextIOWrapper(out, encoding="utf-8", errors="replace", write_through=True)
    inw = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", errors="replace")
    saved = sys.stdin, sys.stdout, sys.argv
    sys.stdin, sys.stdout, sys.argv = inw, outw, [path] + list(args)
    code = 0
    try:
        runpy.run_path(path, run_name="__main__")
    except SystemExit as e:
        if e.code is None:
            code = 0
        elif isinstance(e.code, int):
            code = e.code
        else:                                   # sys.exit("text"): Python prints it and exits 1
            sys.stderr.write(str(e.code) + "\n")
            code = 1
    except Exception:  # noqa: BLE001 - a broken guard lets the call through, as it would on its own
        code = 0
    finally:
        try:
            outw.flush()
        except Exception:  # noqa: BLE001
            pass
        sys.stdin, sys.stdout, sys.argv = saved
    return code, out.getvalue().decode("utf-8", "replace").strip()


def run(guards, raw, event, plain_text_is_context=False):
    """Run each (script, args) in `guards` on the hook input `raw` (bytes). Writes the merged answer; returns the
    exit code for the hook. `plain_text_is_context`: at UserPromptSubmit plain printed text reaches the session."""
    contexts, messages, ask = [], [], None
    for script, args in guards:
        path = os.path.join(HERE, script)
        if not os.path.isfile(path):
            continue
        code, text = _one(path, args, raw)
        if code == 2:
            return 2
        if not text:
            continue
        try:
            d = json.loads(text)
        except ValueError:
            if plain_text_is_context:
                contexts.append(text)
            continue
        if not isinstance(d, dict):
            continue
        hso = d.get("hookSpecificOutput") or {}
        if hso.get("permissionDecision") == "deny" or d.get("decision") == "block" or d.get("continue") is False:
            sys.stdout.write(text)
            return 0
        if hso.get("permissionDecision") == "ask" and ask is None:
            ask = hso.get("permissionDecisionReason") or ""
        if hso.get("additionalContext"):
            contexts.append(str(hso["additionalContext"]).strip())
        if d.get("systemMessage"):
            messages.append(str(d["systemMessage"]).strip())
    answer = {}
    hso = {}
    if ask is not None:
        hso.update({"permissionDecision": "ask", "permissionDecisionReason": ask})
    if contexts:
        hso["additionalContext"] = "\n\n".join(contexts)
    if hso:
        hso["hookEventName"] = event
        answer["hookSpecificOutput"] = hso
    if messages:
        answer["systemMessage"] = "\n".join(messages)
    if answer:
        sys.stdout.write(json.dumps(answer))
    return 0


def read_input():
    try:
        return sys.stdin.buffer.read()
    except Exception:  # noqa: BLE001
        return b""


def parse(raw):
    try:
        d = json.loads(raw.decode("utf-8-sig", "replace") or "{}")
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}
