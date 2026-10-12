-- ghosthand.lua -- Ghost Hand BeG0nE recorder for REFramework scripts (Lanes 0.62.0, 2026-10-12).
-- Writes, while a headset session runs, where the real controllers are, where the game draws the hands, the
-- weapon's moving parts, what the mod measured, and when each hand gesture starts and ends. Lanes' rider files the
-- log when the session ends and ghost_hand_check.py turns it into a short report. A flat run writes nothing.
--
--   local gh = require("ghosthand")          -- put this file in reframework/autorun/ beside the script
--   gh.init("visceral-re2-vr", "openxr")
--   gh.vr_on()  /  gh.vr_off()
--   -- once per frame, all positions in the SAME space (game world, metres):
--   gh.real("L"|"R", tracked, x, y, z)      -- the controller as the headset tracks it
--   gh.game("L"|"R", x, y, z)               -- the hand the game draws (a wrist or palm bone)
--   gh.part("slide", x, y, z)               -- a moving part of the weapon (slide, pump, magazine, muzzle)
--   gh.value("rack", 0.82)                  -- what the mod measured (a pull ratio, a distance, a state)
--   gh.button("LG", true)                   -- a button that matters for the gesture
--   gh.frame()                              -- end of the frame
--   -- around every hand gesture:
--   gh.event("rack", "start")  ...  gh.event("rack", "done" | "fail" | "cancel")
--   gh.value("rack_need", 0.06)             -- optional: how far (metres) the gesture needs, so misses can be judged
--
-- Time comes from os.clock() (milliseconds on Windows): enough to see a frame at 90 Hz.

local gh = { on = false, f = nil, buf = {}, n = 0, t0 = 0, last_flush = 0, game = "game", runtime = "unknown" }

local FLUSH_LINES = 1024         -- lines kept in memory before writing them out
local FLUSH_S = 1.0              -- ... or this long since the last write

local function now_us() return math.floor((os.clock() - gh.t0) * 1000000) end

local function folder()
    local base = os.getenv("LOCALAPPDATA") or "."
    local dir = base .. "\\BeG0nE\\ghost-hand"
    os.execute('mkdir "' .. dir .. '" >nul 2>nul')
    return dir
end

local function flush()
    if gh.f and gh.n > 0 then
        gh.f:write(table.concat(gh.buf, "", 1, gh.n))
        gh.f:flush()
        gh.n = 0
    end
    gh.last_flush = os.clock()
end

local function put(line)
    if not gh.on then return end
    gh.n = gh.n + 1
    gh.buf[gh.n] = line
    if gh.n >= FLUSH_LINES then flush() end
end

local function word(s) return (tostring(s or "?"):gsub("%s+", "_")) end

function gh.init(game, runtime)
    gh.game = game or gh.game
    gh.runtime = runtime or gh.runtime
end

function gh.vr_on()
    if gh.on then return end
    local path = string.format("%s\\%s_%s.ghl", folder(), gh.game, os.date("%Y%m%d-%H%M%S"))
    gh.f = io.open(path, "wb")
    if not gh.f then return end
    gh.t0 = os.clock()
    gh.on = true
    gh.n = 1
    gh.buf[1] = string.format("#ghosthand 1 game=%s runtime=%s\n", gh.game, gh.runtime)
    flush()
end

function gh.vr_off()
    if not gh.on then return end
    put("#end\n")
    flush()
    gh.on = false
    gh.f:close()
    gh.f = nil
end

function gh.is_on() return gh.on end

function gh.real(side, tracked, x, y, z)
    put(string.format("%d R %s %d %.4f %.4f %.4f\n", now_us(), side == "L" and "L" or "R", tracked and 1 or 0,
                      x or 0, y or 0, z or 0))
end

function gh.game(side, x, y, z)
    put(string.format("%d G %s %.4f %.4f %.4f\n", now_us(), side == "L" and "L" or "R", x or 0, y or 0, z or 0))
end

function gh.part(name, x, y, z)
    put(string.format("%d P %s %.4f %.4f %.4f\n", now_us(), word(name), x or 0, y or 0, z or 0))
end

function gh.value(name, v)
    put(string.format("%d V %s %.5f\n", now_us(), word(name), tonumber(v) or 0))
end

function gh.button(name, down)
    put(string.format("%d B %s %d\n", now_us(), word(name), down and 1 or 0))
end

function gh.event(name, what)
    put(string.format("%d E %s %s\n", now_us(), word(name), word(what)))
end

function gh.frame()
    if not gh.on then return end
    put(string.format("%d F\n", now_us()))
    if os.clock() - gh.last_flush > FLUSH_S then flush() end
end

return gh
