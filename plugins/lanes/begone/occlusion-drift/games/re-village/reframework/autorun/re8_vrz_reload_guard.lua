-- re8_vrz_reload_guard.lua -- a reload is not cancelled by the hands-up block gesture (2026-10-10, Tefa in the headset).
--
-- WHY: Tefa, with the left hand gripping the rifle (LG held): "tilting it up and down and moving the right controller ...
-- breaks that reload animation and it doesn't finish, the hand teleports back on the gun" -- "it's when i raised my right
-- controller it stops reloading". Without LG the reload is fine.
-- The grip log showed our grip never let go during those reloads; praydog's is_reloading simply ended after 0.3-1.5 s,
-- so the GAME cancelled them. praydog's RE8 VR (RE8VR.cpp, update_block_gesture) sets wants_block when BOTH controllers
-- are in front of the face (dot >= 0.8 with the gaze) and turned (controller X axis >= 0.5 along the gaze); re8_vr.lua then
-- presses the guard button for the game, and app.PlayerBase.tryGuardStart starts a guard -- which cancels the reload.
-- With LG held the left hand sits beside the right on the rifle, so raising the rifle to the face is exactly that gesture;
-- with the left hand hanging down it never is. `[inferred-static 2026-10-10]` until the first wear.
--
-- WHAT (first try, kept): while the game says the player is reloading, tryGuardStart is skipped (the same hook praydog uses to allow the
-- guard only by gesture; REFramework chains both). The guard button press still goes through (praydog's pad code is not
-- touched), so if the press alone also cancels the reload, this script's log line will show the guard skipped and the
-- reload still ending early -- then the next lever is the pad press itself.
-- Log: [re8-reload-guard] one line per skipped guard, with how long the reload has been running.
-- Settings file: reframework/data/re_scope_reload_guard.txt, `on=1` (default) / `on=0` = do nothing. Read every second.

local TAG = "[re8-reload-guard] "
local function L(s) log.info(TAG .. tostring(s)) end
local CFG_FILE = "re_scope_reload_guard.txt"
local CFG_EVERY_S = 1.0

