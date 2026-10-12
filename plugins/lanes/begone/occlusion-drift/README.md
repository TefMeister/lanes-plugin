# Occlusion Drift BeG0nE

A cure for occlusion drift when aiming two-handed weapons in virtual reality, part of BeG0nE: 🩺 tools that remove unwanted
things from video games, for modders and gamers alike.

## The problem

In VR, most people hold a rifle or shotgun with the left hand stretched out in front of the right one. Seen from
the headset, the front hand hides the back one. The headset's cameras lose the hidden controller, and the weapon's
aim starts drifting by itself. That is **occlusion drift**.

## The cure

Hold the weapon with the **left controller sitting just above the right one**. The headset can see both
controllers all the time, so tracking never drops. The mod makes the game accept that hold as a proper
two-handed grip and keeps the weapon pointing exactly where your right hand points.

## What it is, and what it is not

- **It is** a small add-on for games that already have a VR mod. It changes where your left hand can hold a
  two-handed weapon, and nothing else.
- **It is not** a VR mod by itself. Every download says which game and which VR mod it needs.
- **It does not** touch the camera or the picture, so it carries no motion-sickness caution.
- **It contains** no game files, only our own code.

## Downloads

None yet. A game gets a download only after every long weapon in it has been tested in a headset and passes
one test: **the left controller sits visibly above the right one, and the aim does not drift when aiming down
the scope or the sights.**

| Game | Needs | Status |
| --- | --- | --- |
| [Resident Evil Village](games/re-village/) | REFramework (its built-in VR mode) | In testing |

## For modders, human or AI

Everything we have is here: the idea, the checklist of where to look in a new game, and the exact code that
made it work in each game. It is written in plain words and does not depend on any particular AI tool. Each
new game makes the guide better. The full design is in [`../docs/specs/`](../docs/specs/).
