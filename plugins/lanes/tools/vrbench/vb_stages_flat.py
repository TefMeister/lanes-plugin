"""vb_stages_flat - the flat-screen stages: launch, menus, and flat movement (still camera first).

These go through Menu-o-matiC as it is today, which brings the game to the front to press keys; background input
(benchinput.h) is plan 2. The quit route (gameplay -> desktop) is only checked for, never replayed here: the VR
stages still need the game running, and the standing rule leaves it running at the end.
"""
STILL_DIFFERENCE = 1.5      # Menu-o-matiC's: pictures closer than this count as the same picture
TURN_STEPS = 4
TURN_STEP_PX = 120          # one mouse turn step; about 25 degrees in most games at default sensitivity
TURNS_NEEDED = 3            # of TURN_STEPS, for a PASS
FLAT_KEYS = ("w", "a", "s", "d")
KEY_HOLD_S = 1.5
MENU_GOALS = (("launch", "gameplay"), ("launch", "keybindings"), ("gameplay", "desktop"))
REPLAYED_GOALS = {("launch", "keybindings")}   # launch -> gameplay is the launch stage; the quit route is not replayed


def launch(L):
    route = L.tools.find_route("launch", "gameplay")
    if not route:
        return L.verdict("launch", "UNKNOWN", "no launch route yet: record one with the person, or let plan 2's "
                         "learn-by-looking loop build it")
    res = L.tools.mom(["run", route])
    if res["code"] == 0:
        return L.verdict("launch", "PASS", "the launch route reached gameplay")
    return L.verdict("launch", "CHECK", f"the launch route stopped (Menu-o-matiC exit {res['code']})")


def menus(L):
    found, rows = 0, []
    for goal in MENU_GOALS:
        route = L.tools.find_route(*goal)
        label = " -> ".join(goal)
        if not route:
            rows.append(f"{label}: no route")
            continue
        found += 1
        if goal in REPLAYED_GOALS:
            ok = L.tools.mom(["run", route])["code"] == 0
            rows.append(f"{label}: {'replayed' if ok else 'stopped'}")
        else:
            rows.append(f"{label}: route on file")
    if found == 0:
        return L.verdict("menus", "UNKNOWN", "; ".join(rows))
    return L.verdict("menus", "PASS" if found == len(MENU_GOALS) else "CHECK", "; ".join(rows))


def flat(L):
    t = L.tools
    before = t.flat_shot("flat_still")
    if not before:
        return L.verdict("flat", "UNKNOWN", "no picture of the game window")
    changed, last = 0, before
    for i in range(TURN_STEPS):
        pic = t.turn(TURN_STEP_PX, f"flat_turn_{i + 1}")
        if pic and t.picture_diff(last, pic) > STILL_DIFFERENCE:
            changed += 1
        last = pic or last
    keys = [k for k in FLAT_KEYS if t.probe(k, KEY_HOLD_S)]
    how = f"mouse turned the view {changed} of {TURN_STEPS} times; keys that moved the picture: {', '.join(keys) or 'none'}"
    if changed >= TURNS_NEEDED:
        L.known_add("Controls", f"flat: the mouse turns the view; {', '.join(keys) or 'no'} movement keys seen to work "
                    f"(VR Bench)")
        return L.verdict("flat", "PASS", how, last)
    return L.verdict("flat", "CHECK", how, last)
