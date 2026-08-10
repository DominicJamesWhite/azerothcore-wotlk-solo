-- Alonecraft Tooltip Fix
--
-- The 3.3.5a client ships with the CVar "UberTooltips" off for a fresh
-- WTF/Config.wtf (Interface Options -> Help -> "Enhanced Tooltips"). While it
-- is "0" the client's GameTooltip:SetAction implementation prints the spell or
-- item *name* and nothing else, and ActionButton_SetTooltip
-- (Interface/base/ActionButton.lua:419) anchors to the button corner rather
-- than the default tooltip anchor. The result is that hovering an action bar
-- slot tells you nothing about cast time, cost, range or effect.
--
-- Alonecraft redesigns talents and adds custom spells whose descriptions carry
-- the entire design, so name-only tooltips are close to unusable here. We flip
-- the CVar on for the player.
--
-- We apply it ONCE per account and remember that we did. Setting it on every
-- load would make Enhanced Tooltips a setting the player cannot turn off,
-- which is a worse bug than the one we are fixing.
--
-- TIMING, and the reason v1 of this addon did nothing:
-- UberTooltips is an *account-scoped* CVar. It is not stored in WTF/Config.wtf
-- but in WTF/Account/<ACCOUNT>/config-cache.wtf, and that file is applied only
-- once the account is known. At ADDON_LOADED the CVar still reads its engine
-- default of "1", so a "skip if already 1" guard sees 1, skips, and then the
-- account cache stamps "0" over the top a moment later. Do the work at
-- PLAYER_LOGIN, which fires after the account CVars are in place.

local AlonecraftTooltipFix = {}
_G.AlonecraftTooltipFix = AlonecraftTooltipFix

-- Bump when the apply logic changes, so an account carrying a stale
-- "applied" flag from a broken version gets one more attempt.
local APPLY_VERSION = 2

local frame = CreateFrame("Frame")
frame:RegisterEvent("PLAYER_LOGIN")
frame:SetScript("OnEvent", function(self)
    self:UnregisterEvent("PLAYER_LOGIN")

    if type(AlonecraftTooltipFixDB) ~= "table" then
        AlonecraftTooltipFixDB = {}
    end

    if AlonecraftTooltipFixDB.appliedVersion == APPLY_VERSION then
        return
    end

    AlonecraftTooltipFixDB.appliedVersion = APPLY_VERSION
    AlonecraftTooltipFixDB.applied = nil -- superseded by appliedVersion

    if GetCVar("UberTooltips") == "1" then
        return
    end

    SetCVar("UberTooltips", "1")
    DEFAULT_CHAT_FRAME:AddMessage(
        "|cff44ddffAlonecraft|r: Enhanced Tooltips enabled so ability tooltips"
            .. " show their full text. Toggle it in Interface -> Help.",
        1, 1, 1)
end)

-- /run AlonecraftTooltipFix.Reset() to forget we ever applied it, so the next
-- login turns Enhanced Tooltips back on.
function AlonecraftTooltipFix.Reset()
    if type(AlonecraftTooltipFixDB) == "table" then
        AlonecraftTooltipFixDB.appliedVersion = nil
        AlonecraftTooltipFixDB.applied = nil
    end
end
