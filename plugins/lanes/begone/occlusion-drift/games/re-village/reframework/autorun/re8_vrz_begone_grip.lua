-- re8_vrz_begone_grip.lua -- BeG0nE for Resident Evil Village: the stacked two-handed grip and the drawn left
-- hand. VR only. Split out of the scope mod's re8_vrz_scope_left_grip.lua on 2026-10-01 (Tefa: "the Dr.BeGonE part
-- extracted only for VR"); the code below is unchanged except: the 'grip sound' / 'grip anim' words moved with the
-- probes to the scope's re8_vrz_scope_sounds_menu.lua, and the state line no longer counts silenced clicks.
-- Still gated on the scope's rifle camera (st.clone_go), so today it only acts with the sniper rifle and the scope
-- mod installed. Making it stand alone for every long weapon is the next step (BeG0nE design spec, section 4).
--
-- 2026-10-01 (evening, home PC): THE TWO FIXES FROM THE PATCHED LOADER NOW LIVE HERE -- see "THE TWO FIXES" below.
-- 2026-10-02 (home PC): THE FROZEN SOCKET IS ONLY EVER TAKEN FROM A SOCKET THAT CAN BE TRUSTED -- see "A TRUSTWORTHY
-- SOCKET" below. After a relaunch the rifle pointed far right: the first auto-dock froze the socket while the draw
-- animation was still moving the hand, and every re-take for the rest of the session kept that wrong spot.
--
-- re8_vrz_scope_left_grip.lua -- ONE left-hand grip spot on the rifle (2026-09-27, Tefa in the headset).
--
-- WHY: Tefa: "when the left hand is gripping the rifle, it has 3 different holding animations - one puts the hand on the
-- rifle iron barrel when holding it at a certain angle, and then sometimes two hand positions seem to be fighting when
-- holding the hand under the rifle". praydog's RE8VR::update_hand_ik (REFramework src/mods/vr/games/RE8VR.cpp) does not use
-- a fixed grip spot: every frame it takes the game ANIMATION's left-hand joint relative to the right hand
-- (`original_left_pos_relative`) and puts the docked left hand there, so every hold animation the game plays (normal, aim,
-- blends) moves the hand [inferred-static 2026-09-27].
--
-- WHAT: after REFramework's last update_hand_ik of the frame (re8_vr.lua, pre-PrepareRendering -- this file is named re8_vrz_*
-- so it loads, and registers, after re8_vr.lua), while the left hand is docked on the weapon, the left IK target is put back
-- at ONE spot in the right hand's frame -- the one captured with `grip capture` -- and the IK is solved again.
--
-- Words (harness):
--   grip probe 1|0   log the game's current grip spot (right-hand frame) whenever it moves > GRIP_PROBE_STEP
--   grip capture     keep the spot the hand is in RIGHT NOW (hold the rifle the way that looks right first); saved
--   grip capture <s> the same after <s> seconds, so the wearer can settle into the grip first (the probe stays quiet meanwhile)
--   grip on|off      apply the captured spot / leave the game's own
--   grip button 1|0  the left grip button is the only way to take the grip (1) / praydog's 10 cm dock too (0, default)
--   grip freeze 1|0  steer against the socket frozen at the take (1, default) / the live animation socket (0)
--   grip check       print the pose check (our recomputed right hand against REFramework's own)
--   grip forget      drop the frozen socket now (the next dock freezes a fresh one, once it can be trusted)
--   grip             print the state
-- File: reframework/data/re_scope_left_grip.txt  ("on px py pz qw qx qy qz"). No file = off.
-- Only while the rifle camera exists (st.clone_go), i.e. only with the sniper rifle out.

local TAG = "[re8-grip] "
local function L(s) log.info(TAG .. tostring(s)) end
local function safe(f) local ok, r = pcall(f) if ok then return r end return nil end

local GRIP_FILE = "re_scope_left_grip.txt"
local GRIP_PROBE_STEP = 0.01     -- metres: a grip spot change smaller than this is not logged
local GRIP_PROBE_MIN_S = 0.1     -- seconds between probe lines

local g = { on = false, pos = nil, rot = nil, probe = false, last = nil, last_t = 0.0, applied = 0, fingers = {} }

-- 2026-09-27 (Tefa, second wear): the hand stayed put, but "is still changing finger animations, like it was holding on
-- to a different part" -- the finger curl comes from the game's animation too. So the captured grip also keeps the finger
-- joints' local rotations, written back every frame after the IK solve. Names read live 2026-09-27 from the player's joints.
local FINGER_JOINTS = { "L_Thumb1", "L_Thumb2", "L_Thumb3", "L_IndexF1", "L_IndexF2", "L_IndexF3", "L_MiddleF1", "L_MiddleF2",
    "L_MiddleF3", "L_RingF1", "L_RingF2", "L_RingF3", "L_PinkyF1", "L_PinkyF2", "L_PinkyF3" }
local joint_cache = {}   -- name -> via.Joint (refreshed when the player transform changes)
local joint_cache_tf = nil

local function finger_joint(name)
    local v = rawget(_G, "re8vr")
    local tf = v ~= nil and v.transform or nil
    if tf == nil then return nil end
    if tf ~= joint_cache_tf then joint_cache, joint_cache_tf = {}, tf end
    local j = joint_cache[name]
    if j == nil then
        j = safe(function() return tf:call("getJointByName", name) end)
        joint_cache[name] = j
    end
    return j
end

local function st() return _G.re8_scope_st end
local function vr() return rawget(_G, "re8vr") end

local function save()
    if g.pos == nil or g.rot == nil then return end
    local s = string.format("%d %.6f %.6f %.6f %.6f %.6f %.6f %.6f\n", g.on and 1 or 0, g.pos.x, g.pos.y, g.pos.z,
        g.rot.w, g.rot.x, g.rot.y, g.rot.z)
    for _, n in ipairs(FINGER_JOINTS) do
        local q = g.fingers[n]
        if q ~= nil then s = s .. string.format("f %s %.6f %.6f %.6f %.6f\n", n, q.w, q.x, q.y, q.z) end
    end
    pcall(fs.write, GRIP_FILE, s)
end

local function load()
    local s = safe(function() return fs.read(GRIP_FILE) end)
    if s == nil or s == "" then return end
    local first = s:match("^[^\n]*") or ""
    for n, w, x, y, z in s:gmatch("f%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)") do
        g.fingers[n] = Quaternion.new(tonumber(w), tonumber(x), tonumber(y), tonumber(z)):normalized()
    end
    local v = {}
    for w in first:gmatch("%S+") do v[#v + 1] = tonumber(w) end
    if #v < 8 then return end
    g.on = v[1] == 1
    g.pos = Vector3f.new(v[2], v[3], v[4])
    g.rot = Quaternion.new(v[5], v[6], v[7], v[8]):normalized()
    L(string.format("loaded: %s, spot (%.3f, %.3f, %.3f)", g.on and "ON" or "off", g.pos.x, g.pos.y, g.pos.z))
end

-- the current hand targets, as REFramework set them this frame
local function hands()
    local v = vr()
    if v == nil then return nil end
    local lt, rt = v.left_hand_ik_transform, v.right_hand_ik_transform
    if lt == nil or rt == nil then return nil end
    local lp = safe(function() return lt:call("get_Position") end)
    local lr = safe(function() return lt:call("get_Rotation") end)
    local rp = safe(function() return rt:call("get_Position") end)
    local rr = safe(function() return rt:call("get_Rotation") end)
    if lp == nil or lr == nil or rp == nil or rr == nil then return nil end
    return lp, lr, rp, rr
end

local function relative(lp, lr, rp, rr)
    local inv = rr:inverse()
    return inv * (lp - rp), (inv * lr):normalized()
end

local function capture_now()
    local lp, lr, rp, rr = hands()
    if lp == nil then L("capture: no hand targets yet") return end
    g.pos, g.rot = relative(lp, lr, rp, rr)
    g.on = true
    local nf = 0
    for _, n in ipairs(FINGER_JOINTS) do
        local j = finger_joint(n)
        local q = j ~= nil and safe(function() return j:call("get_LocalRotation") end) or nil
        if q ~= nil then g.fingers[n] = q nf = nf + 1 end
    end
    save()
    L(string.format("capture: spot (%.3f, %.3f, %.3f) and %d finger joint(s) kept, ON; docked=%s", g.pos.x, g.pos.y, g.pos.z,
        nf, tostring(vr() and vr().was_gripping_weapon)))
end

local function fingers_apply()
    for n, q in pairs(g.fingers) do
        local j = finger_joint(n)
        if j ~= nil then safe(function() j:call("set_LocalRotation", q) end) end
    end
end

-- ---- THE TWO FIXES (2026-10-01, Tefa: "make the gun not jump left when shooting two handed and also make the gun only
-- grippable by LG" -- LG is the left grip button).
--
-- praydog's RE8VR::update_hand_ik (stock REFramework a24c3459, the loader players install) decides the two-handed grip
-- every frame:  docked = the left hand within 10 cm of the ANIMATION's grip socket, OR (was docked AND the left grip
-- button is held).  While docked it turns the rifle so the socket line matches the real hand line -- measured against
-- the socket the animation gives it THAT frame. Two faults, both worn and fixed in our patched loader on 2026-09-21/22
-- (re-village-scope-vr dossier 9cg and 9ci, grip-no-throw.patch), lost again when the loader went back to stock:
--   1. THE JUMP. The first trigger pull after a take plays the firing pose, the animation's socket moves, and the gun
--      follows it: 4.6-5.1 deg on every first shot after a take, 0.6-0.8 deg on shots with the hand kept on
--      [verified-live 2026-09-21, n=10 shots]. Fix: the socket the steering measures against is FROZEN at the take.
--      The animation may move its own hand; the gun does not follow it.
--   2. DOCKING WITHOUT THE BUTTON. Anything within 10 cm of the socket docked, while the hand was still travelling up to
--      the rifle, and the rest of the travel became steering. Fix: no left grip button, no grip. The button is the switch.
-- The loader is stock now, so both are done HERE, right after update_hand_ik has run (three times a frame, where re8_vr.lua
-- calls it): the controller poses are computed again the way the C++ does (same inputs, same offsets), the grip decision
-- is remade, and both hands' IK targets are set once more. The recompute PROVES ITSELF: the right hand's position from
-- the C++ is compared with ours on every pass (and its rotation too, whenever the C++ is not steering), the log says when
-- 300 passes agreed, and shouts if they ever do not. `grip check` prints the figures.
-- Steering is the shortest turn from the frozen socket line to the real hand line (no roll invented, the right wrist
-- keeps its roll) -- the maths the loader's corrected build used from 2026-09-21 19:00 on. [hypothesis] that it feels the
-- same as that build; the first wear says.
local GRIP_NEEDS_BUTTON  = false   -- fix 2: the left grip button is the only way to dock. OFF by default since
                                   -- 2026-10-02 00:40 (Tefa: "re-enable the hand docking the gun automatically but
                                   -- remove the janking"); `grip button 1` turns it on live
local GRIP_FREEZE_SOCKET = true    -- fix 1: steer against the socket frozen at the take
local POSE_CHECK_WARN_M   = 0.003  -- metres: our recomputed right hand further than this from REFramework's = wrong
local POSE_CHECK_WARN_DEG = 0.5    -- degrees: same for its rotation (checked only when the C++ is not steering)
local POSE_CHECK_EVERY_S  = 5.0    -- seconds between warnings
local POSE_CHECK_PASSES   = 300    -- agreeing passes before the recompute is called right
local DRIFT_LOG_STEP_DEG  = 1.0    -- log the animation moving the socket each time it grows by this much
local GRIP_DOCK_M         = 0.10   -- metres: the hand this close to the FROZEN socket takes the grip (praydog's 10 cm)
local GRIP_RELEASE_M      = 0.18   -- (stacked zone only now) metres
local GRIP_RELEASE_DEG    = 70     -- (unused since 2026-10-02 afternoon, kept for the state line)
-- 2026-10-02 afternoon (Tefa: "i had to separate my hands a lot more to get the left hand to come off the gun"):
-- the keep-test only measured the hand's DISTANCE from the right hand against an 18 cm band, plus a 70 deg angle,
-- and praydog's own dock kept the grip too. Pulling the hand sideways barely counted. Now the grip lets go when the
-- hand moves this far from WHERE IT WAS when the grip was taken, in distance OR in angle, whichever comes first.
-- praydog's dock no longer keeps a grip we hold; it only starts one.
local GRIP_LETGO_M        = 0.10   -- metres: the left hand closer/further than this from its distance at the take
local GRIP_STEER_MIN_M    = 0.15   -- metres: a grip socket closer than this to the right hand (the pistol's is ~6 cm) is a
                                   -- support hand on a one-handed gun: the left hand is drawn on it but does NOT steer it
                                   -- (Tefa, 2026-10-02 13:58: "with left hand on the pistol, i can steer it with left
                                   -- motion controller"). Two-handed guns (shotgun, rifle) sit at 39-46 cm.
local GRIP_LETGO_DEG      = 25     -- degrees: the left hand swung this far around the right hand from its line at the take
local SHOT_TRACE_PASSES   = 0      -- passes logged after each shot (3 per frame): the shot-jump instrument
local REDOCK_KEEP_S       = 3.0    -- a grip re-taken within this many seconds of letting go keeps the socket frozen
                                   -- earlier (2026-10-02 00:45: after a shot the bolt animation swings the socket ~50 deg,
                                   -- the auto-dock drops and re-takes mid-animation, and a fresh freeze there snapped
                                   -- the rifle sideways -- Tefa: "it over corrected")
-- ---- A TRUSTWORTHY SOCKET (2026-10-02 01:10, Tefa after a relaunch: the rifle pointed far right at strange angles).
-- The log: the first auto-dock after the relaunch froze the socket at (0.100, -0.437, 0.176) -- 48 cm from the right hand
-- and still moving 1.9 deg per pass, the draw animation's hand, not the rifle's grip at (-0.367, -0.142, -0.001) -- and
-- the re-take rule above kept that spot for every grip after it, 82 deg off the real socket. So a socket is FROZEN only
-- when it can be trusted: it has held still for SOCKET_STEADY_S, or it sits within SOCKET_KNOWN_M of the captured rifle
-- spot. Until then praydog's own live-socket steering stays. The frozen spot is also forgotten when the weapon changes
-- and after FROZEN_FORGET_S without any grip, so a stale spot can never outlive the thing it was measured on.
local FROZEN_FORGET_S     = 5.0    -- seconds without any grip after which the frozen socket is forgotten
local SOCKET_STEADY_S     = 0.3    -- seconds the live socket must hold still before a first freeze trusts it
local SOCKET_STEADY_M     = 0.01   -- metres: the live socket straying further than this from where the wait began restarts it
local SOCKET_KNOWN_M      = 0.10   -- metres: a live socket this close to the captured rifle spot is trusted at once
local WAIT_LOG_EVERY_S    = 1.0    -- seconds between "not trusted yet" lines while praydog steers

local S = { take = nil, takes = 0, undone = 0, undone_logged = false, steer_deg = 0, drift_deg = 0, drift_max = 0 }
S.frozen = nil          -- the last frozen socket, kept across a quick release/re-take
S.last_release = -1e9
local function release_take()
    if S.take ~= nil then S.last_release = os.clock() end
    S.take = nil
end
S.weapon = nil          -- the weapon the frozen socket was measured on (its address); a change forgets the socket
S.cand = nil            -- the live socket being watched for steadiness: { socket, t0 }
local function forget_frozen(why)
    if S.frozen ~= nil or S.take ~= nil then L("frozen socket forgotten: " .. why) end
    S.frozen = nil
    S.cand = nil
    release_take()
end
local chk = { ok = 0, bad = 0, worst_m = 0, worst_deg = 0, last_t = 0, verified = false }

local function v3(a) return Vector3f.new(a.x, a.y, a.z) end
-- 2026-10-02: plain component maths for the few sums praydog's Lua vectors may not offer (a vector subtraction threw a
-- C++ exception inside pose_check on the first wear); nothing below depends on operator bindings for subtraction.
local function sub(a, b) return Vector3f.new(a.x - b.x, a.y - b.y, a.z - b.z) end
local function len(a) return math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z) end
local function unit(a)
    local l = math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z)
    if l < 1e-6 then return nil end
    return Vector3f.new(a.x / l, a.y / l, a.z / l)
end
local function quat_deg(q)   -- the turn a unit quaternion carries, in degrees
    return math.deg(2 * math.acos(math.min(1, math.abs(q.w))))
end
local function angle_between_deg(a, b)   -- two unit vectors
    local d = a.x * b.x + a.y * b.y + a.z * b.z
    return math.deg(math.acos(math.max(-1, math.min(1, d))))
end
-- the shortest turn taking unit vector a onto unit vector b; no roll about the line
local function shortest_arc(a, b)
    local d = a.x * b.x + a.y * b.y + a.z * b.z
    if d < -0.9999 then return Quaternion.new(1, 0, 0, 0) end   -- opposite: refuse rather than flip the gun
    local cx = a.y * b.z - a.z * b.y
    local cy = a.z * b.x - a.x * b.z
    local cz = a.x * b.y - a.y * b.x
    return Quaternion.new(1 + d, cx, cy, cz):normalized()
end
-- may this live socket be frozen? `known` is the captured rifle spot (or nil), `steady_s` how long it has held still
-- keep the grip? r/a = the hand's distance from the right hand and its angle off the frozen socket line now;
-- r0/a0 = the same at the take. Pure, so the test file can check it.
local function keep_grip(r, r0, a, a0, lim_m, lim_deg)
    local dr, da = math.abs(r - r0), math.abs(a - a0)
    return dr <= lim_m and da <= lim_deg, dr, da
end

local RIFLE_PREFIX = "ri3042"   -- the sniper rifle's GameObject name (as the plugin's scoped-weapon filter)
-- the name of praydog's weapon object (a GameObject, or a component on one); nil if it cannot be read
local function weapon_name(w)
    if w == nil then return nil end
    -- the same two ways re8_vr.lua finds the weapon's GameObject (get_GameObject, else the <owner> field); a GameObject
    -- answers get_Name itself (2026-10-02 13:55: the first version tried only get_GameObject and read nil every time)
    local go = safe(function() return w:call("get_GameObject") end)
    if go == nil then go = safe(function() return w:get_field("<owner>k__BackingField") end) end
    local nm = go and safe(function() return go:call("get_Name") end)
    if nm == nil then nm = safe(function() return w:call("get_Name") end) end
    return nm ~= nil and tostring(nm) or nil
end

local function socket_trusted(socket, known, steady_s)
    if known ~= nil and len(sub(socket, known)) <= SOCKET_KNOWN_M then return true, "near the captured rifle spot" end
    if steady_s >= SOCKET_STEADY_S then return true, string.format("held still %.2f s", steady_s) end
    return false, nil
end
_G.re8_begone_grip_maths = { shortest_arc = shortest_arc, quat_deg = quat_deg, angle_between_deg = angle_between_deg,
    socket_trusted = socket_trusted, keep_grip = keep_grip, weapon_name = weapon_name, RIFLE_PREFIX = RIFLE_PREFIX }

-- the controller poses the way RE8VR::update_hand_ik computes them: world position and rotation of each hand target
-- BEFORE any grip steering. Same inputs (camera world matrix + HMD transform, the controllers' tracking-space transforms,
-- re8_vr.lua's hand offsets), same order of operations.
local function controller_poses(v)
    local c = vrmod:get_controllers()
    if c == nil or #c < 2 then return nil end
    local lct, rct, hmd = vrmod:get_transform(c[1]), vrmod:get_transform(c[2]), vrmod:get_transform(0)
    local cam = sdk.get_primary_camera()
    if cam == nil or lct == nil or rct == nil or hmd == nil then return nil end
    local m = cam:call("get_WorldMatrix")
    if m == nil then return nil end
    local cam_rot, cam_pos = m:to_quat(), m[3]
    vrmod:apply_hmd_transform(cam_rot, cam_pos)
    cam_rot = (cam_rot * hmd:to_quat():inverse()):normalized()
    local cp = v3(cam_pos)
    local h3 = hmd[3]
    local function hand(ct, rot_off, pos_off)
        local crot = ct:to_quat()
        local c3 = ct[3]
        local off = Vector3f.new(c3.x - h3.x, c3.y - h3.y, c3.z - h3.z)
        local rot = (cam_rot * crot * rot_off):normalized()
        local pos = cp + cam_rot * off + (cam_rot * crot):normalized() * v3(pos_off)
        return pos, rot
    end
    local lp, lr = hand(lct, v.left_hand_rotation_offset, v.left_hand_position_offset)
    local rp, rr = hand(rct, v.right_hand_rotation_offset, v.right_hand_position_offset)
    return lp, lr, rp, rr
end

local function pose_check(rp, rr, rp_ik, rr_ik, cpp_steering)
    local dm = len(sub(rp, rp_ik))
    chk.worst_m = math.max(chk.worst_m, dm)
    local ddeg = nil
    if not cpp_steering then
        ddeg = quat_deg((rr:inverse() * rr_ik):normalized())
        chk.worst_deg = math.max(chk.worst_deg, ddeg)
    end
    local bad = dm > POSE_CHECK_WARN_M or (ddeg ~= nil and ddeg > POSE_CHECK_WARN_DEG)
    if bad then chk.bad = chk.bad + 1 else chk.ok = chk.ok + 1 end
    local now = os.clock()
    if bad and now - chk.last_t >= POSE_CHECK_EVERY_S then
        chk.last_t = now
        L(string.format("POSE CHECK FAILED: our right hand is %.1f mm%s from REFramework's own -- the recompute is WRONG and the two fixes are steering on bad numbers (grip button 0 and grip freeze 0 put praydog's behaviour back)",
            dm * 1000, ddeg ~= nil and string.format(" / %.2f deg", ddeg) or ""))
    elseif not bad and not chk.verified and chk.ok >= POSE_CHECK_PASSES then
        chk.verified = true
        L(string.format("pose check: %d passes within %.1f mm / %.2f deg of REFramework's own right hand -- the recompute is right",
            chk.ok, chk.worst_m * 1000, chk.worst_deg))
    end
end

local function set_ik(v, ik, tf, pos, rot)
    safe(function() v:set_hand_joints_to_tpose(ik) end)
    safe(function() tf:call("set_Position", pos) end)
    safe(function() tf:call("set_Rotation", rot) end)
    safe(function() ik:set_field("Transition", 1.0) end)
    safe(function() ik:call("calc") end)
end

local function grip(a, b, c)
    if a == "capture" and tonumber(b) then
        g.capture_at = os.clock() + tonumber(b)
        g.on = false   -- the game's own spot while the wearer settles, so the capture reads it, not ours
        L("capture in " .. b .. " s -- hold the grip you want")
    elseif a == "probe" then
        g.probe = not g.probe
        L("probe " .. (g.probe and "ON" or "off"))
    elseif a == "capture" then
        capture_now()
    elseif a == "on" then
        if g.pos == nil then L("on: nothing captured yet -- grip capture first") return end
        g.on = true save() L("ON")
    elseif a == "off" then
        g.on = false save() L("off: the game's own grip spot")
    elseif a == "button" then
        GRIP_NEEDS_BUTTON = b ~= "0" and b ~= "off"
        L("button: " .. (GRIP_NEEDS_BUTTON and "the left grip button is the only way to dock" or "praydog's 10 cm dock allowed too"))
    elseif a == "freeze" then
        GRIP_FREEZE_SOCKET = b ~= "0" and b ~= "off"
        L("freeze: " .. (GRIP_FREEZE_SOCKET and "steering against the socket frozen at the take" or "steering against the live animation socket (praydog's)"))
    elseif a == "check" then
        L(string.format("pose check: %d passes agree, %d disagree, worst %.1f mm / %.2f deg, %s", chk.ok, chk.bad,
            chk.worst_m * 1000, chk.worst_deg, chk.verified and "VERIFIED" or "not yet verified"))
    elseif a == "letgo" then
        local cm, deg = tonumber(b), tonumber(c)
        if cm then GRIP_LETGO_M = cm / 100 end
        if deg then GRIP_LETGO_DEG = deg end
        L(string.format("letgo: the grip lets go when the left hand moves %.0f cm or %.0f deg from where it took the grip", GRIP_LETGO_M * 100, GRIP_LETGO_DEG))
    elseif a == "forget" then
        forget_frozen("the 'grip forget' word")
        L("forget: the next dock freezes a fresh socket once it can be trusted")
    else
        L(string.format("state: %s, spot %s, probe %s, applied %d frames | button-only %s, frozen socket %s | takes %d, docks undone %d, steering %.2f deg, socket drift %.2f deg (max %.2f) | pose check %s",
            g.on and "ON" or "off", g.pos and string.format("(%.3f, %.3f, %.3f)", g.pos.x, g.pos.y, g.pos.z) or "none",
            tostring(g.probe), g.applied, tostring(GRIP_NEEDS_BUTTON), tostring(GRIP_FREEZE_SOCKET), S.takes, S.undone,
            S.steer_deg, S.drift_deg, S.drift_max, chk.verified and "ok" or (chk.bad > 0 and "FAILING" or "pending")))
        L(string.format("let go: the left hand has moved %.1f cm and %.0f deg from where it took the grip (lets go beyond %.0f cm or %.0f deg; `grip letgo <cm> <deg>`)", (S.letgo_dr or 0) * 100, S.letgo_da or 0, GRIP_LETGO_M * 100, GRIP_LETGO_DEG))
        L(string.format("frozen socket %s%s, forgotten %.0f s after a release or on a weapon change; a first freeze needs the socket still for %.1f s or within %.0f cm of the captured spot",
            S.frozen and string.format("(%.3f, %.3f, %.3f)", S.frozen.socket.x, S.frozen.socket.y, S.frozen.socket.z) or "none",
            S.take and " (gripped)" or (S.frozen and string.format(" (released %.1f s ago)", os.clock() - S.last_release) or ""),
            FROZEN_FORGET_S, SOCKET_STEADY_S, SOCKET_KNOWN_M * 100))
    end
end

local function probe_tick(lp, lr, rp, rr)
    local p = relative(lp, lr, rp, rr)
    local now = os.clock()
    if now - g.last_t < GRIP_PROBE_MIN_S then return end
    if g.last ~= nil and (p - g.last):length() < GRIP_PROBE_STEP then return end
    g.last, g.last_t = p, now
    local v = vr()
    L(string.format("probe: game grip spot (%.3f, %.3f, %.3f) docked=%s holding=%s reloading=%s", p.x, p.y, p.z,
        tostring(v.was_gripping_weapon), tostring(v.is_holding_left_grip), tostring(v.is_reloading)))
end

-- ---- THE STACKED GRIP, in our own file (2026-09-27). Tefa's rule: players install praydog's REFramework and our mod only
-- adds files. The stacked grip lived in our patched loader (grip-no-throw.patch, RE8VR::update_hand_ik, worn 2026-09-22:
-- "the occlusion drift is no more"): with the LEFT GRIP BUTTON held and the left controller 3-35 cm above the right one
-- (within 12 cm sideways to enter, 18 cm to leave), the left hand counts as holding the rifle -- drawn on the forestock --
-- while the rifle is aimed by the right hand only. On stock REFramework a hand held there is NOT docked (it is far from the
-- animation's grip socket), so the rifle already follows the right hand alone; all that is missing is the drawn hand, which
-- the grip spot below provides. Measured on the controllers' own tracked positions (tracking space, metres, y up).
local STACK_UP_MIN_M, STACK_UP_MAX_M = 0.03, 0.35
local STACK_SIDE_ENTER_M, STACK_SIDE_LEAVE_M = 0.12, 0.18
g.stacked = false
local function stacked_zone(v)
    if not v.is_holding_left_grip or v.is_reloading then return false end
    local ok, l, r = pcall(function()
        local c = vrmod:get_controllers()
        return vrmod:get_transform(c[1])[3], vrmod:get_transform(c[2])[3]
    end)
    if not ok or l == nil or r == nil then return false end
    local up = l.y - r.y
    local side = math.sqrt((l.x - r.x) ^ 2 + (l.z - r.z) ^ 2)
    local limit = g.stacked and STACK_SIDE_LEAVE_M or STACK_SIDE_ENTER_M
    local now = up >= STACK_UP_MIN_M and up <= STACK_UP_MAX_M and side <= limit
    if now ~= g.stacked then
        L(string.format("stacked grip %s (%.0f cm above, %.0f cm to the side)", now and "TAKEN" or "released", up * 100, side * 100))
        g.stacked = now
    end
    return now
end

-- One pass, after REFramework's update_hand_ik. `final` = the PrepareRendering pass, the last of the frame, where the
-- once-a-frame things (probe, timed capture) run.
-- 2026-10-02 00:30, Tefa after a script reset: "it still does it". The script had loaded and then logged nothing: it
-- only acted while the scope's rifle camera was known to it (st.clone_go), and after a reset that is gone until the
-- scope is rebuilt. The two fixes do not need the scope at all (they are about praydog's grip, for any long gun), so
-- they now run whenever VR is on; the scope's rifle camera is only needed for the CAPTURED hand spot, which was
-- captured on the rifle. `blocked_why` says, once per reason, what stopped the pass, so a silent log is never a mystery.
local blocked_logged = {}
local function blocked(why)
    if not blocked_logged[why] then blocked_logged[why] = true L("pass idle: " .. why) end
end
local active_logged = false

local function grip_pass(final)
    local v = vr()
    if v == nil then blocked("re8vr is not there (praydog's RE8 VR mode not loaded)") return end
    if not safe(function() return vrmod:is_hmd_active() end) then blocked("the headset is not active") return end
    if not safe(function() return vrmod:is_using_controllers() end) then blocked("no motion controllers") return end
    -- 2026-10-02 00:55 (fourth wear, "still does it, first shot"): the bolt action after every shot counts as
    -- is_reloading, and this pass used to step aside for it. praydog parks both hands on the live socket and drops the
    -- steering for those frames, so the rifle snapped to one-handed aim at each shot and back a second later. Now the
    -- pass keeps the grip and the right hand's steering through a reload; only the LEFT hand is left to praydog there,
    -- so the bolt animation still looks right. A grip is never first TAKEN mid-reload (the socket is mid-animation).
    local reloading = v.is_reloading
    local now = os.clock()
    -- a different weapon (or none) means the frozen socket was measured on something else: forget it
    local wid = safe(function() return v.weapon ~= nil and v.weapon:get_address() or nil end) or "none"
    if wid ~= S.weapon then
        if S.weapon ~= nil then forget_frozen("the weapon changed") end
        S.weapon = wid
        -- 2026-10-02 13:47 (Tefa's screenshots: the left hand floating open beside the pistol and the shotgun): the rifle
        -- camera (st.clone_go) is made once and never cleared, so "the rifle camera exists" stayed true for EVERY weapon
        -- and every weapon's left hand was put on the rifle's captured forestock spot, 37 cm ahead of the right hand.
        -- The captured spot and finger pose now apply only when the weapon in hand IS the sniper rifle, by its name.
        S.weapon_name = weapon_name(v.weapon)
        S.is_rifle = S.weapon_name ~= nil and S.weapon_name:find(RIFLE_PREFIX, 1, true) == 1
        if S.weapon_name == nil and v.weapon ~= nil then
            L("weapon in hand: name not readable, object type " .. tostring(safe(function() return v.weapon:get_type_definition():get_full_name() end)))
        end
        L(string.format("weapon in hand: %s (%s)", tostring(S.weapon_name),
            S.is_rifle and "the sniper rifle: its captured grip spot applies" or "not the rifle: the game's own grip spot"))
    end
    if S.take == nil and S.frozen ~= nil and now - S.last_release > FROZEN_FORGET_S then
        forget_frozen(string.format("%.1f s without a grip", now - S.last_release))
    end
    local s = st()
    local rifle_scope = S.is_rifle == true and s ~= nil and s.clone_go ~= nil   -- the rifle in hand AND its camera up
    local stacked = stacked_zone(v)
    local cpp_grip = v.was_gripping_weapon
    local holding = v.is_holding_left_grip
    -- (2026-10-02 00:55, fifth wear) this used to be "if praydog is not docked and not stacked, let go and return":
    -- a leftover from before the grip was our own decision. It dropped our grip the instant praydog's dock dropped
    -- (every bolt swing), before the keep-test below ever ran -- the jerk that survived four fixes. Now the pass only
    -- skips when there is truly nothing it could do.
    if not cpp_grip and not stacked and S.take == nil and S.frozen == nil and chk.verified then return end
    S.stage = "hands()"
    local lp_ik, lr_ik, rp_ik, rr_ik = hands()
    if lp_ik == nil then blocked("no hand IK targets yet (no weapon in hand, or not in gameplay)") return end
    S.stage = "controller_poses"
    -- pcall directly: safe() keeps only the first return value, which left lr/rp/rr nil on the first wear (2026-10-02)
    local ok_cp, lp, lr, rp, rr = pcall(controller_poses, v)
    if not ok_cp or lp == nil then blocked("could not recompute the controller poses (camera or controller transforms missing)") return end
    if not active_logged then
        active_logged = true
        L(string.format("pass active: VR on, controllers on, hand targets found%s", rifle_scope and ", scope rifle camera up" or " (scope rifle camera not up: the captured hand spot waits for it)"))
    end
    S.stage = "pose_check"
    pose_check(rp, rr, rp_ik, rr_ik, cpp_grip)
    S.stage = "after pose_check"
    -- (2026-10-02 00:58) a second early exit of the same kind used to sit here; the keep-test below decides now
    if final and g.probe then probe_tick(lp_ik, lr_ik, rp_ik, rr_ik) end
    if final and g.capture_at ~= nil and os.clock() >= g.capture_at then g.capture_at = nil capture_now() return end

    -- 2026-10-02 00:50, the auto-dock jerk explained by the log: with no button held, praydog keeps the grip only
    -- while the hand is within 10 cm of the ANIMATION's socket. The bolt animation swings that socket ~50 deg after a
    -- shot, the grip drops, the rifle snaps to one-handed aim, and a second later it re-docks. Your real hand never
    -- moved. So the grip is now OUR decision, measured against the FROZEN socket: take it when praydog docks (or the
    -- hand comes within GRIP_DOCK_M of the frozen socket), keep it while the hand stays within GRIP_RELEASE_M of it,
    -- whatever the animation does. praydog's dock is only used as the first measurement of where the socket is.
    local socket_live, lrot_live = nil, nil
    if cpp_grip then
        local inv = rr_ik:inverse()
        socket_live = inv * sub(lp_ik, rp_ik)
        lrot_live = (inv * lr_ik):normalized()
        -- how long has the live socket held still? (the wait restarts when it strays from where it began)
        if S.cand == nil or len(sub(socket_live, S.cand.socket)) > SOCKET_STEADY_M then S.cand = { socket = socket_live, t0 = now } end
    else
        S.cand = nil
    end
    -- 2026-10-02 00:50 (third wear): the grip still let go at every shot. The keep-test measured the hand against the
    -- frozen socket in the UN-steered right-hand frame, but the rifle is steered 30-36 deg so that the forestock meets
    -- the hand -- so the un-steered socket point sat ~25 cm from the hand and the grip released on every bolt swing.
    -- The steering, by construction, points the socket AT the hand, so the only thing left to measure is the RADIUS:
    -- how far the hand is from the right hand, against how long the socket is. That is the keep-test now (plus a wide
    -- angle sanity limit). The TAKE still uses the plain 10 cm distance to the un-steered socket, as praydog does.
    local d_take, d_keep, ang_keep = nil, nil, nil
    local r_now, a_now, keep_ok, dr, da = nil, nil, true, 0, 0
    if S.frozen ~= nil then
        d_take = len(sub(lp, rp + rr * S.frozen.socket))
        d_keep = math.abs(len(sub(lp, rp)) - len(S.frozen.socket))
        local sd, hd = unit(rr * S.frozen.socket), unit(sub(lp, rp))
        ang_keep = (sd ~= nil and hd ~= nil) and angle_between_deg(sd, hd) or 180
    end
    if S.take ~= nil then
        local sd, hd = unit(rr * S.take.socket), unit(sub(lp, rp))
        r_now = len(sub(lp, rp))
        a_now = (sd ~= nil and hd ~= nil) and angle_between_deg(sd, hd) or 180
        if S.take.r0 == nil then S.take.r0, S.take.a0 = r_now, a_now end   -- where the hand was at the take
        keep_ok, dr, da = keep_grip(r_now, S.take.r0, a_now, S.take.a0, GRIP_LETGO_M, GRIP_LETGO_DEG)
    end
    S.letgo_dr, S.letgo_da = dr, da
    local allowed = (not GRIP_NEEDS_BUTTON) or holding
    local our_grip
    if S.take ~= nil then
        our_grip = allowed and (holding or keep_ok)
    else
        local near = cpp_grip or (d_take ~= nil and d_take <= GRIP_DOCK_M)
        -- after the hand pulled away, it must leave the dock zone once before the auto-dock may take it again
        -- (otherwise praydog's dock re-grabs a hand that is still close, and the let-go never seems to happen)
        if S.need_clear and not near then S.need_clear = false end
        our_grip = allowed and (holding or (near and not S.need_clear))
    end
    -- 2026-10-10 (Tefa: tilting the rifle or moving the right controller "breaks that reload animation and it doesn't
    -- finish, the hand teleports back on the gun"): one line whenever the reload / button / dock / our grip changes, so the
    -- next run shows what cut the reload short.
    do
        local key = string.format("reloading=%s button=%s praydog_docked=%s our_grip=%s take=%s", tostring(reloading),
            tostring(holding), tostring(cpp_grip), tostring(our_grip), tostring(S.take ~= nil))
        if key ~= S.state_key then
            S.state_key = key
            L(string.format("state: %s | hand %.1f cm / %.0f deg from the take", key, (d_keep or -0.01) * 100, ang_keep or -1))
        end
    end
    S.hand_from_frozen_m = d_keep or -1
    S.hand_angle_deg = ang_keep or -1

    if not our_grip then
        if cpp_grip then
            -- praydog docked but we say no (button not held, or the hand is away from our reference): undo it
            set_ik(v, v.right_hand_ik, v.right_hand_ik_transform, rp, rr)
            set_ik(v, v.left_hand_ik, v.left_hand_ik_transform, lp, lr)
            safe(function() v.was_gripping_weapon = false end)
            release_take()
            S.undone = S.undone + 1
            if not S.undone_logged then
                S.undone_logged = true
                L(GRIP_NEEDS_BUTTON and "the game docked the left hand without the left grip button -- undone; hold the button to take the grip"
                    or "the game docked the left hand away from the frozen socket -- undone")
            end
            return
        end
        if S.take ~= nil then
            S.need_clear = not holding
            L(string.format("grip let go: the left hand moved %.1f cm (limit %.0f) and %.0f deg (limit %.0f) from where it took the grip, praydog docked=%s, button=%s",
                dr * 100, GRIP_LETGO_M * 100, da, GRIP_LETGO_DEG, tostring(cpp_grip), tostring(holding)))
        end
        release_take()
        -- stacked only: the rifle already follows the right hand alone; draw the left hand at the captured spot
        -- (rifle only: the spot was captured on it)
        if not stacked or not rifle_scope or not g.on or g.pos == nil then return end
        set_ik(v, v.left_hand_ik, v.left_hand_ik_transform, rp_ik + rr_ik * g.pos, (rr_ik * g.rot):normalized())
        fingers_apply()
        g.applied = g.applied + 1
        return
    end
    S.undone_logged = false

    -- gripped: by praydog's dock, by our own dock on the frozen socket, or kept through an animation
    if S.take == nil and reloading then return end
    if S.take == nil then
        local since = os.clock() - S.last_release
        if S.frozen ~= nil and (since < REDOCK_KEEP_S or socket_live == nil) then
            S.takes = S.takes + 1
            S.drift_max = 0
            S.take = { socket = S.frozen.socket, lrot = S.frozen.lrot, drift_max = 0 }
            L(string.format("grip taken #%d (%s, %.1f s after letting go): keeping the socket frozen earlier at (%.3f, %.3f, %.3f)",
                S.takes, cpp_grip and "praydog docked" or "our own dock on the frozen socket", since,
                S.frozen.socket.x, S.frozen.socket.y, S.frozen.socket.z))
        elseif socket_live ~= nil then
            local steady_s = S.cand ~= nil and (now - S.cand.t0) or 0
            local trusted, why = socket_trusted(socket_live, g.pos, steady_s)
            if not trusted then
                -- praydog's own live-socket steering stays until the socket can be trusted
                if now - (S.wait_logged_t or -1e9) >= WAIT_LOG_EVERY_S then
                    S.wait_logged_t = now
                    L(string.format("praydog docked, but the socket (%.3f, %.3f, %.3f) is not trusted yet: still for %.2f s (needs %.1f)%s -- praydog steers until it settles",
                        socket_live.x, socket_live.y, socket_live.z, steady_s, SOCKET_STEADY_S,
                        g.pos and string.format(", %.1f cm from the captured rifle spot (needs %.0f)", len(sub(socket_live, g.pos)) * 100, SOCKET_KNOWN_M * 100) or ""))
                end
                return
            end
            S.takes = S.takes + 1
            S.drift_max = 0
            S.take = { socket = socket_live, lrot = lrot_live, drift_max = 0 }
            S.frozen = { socket = socket_live, lrot = lrot_live }
            L(string.format("grip taken #%d%s: socket frozen at (%.3f, %.3f, %.3f) in the right hand's frame (%s)%s",
                S.takes, holding and " with the button" or " by itself (auto-dock)", socket_live.x, socket_live.y, socket_live.z, why,
                stacked and " (stacked: the right hand aims alone)" or ""))
        else
            return   -- nothing to freeze yet (cannot happen: our own dock needs a frozen socket)
        end
    end
    safe(function() v.was_gripping_weapon = true end)   -- so praydog's own scripts (haptics) see the grip we keep
    S.stage = "socket drift"
    local socket_ref = GRIP_FREEZE_SOCKET and S.take.socket or (socket_live or S.take.socket)
    if socket_live ~= nil then
        local a, b = unit(S.take.socket), unit(socket_live)
        if a ~= nil and b ~= nil then
            S.drift_deg = angle_between_deg(a, b)
            if S.drift_deg > S.take.drift_max + DRIFT_LOG_STEP_DEG then
                S.take.drift_max = S.drift_deg
                S.drift_max = math.max(S.drift_max, S.drift_deg)
                L(string.format("grip #%d: the ANIMATION has moved the socket %.2f deg under the held grip -- %s", S.takes, S.drift_deg,
                    GRIP_FREEZE_SOCKET and "IGNORED, the gun does not move" or "FOLLOWED (freeze off)"))
            end
        end
    end
    S.stage = "steer"
    local steer = Quaternion.new(1, 0, 0, 0)
    if not stacked and len(socket_ref) >= GRIP_STEER_MIN_M then
        local frozen_dir = unit(rr * socket_ref)
        local hand_dir = unit(sub(lp, rp))
        if frozen_dir ~= nil and hand_dir ~= nil then steer = shortest_arc(frozen_dir, hand_dir) end
    end
    S.stage = "apply right hand"
    S.steer_deg = quat_deg(steer)
    local rr_new = (steer * rr):normalized()
    -- shot trace (2026-10-02 01:00): for SHOT_TRACE_PASSES passes after each shot, one line per pass with the angles
    -- that could be the jump: praydog's right-hand rotation (as he left it this pass) against ours, our applied rotation
    -- against our previous pass, the controller against its previous pass, and the steering.
    if S.trace_left ~= nil and S.trace_left > 0 then
        S.trace_left = S.trace_left - 1
        local d_pd = quat_deg((rr_new:inverse() * rr_ik):normalized())
        local d_ours = S.last_rr_new ~= nil and quat_deg((S.last_rr_new:inverse() * rr_new):normalized()) or 0
        local d_ctrl = S.last_rr ~= nil and quat_deg((S.last_rr:inverse() * rr):normalized()) or 0
        L(string.format("trace %s: praydog vs ours %.2f deg | ours moved %.2f | controller moved %.2f | steering %.2f | drift %.2f | reloading=%s docked=%s",
            final and "PrepareRendering" or "update", d_pd, d_ours, d_ctrl, S.steer_deg, S.drift_deg, tostring(reloading), tostring(cpp_grip)))
    end
    S.last_rr_new, S.last_rr = rr_new, rr
    set_ik(v, v.right_hand_ik, v.right_hand_ik_transform, rp, rr_new)
    S.stage = "apply left hand"
    if reloading then
        -- 2026-10-10 (Tefa, recording: "ethan's hand doesnt follow the reload animation, when i hold on to the gun with LG,
        -- without LG held the reload animation is fine"): praydog's reload hand is placed against the right hand as HE posed
        -- it (rp_ik/rr_ik), but we just turned the right hand (rr_new), so the left hand came off the gun. Keep the
        -- animation's left hand exactly as it is relative to the right hand, re-attached to OUR right hand.
        local inv = rr_ik:inverse()
        set_ik(v, v.left_hand_ik, v.left_hand_ik_transform, rp + rr_new * (inv * sub(lp_ik, rp_ik)), (rr_new * (inv * lr_ik)):normalized())
        g.applied = g.applied + 1
        return
    end
    local pos, rot
    local use_spot = rifle_scope and g.on and g.pos ~= nil
    if use_spot then
        pos, rot = rp + rr_new * g.pos, (rr_new * g.rot):normalized()
    else
        pos, rot = rp + rr_new * socket_ref, (rr_new * S.take.lrot):normalized()
    end
    set_ik(v, v.left_hand_ik, v.left_hand_ik_transform, pos, rot)
    if use_spot then fingers_apply() end
    g.applied = g.applied + 1
end

local err_logged = {}
local function run_pass(final)
    local ok, e = pcall(grip_pass, final)
    if not ok then
        local k = tostring(e)
        if not err_logged[k] then err_logged[k] = true L("PASS ERROR (the fixes are NOT acting) at stage [" .. tostring(S.stage) .. "]: " .. k) end
    end
end
re.on_application_entry("UpdateMotion", function() run_pass(false) end)
re.on_application_entry("LateUpdateBehavior", function() run_pass(false) end)
re.on_pre_application_entry("PrepareRendering", function() run_pass(true) end)

-- ---- THE SHOT ITSELF (2026-10-02 00:40, Tefa after the first wear of the fixes: "the grip works, but the gun janks just
-- a little bit to the other side now"). re8_vr.lua hooks app.WeaponGunCore.shoot and, inside that hook, runs praydog's
-- update_hand_ik once more BEFORE the bullet is made -- with the live animation socket, i.e. the old steering -- and our
-- three passes only run later in the frame. So for the shot itself the gun stood where praydog put it. This hook sits on
-- the same function, registered after his (this file loads after re8_vr.lua), and puts our steering back before the bullet.
S.shots = 0
local function hook_shoot()
    local td = sdk.find_type_definition("app.WeaponGunCore")
    local m = td ~= nil and td:get_method("shoot") or nil
    if m == nil then L("shoot hook: app.WeaponGunCore.shoot not found -- the shot keeps praydog's steering") return end
    sdk.hook(m, function(args)
        S.shots = S.shots + 1
        local _, _, _, rr_entry = hands()
        S.trace_left = SHOT_TRACE_PASSES
        run_pass(false)
        if rr_entry ~= nil and S.last_rr_new ~= nil then
            L(string.format("shot #%d entry: the right hand stood %.2f deg from our last applied pose when our hook ran (0 = praydog's hook has NOT run before ours; ~5 = it has)",
                S.shots, quat_deg((S.last_rr_new:inverse() * rr_entry):normalized())))
        end
        if S.take ~= nil then
            L(string.format("shot #%d under grip #%d: socket drift %.2f deg ignored, our steering %.2f deg re-applied before the bullet",
                S.shots, S.takes, S.drift_deg, S.steer_deg))
        end
    end, function(r) return r end)
    L("shoot hook: our steering is re-applied inside app.WeaponGunCore.shoot, after praydog's hand update")
end
pcall(hook_shoot)

load()
_G.re8_scope_left_grip = grip
L("loaded -- words: grip probe | grip capture | grip on | grip off | grip button | grip freeze | grip check | grip forget | grip")
