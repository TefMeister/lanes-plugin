---
description: (Menu-o-matiC) Gets an app from launch to where the work happens, and back out, by replaying a recorded menu route, and records new routes while looking at as little of the screen as possible. A replay costs no model tokens; the model only looks when a checkpoint fails. Launching belongs to /lm (or the person's say-so); never from /pd, /gr, /sr or /gs.
---

`/menu` — **Menu-o-matiC.** Walks an app's menus by itself: start it, get through the intro, the title screen and
the menus to where the work happens, and quit through the menu at the end. Built for game modding, where one
session walks the same menus dozens of times.

The tool is `python "${CLAUDE_PLUGIN_ROOT}/tools/menu-o-matic/menu_o_matic.py"`, below `mom`. Its own `README.md`
beside it explains the route format. Windows only; needs Pillow (`python -m pip install pillow`).

## Which lane may use it

- **`/lm`**: yes, all of it, including routes that launch the app (typing `/lm` is the go-ahead to launch).
- **`/ms`**: only if the person asks for it in that session; the person is the hands there.
- **`/pd`, `/gr`, `/sr`, `/gs`**: never run it. They must not launch or drive anything. They may read and edit route
  files.
- Keys only ever go to the named window: the tool brings it to the front before every key and every picture, and
  stops with an error if it cannot. Do not work around that error; find out what is in the way.

## The rule that keeps it cheap

**Look big once, then only at small patches.** A full screenshot is about 1,200 input tokens at 1280×720; a
half-size one about 300; the patch around a menu often under 100. So:

1. **A route exists?** Look for `routes/<project>/*.json` in the project's control profile or notes. Run it:
   `mom run <route.json> --lost-dir <scratch folder>`. Exit **0**: you are there, no picture was needed.
2. **Exit 2 (lost):** the JSON line names the checkpoint, its note and two pictures. Read the **small patch first**
   (`lost-patch.png`). Only if the patch does not explain it, read the half-size `lost-full.png`. Usual causes: a
   pop-up (a firewall prompt, a news screen), a slower load (rerun with a longer `--timeout`), or the app changed.
   Fix it by hand with `mom press`, then continue with `mom run <route> --from <next step>`. If the app has changed
   for good, re-record that part.
3. **No route yet? Record one while you walk it:**
   - `mom new <route.json> --game "<name>" --window "<part of the window title>" --route <name>`, and
     `mom add <route.json> --launch <how it starts>` if it should start the app.
   - `mom look <window> <file> --scale 0.5` **once**, to see the first screen.
   - `mom press <window> <key> --route <route.json> --changed <crop.png>`: the key is recorded, and the tool saves
     only the patch that changed (it ignores anything that moves by itself). **Read the crop, not the screen.**
   - `mom look <window> <crop.png> --region x,y,w,h` to see that patch again after the next key.
   - When a screen is reached, `mom mark <window> <route.json> <name> --region x,y,w,h --note "<what it shows>"`.
     Pick a patch of **text or icons that does not animate**; the note is what a later session reads when lost.
   - Take a bigger picture again only when the patches stop making sense (a new screen, a pop-up).
   - If a key is sometimes ignored because a screen is still fading in, add `"repress": 4` to the wait step after
     it in the route file: the tool presses that key again every 4 seconds until the screen arrives.
4. **Save the route** with the project's control profile (`routes/<project>/<route>.json`) and commit it. A route
   holds fingerprints only, never a picture of the app, so it is safe to publish. **Never commit the screenshots.**

## Report

Say in one line which route ran and how far it got ("launch → main menu → city, 0 pictures"), or where it got lost
and what fixed it. A lost checkpoint that needed a fix is worth a line in the project's notes, so the route can be
repaired.
