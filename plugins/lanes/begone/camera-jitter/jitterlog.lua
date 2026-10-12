-- jitterlog.lua -- BeG0nE Camera Jitter ride-along for REFramework scripts (2026-10-08). Same file format and the
-- same three calls as jitterlog.h: pose read, camera write, picture presented. Writes only between vr_on() and
-- vr_off(), so a flat run writes nothing.
--
--   local jl = require("jitterlog")        -- put this file in reframework/autorun/ beside the script
--   jl.init("re-village-scope-vr", "openvr")
--   jl.vr_on()  /  jl.vr_off()
--   jl.pose(yaw, pitch, roll, x, y, z)     -- degrees; whatever angles the script already has
--   jl.camera(yaw, pitch, roll, x, y, z)
--   jl.present()
--   jl.hand("L"|"R", tracked, yaw, pitch, roll, x, y, z)   -- controllers, for Occlusion Drift BeG0nE
--
-- Time comes from os.clock(), which on Windows ticks in milliseconds; good enough to see a frame (11 ms at 90 Hz)
-- but the checker's "pose age" numbers from Lua are coarser than from the C header.

local jl = { on = false, f = nil, buf = {}, n = 0, t0 = 0, last_flush = 0, game = "game", runtime = "unknown" }

local FLUSH_LINES = 512          -- lines kept in memory before writing them out
local FLUSH_S = 1.0              -- ... or this long since the last write

local function now_us() return math.floor((os.clock() - jl.t0) * 1000000) end

local function folder()
    local base = os.getenv("LOCALAPPDATA") or "."
    local dir = base .. "\\BeG0nE\\jitter"
    os.execute('mkdir "' .. dir .. '" >nul 2>nul')
    return dir
end

local function flush()
    if jl.f and jl.n > 0 then
        jl.f:write(table.concat(jl.buf, "", 1, jl.n))
        jl.f:flush()
        jl.n = 0
    end
    jl.last_flush = os.clock()
end

local function write(kind, yaw, pitch, roll, x, y, z)
    if not jl.on then return end
    jl.n = jl.n + 1
    jl.buf[jl.n] = string.format("%d %s %.3f %.3f %.3f %.4f %.4f %.4f\n", now_us(), kind,
                                 yaw or 0, pitch or 0, roll or 0, x or 0, y or 0, z or 0)
    if jl.n >= FLUSH_LINES then flush() end
end

function jl.init(game, runtime)
    jl.game = game or jl.game
    jl.runtime = runtime or jl.runtime
end

function jl.vr_on()
    if jl.on then return end
    local path = string.format("%s\\%s_%s.jl", folder(), jl.game, os.date("%Y%m%d-%H%M%S"))
    jl.f = io.open(path, "wb")
    if not jl.f then return end
    jl.t0 = os.clock()
    jl.on = true
    jl.n = 1
    jl.buf[1] = string.format("#jitterlog 1 game=%s runtime=%s pid=lua\n", jl.game, jl.runtime)
    flush()
end

function jl.vr_off()
    if not jl.on then return end
    jl.on = false
    jl.n = jl.n + 1
    jl.buf[jl.n] = "#end\n"
    flush()
    jl.f:close()
    jl.f = nil
end

function jl.is_on() return jl.on end
function jl.pose(yaw, pitch, roll, x, y, z) write("P", yaw, pitch, roll, x, y, z) end
function jl.camera(yaw, pitch, roll, x, y, z) write("C", yaw, pitch, roll, x, y, z) end
function jl.hand(side, tracked, yaw, pitch, roll, x, y, z)
    if not jl.on then return end
    jl.n = jl.n + 1
    jl.buf[jl.n] = string.format("%d %s %.3f %.3f %.3f %.4f %.4f %.4f %d\n", now_us(), side == "L" and "L" or "R",
                                 yaw or 0, pitch or 0, roll or 0, x or 0, y or 0, z or 0, tracked and 1 or 0)
    if jl.n >= FLUSH_LINES then flush() end
end

function jl.mark(text) if jl.on then jl.n = jl.n + 1; jl.buf[jl.n] = string.format("%d M %s\n", now_us(), text) end end

function jl.present()
    if not jl.on then return end
    write("F", 0, 0, 0, 0, 0, 0)
    if os.clock() - jl.last_flush > FLUSH_S then flush() end
end

return jl