-- two_hands=1 (2026-10-10, Tefa: "block the guard if there are two hands on the weapon for all guns, so if LG held and
-- hand docked"): with the left grip button held AND the left hand docked on the weapon (praydog's was_gripping_weapon),
-- the block gesture is ignored on every gun, reloading or not. two_hands=0 = only during reloads.
local cfg = { on = 1, two_hands = 1 }
local cfg_at = -10
local function read_cfg()
    if os.clock() - cfg_at < CFG_EVERY_S then return end
    cfg_at = os.clock()
    local f = io.open("reframework/data/" .. CFG_FILE, "r")
    if f == nil then return end
    for line in f:lines() do
        local k, v = line:match("^%s*([%w_]+)%s*=%s*([-%d.]+)")
        if k ~= nil and cfg[k] ~= nil and tonumber(v) ~= nil then cfg[k] = tonumber(v) end
    end
    f:close()
end

local reload_t0 = nil      -- os.clock() when the current reload was first seen
local skipped = 0

local function reloading_now()
    local v = rawget(_G, "re8vr")
    if v == nil then return false end
    local ok, r = pcall(function() return v.is_reloading end)
    return ok and r == true
end

re.on_frame(function()
    read_cfg()
    if reloading_now() then
        if reload_t0 == nil then reload_t0 = os.clock() end
    else
        reload_t0 = nil
    end
end)

-- 2026-10-10 00:35, the probe (re8_vrz_reload_probe.lua): a full reload is 2.65 s; every reload that broke ended with
-- praydog's wants_block TRUE, every good one with it false -- and tryGuardStart was never called. So the cancel comes from
-- the guard BUTTON praydog presses for the game (re8_vr.lua: wants_block -> LTrigTop in the pad update), which the reload
-- honours on its own. The gesture is computed in praydog's UpdateBehavior callback and read by the pad hook in the NEXT
-- frame's UpdateHID, so clearing wants_block after UpdateBehavior, while reloading, stops the press before it is made.
local function two_hands_now(v)
    if cfg.two_hands == 0 then return false end
    local ok, r = pcall(function() return v.is_holding_left_grip == true and v.was_gripping_weapon == true end)
    return ok and r == true
end

local withheld_why = nil   -- nil = the block is free; otherwise why it is being withheld (logged on change)
local function withhold_block()
    if cfg.on == 0 then return end
    local v = rawget(_G, "re8vr")
    if v == nil then return end
    local why = nil
    if reloading_now() then why = "reloading"
    elseif two_hands_now(v) then why = "two hands on the weapon (LG held, left hand docked)" end
    local wb = false
    pcall(function() wb = v.wants_block == true end)
    if why ~= nil and wb then
        pcall(function() v.wants_block = false end)
        if withheld_why ~= why then
            withheld_why = why
            L(string.format("block gesture ignored: %s%s", why,
                why == "reloading" and string.format(" (%.2f s into it)", reload_t0 and (os.clock() - reload_t0) or 0) or ""))
        end
    elseif why == nil and withheld_why ~= nil then
        withheld_why = nil
        L("block gesture free again")
    end
end

-- 2026-10-10 01:05 (third wear: still broke, the reload ended 4-16 ms AFTER the clear above was logged): the clear ran too
-- late. praydog presses the button in his PRE-hook on HIDPadManager.doUpdate (re8_vr.lua:551), and REFramework runs the
-- hooks on one method NEWEST FIRST (HookManager.cpp:132 "iterate in reverse"). So the clear now lives in our own pre-hook
-- on that same method, registered on the first frame (after every autorun script has registered its hooks), so it runs
-- right before praydog reads wants_block. The UpdateBehavior clear stays as a second layer.
-- 2026-10-10 01:40 (fourth wear, probe round three): still breaks, and the probe shows the game entering its GUARD
-- (isGuard/isGunGuard flip on) in the same frame the reload is cancelled -- with no guard-named method called first, so
-- the guard comes from the pad's guard button. All autorun scripts share one Lua state, whose hooks on a method run in
-- registration order (praydog's first), so our pre-hook clear above lands AFTER he has already pressed the button.
-- Two fixes that do not depend on hook order: (1) the flag is cleared in on_pre_application_entry("UpdateHID"), which
-- runs before the engine's pad update and so before praydog's hook; (2) in our POST-hook on the pad update the guard
-- bit (LTrigTop) is removed again from the pad device praydog wrote to, so even a press that got through is undone
-- before the game reads it.
local pad_hooked = false
local pad_padman = nil
local bit_removed_logged = false
local function pad_strip_guard()
    if withheld_why == nil then return end
    pcall(function()
        local pad = pad_padman:call("get_activePad")
        if pad == nil then pad = pad_padman:call("get_mergedPad") end
        local device = pad:get_field("Device")
        local guard = via.hid.GamePadButton.LTrigTop
        local b = device:call("get_Button")
        local bd = device:call("get_ButtonDown")
        local had = (b & guard) ~= 0 or (bd & guard) ~= 0
        if (b & guard) ~= 0 then device:call("set_Button", b & ~guard) end
        if (bd & guard) ~= 0 then device:call("set_ButtonDown", bd & ~guard) end
        if had and not bit_removed_logged then
            bit_removed_logged = true
            L("the guard button was pressed on the pad anyway -- bit removed (" .. tostring(withheld_why) .. ")")
        end
        if not had then bit_removed_logged = false end
    end)
end
local function hook_pad()
    if pad_hooked then return end
    pad_hooked = true
    local ok, err = pcall(function()
        local td = sdk.find_type_definition(sdk.game_namespace("HIDPadManager"))
        local m = td and td:get_method("doUpdate")
        if m == nil then error("HIDPadManager.doUpdate not found") end
        sdk.hook(m, function(args) pad_padman = sdk.to_managed_object(args[2]) withhold_block() end,
                    function(r) pad_strip_guard() return r end)
    end)
    L(ok and "hooked HIDPadManager.doUpdate: the block flag is cleared before, and the guard bit removed after, praydog's pad hook"
         or ("could not hook the pad update: " .. tostring(err)))
end

re.on_pre_application_entry("UpdateHID", withhold_block)

-- 2026-10-10 01:55 (fifth wear): the pad bit was removed in our post-hook and the probe STILL read it set at the cancel,
-- so the pad route is a losing race. The game has its own gate: app.PlayerStatus.get_isGuardCommandAcceptable, asked
-- before a guard command is honoured. While withholding, it answers NO -- whatever button or gesture arrived.
local acceptable_hooked = false
local refused_logged = false
local function hook_acceptable()
    if acceptable_hooked then return end
    acceptable_hooked = true
    local ok, err = pcall(function()
        local td = sdk.find_type_definition("app.PlayerStatus")
        local m = td and td:get_method("get_isGuardCommandAcceptable")
        if m == nil then error("app.PlayerStatus.get_isGuardCommandAcceptable not found") end
        sdk.hook(m, function(args) end, function(retval)
            if withheld_why == nil then refused_logged = false return retval end
            if not refused_logged then
                refused_logged = true
                L("guard command refused by the game's own gate (" .. tostring(withheld_why) .. ")")
            end
            return sdk.to_ptr(0)
        end)
    end)
    L(ok and "hooked app.PlayerStatus.get_isGuardCommandAcceptable: answers no while withholding"
         or ("could not hook the guard gate: " .. tostring(err)))
end
re.on_frame(function() hook_acceptable() end)
re.on_frame(function() hook_pad() end)
re.on_application_entry("UpdateBehavior", withhold_block)

local function on_pre_try_guard_start(args)
    if cfg.on == 0 then return end
    if not reloading_now() then return end
    skipped = skipped + 1
    L(string.format("guard #%d skipped: the player is reloading (%.2f s into it) -- the hands-up block gesture would have cancelled the reload",
        skipped, reload_t0 and (os.clock() - reload_t0) or 0))
    return sdk.PreHookResult.SKIP_ORIGINAL
end

local function on_post_try_guard_start(retval)
    return retval
end

local td = sdk.find_type_definition("app.PlayerBase")
local m = td and td:get_method("tryGuardStart")
if m == nil then
    L("app.PlayerBase.tryGuardStart not found -- doing nothing")
else
    sdk.hook(m, on_pre_try_guard_start, on_post_try_guard_start)
    L("hooked app.PlayerBase.tryGuardStart: a guard is skipped while reloading")
end
