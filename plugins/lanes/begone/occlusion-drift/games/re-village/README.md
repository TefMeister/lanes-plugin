# BeG0nE for Resident Evil Village

**Status: in testing. No download yet.** A download comes only after every long weapon passes the test in
the main README.

## What is here

`reframework/autorun/re8_vrz_begone_grip.lua`: the stacked two-handed grip, for REFramework's built-in RE8 VR
mode by praydog. Hold the left grip button with the left controller 3 to 35 cm above the right one. The weapon
then aims with the right hand alone, and the drawn left hand stays on the forestock.

It is VR only. On a flat screen it loads and does nothing.

Since 2026-10-01/02 it also takes over praydog's two-handed grip, worn and proven on 2026-10-02:

- **The grip spot is frozen when the grip is taken.** Praydog steers the weapon against the grip spot the game's
  animation gives him each frame, and the firing pose moves that spot by about five degrees, so the first shot after
  taking the grip jerked the rifle. The animation may move its own hand now; the weapon does not follow.
- **The grip is the script's own decision.** It takes when praydog docks (hand within 10 cm of the spot) and keeps
  holding while your real hand stays on the rifle, through the bolt action and the reload animation. Praydog's own
  dock drops the moment the animation swings his hand spot away, which snapped the rifle to one-handed aim at every
  shot; that no longer happens.
- **Auto-dock stays on.** The hand near the rifle grabs it, no button needed (Tefa's choice). `grip button 1` makes
  the left grip button the only way to grip, live.
- **The shot itself is covered.** Praydog re-runs his hand update inside the gun's shoot function; this file hooks
  the same function after him and puts its steering back before the bullet.
- **The frozen spot is only taken from a hand that can be trusted** (2026-10-02, not yet worn). After a relaunch
  the first dock froze the spot while the draw animation was still moving the hand, and the rifle pointed far right
  for the rest of the session. Now the spot is frozen only once the animation's hand has held still for 0.3 s, or
  sits within 10 cm of the captured rifle grip; until then praydog's own steering stays. A weapon change, or five
  seconds without a grip, forgets it. `grip forget` drops it live.

What remains is the game's own move: it turns the rifle toward its aim point in the frames before the bullet, one-handed
too; the scope mod's picture looks back a few frames to cover it.

It runs right after each of praydog's hand updates, using only REFramework's public Lua API, and checks itself: the
file recomputes the controller poses the way praydog's C++ does and compares its right hand with his on every
pass (`pose check: … the recompute is right` after 300 agreeing passes, `POSE CHECK FAILED` otherwise; 0.0 mm on
the first wear). Harness words: `grip button 0|1`, `grip freeze 0|1`, `grip check`, `grip forget`, `grip` (the state line, with
how far the hand sits from the frozen spot and when it is forgotten).

## Where it came from

On 2026-10-01 it was split out of the RE Village VR Scope mod (`re8_vrz_scope_left_grip.lua`, shipped in its
v1.0.0 and v1.0.1). The grip code itself was not changed. The scope mod keeps its weapon-click silencing and
left-menu-button fix in its own file.

## Shipped

**In the RE Village VR Scope mod v1.1.1 and v1.1.2 (2026-10-02), worn and confirmed by Tefa in the headset.** Since the split:

- The reference spot is frozen only once it can be trusted (held still 0.3 s, or within 10 cm of the captured rifle
  spot), and forgotten on a weapon change or after 5 s without a grip, so the rifle no longer points far right after a
  relaunch.
- The left hand docks by itself on any two-handed gun and lets go when it moves about 10 cm, or about 25 degrees
  sideways, from where it took the grip. Firing and the bolt do not drop it. Live word: `grip letgo <cm> <deg>`.
- The weapon in hand is read by name (as `re8_vr.lua` finds it), so the rifle's captured spot applies to the sniper
  rifle only, and every other gun keeps the game's own grip spot.
- A left hand on the pistol (grip spot under 15 cm from the right hand) rests on it but does not steer it.

## Not done yet

- **It still uses the scope's settings file** for the captured hand spot (`reframework/data/re_scope_left_grip.txt`),
  so a spot captured before the split keeps working.
- **Praydog has not been sent the grip rules upstream yet.**

## Test

`re-village-scope-vr` staging: `scripts/tests/grip_split_test.lua` loads this file and the scope's half
separately and checks that each one starts on its own and answers its words; `scripts/tests/begone_grip_fixes_test.lua`
checks the two fixes are on by default, answer their words, and that the steering maths turns the right way.
