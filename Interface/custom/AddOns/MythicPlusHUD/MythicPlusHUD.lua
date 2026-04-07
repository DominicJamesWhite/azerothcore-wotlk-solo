-- MythicPlusHUD: Mythic Plus dungeon overlay
-- Receives state updates from the server via addon messages and displays
-- a WoW-native HUD with timer bar, speed tiers, deaths, affixes, and boss.

local ADDON_PREFIX = "MPHUD"
local FADE_DELAY = 5

-- ----------------------------------------------------------------
-- Affix info (matches MythicAffixType enum on server)
-- ----------------------------------------------------------------
local AFFIX_INFO = {
    [0] = { name = "Fortified",   desc = "All enemies have increased health" },
    [1] = { name = "Bolstering",  desc = "Trash mobs have increased health" },
    [2] = { name = "Tyrannical",  desc = "Bosses have increased health" },
    [3] = { name = "Teeming",     desc = "Trash mobs can spawn copies" },
    [4] = { name = "Raging",      desc = "All enemies deal more damage" },
    [5] = { name = "Volcanic",    desc = "Random explosions damage players" },
    [6] = { name = "Storming",    desc = "Lightning spheres spawn periodically" },
    [7] = { name = "Enrage",      desc = "Enemies can randomly enrage" },
    [8] = { name = "Entangling",  desc = "Enemies cast roots on players" },
}

-- Tier colours
local TIER_COLORS = {
    Platinum = { 0.88, 0.93, 1.00 },
    Gold     = { 1.00, 0.82, 0.00 },
    Silver   = { 0.75, 0.75, 0.75 },
    Bronze   = { 0.80, 0.50, 0.20 },
}
local TIER_BAR_COLORS = {
    Platinum = { 0.70, 0.80, 1.00 },
    Gold     = { 0.85, 0.65, 0.00 },
    Silver   = { 0.55, 0.55, 0.55 },
    Bronze   = { 0.65, 0.35, 0.15 },
}

-- Inline texture shortcuts
local ICON_SKULL = "|TInterface\\TargetingFrame\\UI-RaidTargetingIcon_8:14|t"
local ICON_STAR  = "|TInterface\\TargetingFrame\\UI-RaidTargetingIcon_1:14|t"
local ICON_CROSS = "|TInterface\\TargetingFrame\\UI-RaidTargetingIcon_7:14|t"

local function FormatTime(sec)
    sec = math.max(0, math.floor(sec))
    return string.format("%02d:%02d", math.floor(sec / 60), sec % 60)
end

-- ================================================================
--  MAIN FRAME
-- ================================================================
local f = CreateFrame("Frame", "MythicPlusHUDFrame", UIParent)
f:SetWidth(260)
f:SetHeight(180)
f:SetMovable(true)
f:EnableMouse(true)
f:RegisterForDrag("LeftButton")
f:SetScript("OnDragStart", f.StartMoving)
f:SetScript("OnDragStop", f.StopMovingOrSizing)
f:SetClampedToScreen(true)
f:Hide()

local DEFAULT_ANCHOR = { "RIGHT", UIParent, "RIGHT", -120, 0 }
f:SetPoint(unpack(DEFAULT_ANCHOR))

f:SetBackdrop({
    bgFile   = "Interface\\Tooltips\\UI-Tooltip-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 16,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
f:SetBackdropColor(0.05, 0.05, 0.08, 0.92)

-- ----------------------------------------------------------------
--  Decorative header banner
-- ----------------------------------------------------------------
local headerBg = f:CreateTexture(nil, "ARTWORK")
headerBg:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
headerBg:SetWidth(200)
headerBg:SetHeight(44)
headerBg:SetPoint("TOP", f, "TOP", 0, 10)

local header = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
header:SetPoint("TOP", f, "TOP", 0, 2)
header:SetTextColor(1, 1, 1)
header:SetText("MYTHIC 5")

-- ================================================================
--  TIMER STATUS BAR
-- ================================================================
local barFrame = CreateFrame("Frame", nil, f)
barFrame:SetWidth(232)
barFrame:SetHeight(22)
barFrame:SetPoint("TOP", f, "TOP", 0, -30)

-- Border overlay (drawn on top of everything)
local barBorder = barFrame:CreateTexture(nil, "OVERLAY", nil, 2)
barBorder:SetPoint("TOPLEFT", barFrame, "TOPLEFT", -1, 1)
barBorder:SetPoint("BOTTOMRIGHT", barFrame, "BOTTOMRIGHT", 1, -1)
barBorder:SetTexture("Interface\\Tooltips\\UI-StatusBar-Border")

-- Bar background (inset inside the border)
local BAR_INSET = 3
local barBG = barFrame:CreateTexture(nil, "BACKGROUND")
barBG:SetPoint("TOPLEFT", barFrame, "TOPLEFT", BAR_INSET, -BAR_INSET)
barBG:SetPoint("BOTTOMRIGHT", barFrame, "BOTTOMRIGHT", -BAR_INSET, BAR_INSET)
barBG:SetTexture("Interface\\TargetingFrame\\UI-StatusBar")
barBG:SetVertexColor(0.12, 0.12, 0.15, 1)

-- StatusBar fill (inset to match, stays inside the rounded border)
local timerBar = CreateFrame("StatusBar", "MythicPlusTimerBar", barFrame)
timerBar:SetPoint("TOPLEFT", barFrame, "TOPLEFT", BAR_INSET, -BAR_INSET)
timerBar:SetPoint("BOTTOMRIGHT", barFrame, "BOTTOMRIGHT", -BAR_INSET, BAR_INSET)
timerBar:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
timerBar:SetMinMaxValues(0, 100)
timerBar:SetValue(0)

-- Spark at leading edge
local spark = timerBar:CreateTexture(nil, "OVERLAY")
spark:SetTexture("Interface\\CastingBar\\UI-CastingBar-Spark")
spark:SetWidth(16)
spark:SetHeight(32)
spark:SetBlendMode("ADD")
spark:SetPoint("CENTER", timerBar, "LEFT", 0, 0)

-- Time text on bar
local timerText = timerBar:CreateFontString(nil, "OVERLAY", "GameFontHighlight")
timerText:SetPoint("CENTER", timerBar, "CENTER", 0, 0)
timerText:SetText("00:00 / 00:00")

-- Tier threshold markers (vertical tick lines on the bar)
local function CreateTick(parent)
    local tick = parent:CreateTexture(nil, "OVERLAY", nil, 1)
    tick:SetWidth(1)
    tick:SetHeight(24)
    tick:SetTexture(1, 1, 1, 0.35)
    tick:Hide()
    return tick
end
local tickPlat   = CreateTick(barFrame)
local tickGold   = CreateTick(barFrame)
local tickSilver = CreateTick(barFrame)

-- Small tier labels above ticks
local function CreateTickLabel(parent)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetTextColor(0.7, 0.7, 0.7)
    label:Hide()
    return label
end
local tickLabelP = CreateTickLabel(barFrame)
local tickLabelG = CreateTickLabel(barFrame)
local tickLabelS = CreateTickLabel(barFrame)

-- ================================================================
--  TIER BREAKDOWN
-- ================================================================
local tierSection = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
tierSection:SetPoint("TOPLEFT", barFrame, "BOTTOMLEFT", 2, -8)
tierSection:SetJustifyH("LEFT")
tierSection:SetTextColor(0.6, 0.6, 0.6)
tierSection:SetText("Rewards")

local tierLines = {}
local tierOrder = { "Platinum", "Gold", "Silver", "Bronze" }
for i = 1, 4 do
    local line = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    if i == 1 then
        line:SetPoint("TOPLEFT", tierSection, "BOTTOMLEFT", 2, -2)
    else
        line:SetPoint("TOPLEFT", tierLines[i - 1], "BOTTOMLEFT", 0, -1)
    end
    line:SetJustifyH("LEFT")
    tierLines[i] = line
end

-- Separator line
local sep1 = f:CreateTexture(nil, "ARTWORK")
sep1:SetHeight(1)
sep1:SetPoint("TOPLEFT", tierLines[4], "BOTTOMLEFT", -4, -5)
sep1:SetPoint("RIGHT", f, "RIGHT", -14, 0)
sep1:SetTexture(1, 1, 1, 0.1)

-- ================================================================
--  DEATHS / UNDYING
-- ================================================================
local deathText = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
deathText:SetPoint("TOPLEFT", sep1, "BOTTOMLEFT", 4, -5)
deathText:SetJustifyH("LEFT")

-- Separator
local sep2 = f:CreateTexture(nil, "ARTWORK")
sep2:SetHeight(1)
sep2:SetPoint("TOPLEFT", deathText, "BOTTOMLEFT", -4, -5)
sep2:SetPoint("RIGHT", f, "RIGHT", -14, 0)
sep2:SetTexture(1, 1, 1, 0.1)

-- ================================================================
--  BOONS & CURSES (active modifiers for this run)
-- ================================================================
local modHeader = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
modHeader:SetJustifyH("LEFT")
modHeader:SetTextColor(0.6, 0.6, 0.6)
modHeader:SetText("Boons & Curses")
modHeader:Hide()

local MAX_MODIFIER_LINES = 6
local modifierLines = {}
for i = 1, MAX_MODIFIER_LINES do
    local line = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    line:SetJustifyH("LEFT")
    line:SetWidth(232)
    line:Hide()
    modifierLines[i] = line
end

local sepMod = f:CreateTexture(nil, "ARTWORK")
sepMod:SetHeight(1)
sepMod:SetPoint("RIGHT", f, "RIGHT", -14, 0)
sepMod:SetTexture(1, 1, 1, 0.1)
sepMod:Hide()

-- ================================================================
--  AFFIXES
-- ================================================================
local MAX_AFFIX_LINES = 4
local affixLines = {}
for i = 1, MAX_AFFIX_LINES do
    local line = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    -- Anchored dynamically in UpdateDisplay based on modifier count
    line:SetJustifyH("LEFT")
    line:SetWidth(232)
    line:Hide()
    affixLines[i] = line
end

-- Separator
local sep3 = f:CreateTexture(nil, "ARTWORK")
sep3:SetHeight(1)
sep3:SetPoint("TOPLEFT", affixLines[1], "BOTTOMLEFT", -4, -5) -- re-anchored dynamically
sep3:SetPoint("RIGHT", f, "RIGHT", -14, 0)
sep3:SetTexture(1, 1, 1, 0.1)

-- ================================================================
--  BOSS
-- ================================================================
local bossText = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
bossText:SetPoint("TOPLEFT", sep3, "BOTTOMLEFT", 4, -5)
bossText:SetJustifyH("LEFT")

-- ================================================================
--  LEAVE BUTTON
-- ================================================================
local leaveBtn = CreateFrame("Button", "MythicPlusHUDLeaveBtn", f, "UIPanelButtonTemplate")
leaveBtn:SetWidth(160)
leaveBtn:SetHeight(24)
leaveBtn:SetText("Return to Ethereal")
leaveBtn:SetScript("OnClick", function()
    SendChatMessage(".mythic leave", "SAY")
end)
leaveBtn:Hide()

-- ================================================================
--  STATE
-- ================================================================
local state = {}
local lastUpdate = 0

-- ================================================================
--  UPDATE DISPLAY
-- ================================================================
local function UpdateDisplay()
    if not state.level then return end

    local penalty = state.deaths * state.deathPenalty
    local effective = state.elapsed + penalty
    local timeLimit = state.timeLimit

    -- Header
    header:SetText("MYTHIC " .. state.level)

    -- Timer bar
    if timeLimit > 0 then
        local barMax = math.max(timeLimit, effective) * 1.05
        timerBar:SetMinMaxValues(0, barMax)
        timerBar:SetValue(effective)

        -- Bar color
        local bc = TIER_BAR_COLORS[state.tier] or TIER_BAR_COLORS.Bronze
        if state.done then
            timerBar:SetStatusBarColor(bc[1] * 0.5, bc[2] * 0.5, bc[3] * 0.5, 1)
        else
            timerBar:SetStatusBarColor(bc[1], bc[2], bc[3], 1)
        end

        -- Spark position
        if not state.done then
            local barWidth = barFrame:GetWidth()
            local sparkX = (effective / barMax) * barWidth
            spark:ClearAllPoints()
            spark:SetPoint("CENTER", timerBar, "LEFT", sparkX, 0)
            spark:Show()
        else
            spark:Hide()
        end

        -- Tick marks
        local function PlaceTick(tick, label, threshold, letter)
            local barWidth = barFrame:GetWidth()
            local x = (threshold / barMax) * barWidth
            tick:ClearAllPoints()
            tick:SetPoint("CENTER", barFrame, "LEFT", x, 0)
            tick:Show()
            label:ClearAllPoints()
            label:SetPoint("BOTTOM", tick, "TOP", 0, 0)
            label:SetText(letter)
            label:Show()
        end

        PlaceTick(tickPlat,   tickLabelP, state.platTime   or 0, "P")
        PlaceTick(tickGold,   tickLabelG, state.goldTime   or 0, "G")
        PlaceTick(tickSilver, tickLabelS, state.silverTime or 0, "S")
    end

    -- Timer text
    timerText:SetText(FormatTime(state.elapsed) .. "  /  " .. FormatTime(timeLimit))
    if state.done then
        timerText:SetTextColor(0.7, 0.7, 0.7)
    else
        timerText:SetTextColor(1, 1, 1)
    end

    -- Tier lines
    local thresholds = {
        { name = "Platinum", time = state.platTime   or 0, mult = 3.0 },
        { name = "Gold",     time = state.goldTime   or 0, mult = 2.0 },
        { name = "Silver",   time = state.silverTime or 0, mult = 1.5 },
        { name = "Bronze",   time = state.timeLimit  or 0, mult = 1.0 },
    }

    for i, tier in ipairs(thresholds) do
        local line = tierLines[i]
        local tc = TIER_COLORS[tier.name]
        local timeStr = FormatTime(tier.time)
        local label

        if tier.name == "Bronze" then
            label = "  " .. tier.name .. "    > " .. timeStr .. "  (x" .. string.format("%.1f", tier.mult) .. ")"
        else
            label = "  " .. tier.name .. string.rep(" ", 10 - #tier.name) .. "< " .. timeStr .. "  (x" .. string.format("%.1f", tier.mult) .. ")"
        end

        if state.done and state.tier == tier.name then
            -- Achieved tier: bright + marker
            line:SetTextColor(tc[1], tc[2], tc[3])
            line:SetText(ICON_STAR .. label .. "  " .. ICON_STAR)
        elseif tier.name ~= "Bronze" and effective >= tier.time then
            -- No longer reachable: dim red
            line:SetTextColor(0.35, 0.20, 0.20)
            line:SetText("  " .. tier.name .. string.rep(" ", 10 - #tier.name) .. "  " .. timeStr)
        else
            line:SetTextColor(tc[1], tc[2], tc[3])
            line:SetText(label)
        end
    end

    -- Deaths / Undying
    if state.deaths == 0 then
        local bonusStr = string.format("+%.1fx", state.undyingBonusVal or 0.5)
        deathText:SetTextColor(0.2, 0.9, 0.2)
        deathText:SetText(ICON_STAR .. "  Undying  (" .. bonusStr .. " bonus)")
    else
        local penTotal = state.deaths * state.deathPenalty
        deathText:SetTextColor(0.9, 0.3, 0.3)
        if state.deathPenalty > 0 then
            deathText:SetText(ICON_CROSS .. "  Deaths: " .. state.deaths .. "  (+" .. FormatTime(penTotal) .. " penalty)")
        else
            deathText:SetText(ICON_CROSS .. "  Deaths: " .. state.deaths)
        end
    end

    -- Affixes (anchored below sep2 / death line)
    local lastVisibleAffix = nil
    local affixCount = 0
    if state.affixes and state.affixes ~= "" then
        local parts = { strsplit(":", state.affixes) }
        for _, idStr in ipairs(parts) do
            local id = tonumber(idStr)
            if id then
                affixCount = affixCount + 1
                if affixCount <= MAX_AFFIX_LINES then
                    local info = AFFIX_INFO[id]
                    local name = info and info.name or ("Affix " .. id)
                    local desc = info and info.desc or ""
                    affixLines[affixCount]:ClearAllPoints()
                    if affixCount == 1 then
                        affixLines[affixCount]:SetPoint("TOPLEFT", sep2, "BOTTOMLEFT", 4, -5)
                    else
                        affixLines[affixCount]:SetPoint("TOPLEFT", affixLines[affixCount - 1], "BOTTOMLEFT", 0, -1)
                    end
                    affixLines[affixCount]:SetText("|cffb49bff" .. name .. "|r  " .. desc)
                    affixLines[affixCount]:SetTextColor(0.65, 0.65, 0.65)
                    affixLines[affixCount]:Show()
                    lastVisibleAffix = affixLines[affixCount]
                end
            end
        end
    end
    for j = affixCount + 1, MAX_AFFIX_LINES do
        affixLines[j]:Hide()
    end

    -- Separator after affixes
    local afterAffixAnchor = sep2
    if affixCount > 0 then
        sep3:ClearAllPoints()
        sep3:SetPoint("TOPLEFT", lastVisibleAffix, "BOTTOMLEFT", -4, -5)
        sep3:SetPoint("RIGHT", f, "RIGHT", -14, 0)
        sep3:Show()
        afterAffixAnchor = sep3
    else
        sep3:Hide()
    end

    -- Boons & Curses (below affixes)
    local modCount = 0
    local lastVisibleMod = nil
    if state.modifiers and state.modifiers ~= "" then
        local parts = { strsplit(":", state.modifiers) }
        for _, idStr in ipairs(parts) do
            local id = tonumber(idStr)
            if id then
                modCount = modCount + 1
                if modCount <= MAX_MODIFIER_LINES then
                    local info = MPHUD_MODIFIER_DATA and MPHUD_MODIFIER_DATA[id]
                    local name = info and info.name or ("Modifier " .. id)
                    local isBoon = info and info.type == 0
                    local color = isBoon and "|cff4de94d" or "|cffff4444"
                    local rewardStr = ""
                    if info then
                        if info.rewardMult > 0 then
                            rewardStr = "  |cff4de94d(+" .. string.format("%.1f", info.rewardMult) .. "x)|r"
                        else
                            rewardStr = "  |cffff4444(" .. string.format("%.1f", info.rewardMult) .. "x)|r"
                        end
                    end
                    modifierLines[modCount]:SetText(color .. name .. "|r" .. rewardStr)
                    modifierLines[modCount]:SetTextColor(0.65, 0.65, 0.65)
                    modifierLines[modCount]:ClearAllPoints()
                    if modCount == 1 then
                        modifierLines[modCount]:SetPoint("TOPLEFT", modHeader, "BOTTOMLEFT", 2, -2)
                    else
                        modifierLines[modCount]:SetPoint("TOPLEFT", modifierLines[modCount - 1], "BOTTOMLEFT", 0, -1)
                    end
                    modifierLines[modCount]:Show()
                    lastVisibleMod = modifierLines[modCount]
                end
            end
        end
    end

    -- Show/hide modifier header + separator
    if modCount > 0 then
        modHeader:ClearAllPoints()
        modHeader:SetPoint("TOPLEFT", afterAffixAnchor, "BOTTOMLEFT", 2, -5)
        modHeader:Show()
        sepMod:ClearAllPoints()
        sepMod:SetPoint("TOPLEFT", lastVisibleMod, "BOTTOMLEFT", -4, -5)
        sepMod:SetPoint("RIGHT", f, "RIGHT", -14, 0)
        sepMod:Show()
    else
        modHeader:Hide()
        sepMod:Hide()
    end
    for j = modCount + 1, MAX_MODIFIER_LINES do
        modifierLines[j]:Hide()
    end

    -- Boss — anchor below modifiers (if present) or affixes (if present) or deaths
    local bossAnchor
    if modCount > 0 then
        bossAnchor = sepMod
    elseif affixCount > 0 then
        bossAnchor = sep3
    else
        bossAnchor = sep2
    end

    bossText:ClearAllPoints()
    bossText:SetPoint("TOPLEFT", bossAnchor, "BOTTOMLEFT", 4, -5)

    if state.bossName and state.bossName ~= "" then
        if state.bossDead then
            bossText:SetText(ICON_SKULL .. "  |cff666666" .. state.bossName .. "  -  Defeated|r")
        else
            bossText:SetTextColor(1, 0.82, 0)
            bossText:SetText(ICON_SKULL .. "  " .. state.bossName)
        end
        bossText:Show()
    else
        bossText:Hide()
    end

    -- Leave button
    if state.done then
        leaveBtn:ClearAllPoints()
        local btnAnchor = bossText:IsShown() and bossText or bossAnchor
        leaveBtn:SetPoint("TOP", btnAnchor, "BOTTOM", 0, -4)
        leaveBtn:Show()
    else
        leaveBtn:Hide()
    end

    -- Dynamic height — measure from anchored elements
    local contentBottom = 30  -- barFrame offset from top
        + 22                  -- barFrame height
        + 8                   -- gap to rewards label
        + 12                  -- rewards label
        + 2 + (4 * 13)       -- tier lines
        + 5 + 1 + 5 + 13     -- sep1 + death line

    if affixCount > 0 then
        contentBottom = contentBottom + 5 + (affixCount * 13) + math.max(0, (affixCount - 1))
        contentBottom = contentBottom + 5 + 1 -- sep3
    end
    if modCount > 0 then
        contentBottom = contentBottom + 5 + 12 -- gap + header
        contentBottom = contentBottom + 2 + (modCount * 13) + math.max(0, (modCount - 1))
        contentBottom = contentBottom + 5 + 1 -- sepMod
    end
    if bossText:IsShown() then
        contentBottom = contentBottom + 5 + 13
    end
    if leaveBtn:IsShown() then
        contentBottom = contentBottom + 4 + 24
    end
    f:SetHeight(contentBottom + 6)
end

-- ================================================================
--  MESSAGE HANDLER
-- ================================================================
-- Shared global for modifier metadata (also populated by MythicPlusDungeonSelect)
MPHUD_MODIFIER_DATA = MPHUD_MODIFIER_DATA or {}

local function OnAddonMessage(prefix, msg, channel, sender)
    if prefix ~= ADDON_PREFIX then return end

    local msgType, rest = strsplit("|", msg, 2)

    -- Handle modifier metadata messages so the HUD can resolve IDs to names
    -- even without the DungeonSelect addon or after a /reload
    if msgType == "M" and rest then
        local id, mtype, name, desc, rewardMult = strsplit("|", rest)
        id = tonumber(id)
        if id then
            MPHUD_MODIFIER_DATA[id] = {
                id = id,
                type = tonumber(mtype) or 0,
                name = name or "Unknown",
                description = desc or "",
                rewardMult = tonumber(rewardMult) or 0,
            }
        end
        return
    end

    if msgType ~= "S" or not rest then return end

    local level, timeLimit, elapsed, deaths, deathPenalty, onTime, done,
          tier, mult, undying, affixes, platTime, goldTime, silverTime,
          bossName, bossDead, undyingBonusVal, activeModifiers = strsplit("|", rest)

    state.level = tonumber(level) or 0
    state.timeLimit = tonumber(timeLimit) or 0
    state.elapsed = tonumber(elapsed) or 0
    state.deaths = tonumber(deaths) or 0
    state.deathPenalty = tonumber(deathPenalty) or 0
    state.onTime = (onTime == "1")
    state.done = (done == "1")
    state.tier = tier or ""
    state.multiplier = tonumber(mult) or 1.0
    state.undying = (undying == "1")
    state.affixes = affixes or ""
    state.platTime = tonumber(platTime) or 0
    state.goldTime = tonumber(goldTime) or 0
    state.silverTime = tonumber(silverTime) or 0
    state.bossName = bossName or ""
    state.bossDead = (bossDead == "1")
    state.undyingBonusVal = tonumber(undyingBonusVal) or 0.5
    state.modifiers = activeModifiers or ""

    lastUpdate = GetTime()

    if not f:IsShown() then
        f:SetAlpha(1)
        f:Show()
    end

    UpdateDisplay()
end

-- ================================================================
--  FADE OUT
-- ================================================================
f:SetScript("OnUpdate", function(self, dt)
    if lastUpdate > 0 and (GetTime() - lastUpdate) > FADE_DELAY then
        local alpha = self:GetAlpha() - dt * 0.5
        if alpha <= 0 then
            self:Hide()
            self:SetAlpha(1)
            lastUpdate = 0
            state = {}
        else
            self:SetAlpha(alpha)
        end
    end
end)

-- ================================================================
--  EVENT REGISTRATION
-- ================================================================
local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("CHAT_MSG_ADDON")
eventFrame:SetScript("OnEvent", function(self, event, ...)
    if event == "CHAT_MSG_ADDON" then
        OnAddonMessage(...)
    end
end)

RegisterAddonMessagePrefix(ADDON_PREFIX)

-- ================================================================
--  SLASH COMMANDS
-- ================================================================
SLASH_MPHUD1 = "/mphud"
SlashCmdList["MPHUD"] = function(msg)
    msg = strlower(strtrim(msg))
    if msg == "reset" then
        f:ClearAllPoints()
        f:SetPoint(unpack(DEFAULT_ANCHOR))
        print("|cffa11585[MythicPlusHUD]|r Position reset.")
    elseif msg == "test" then
        -- Seed modifier lookup data for test
        MPHUD_MODIFIER_DATA = MPHUD_MODIFIER_DATA or {}
        MPHUD_MODIFIER_DATA[3] = {id=3,type=1,name="Frailty",description="-25% max HP",rewardMult=0.50}
        MPHUD_MODIFIER_DATA[5] = {id=5,type=1,name="Entropy",description="-30% healing",rewardMult=0.30}
        state = {
            level = 5, timeLimit = 2700, elapsed = 623,
            deaths = 0, deathPenalty = 15,
            onTime = true, done = false,
            tier = "Platinum", multiplier = 1.0, undying = true,
            affixes = "0:4:7",
            platTime = 1350, goldTime = 2025, silverTime = 2700,
            bossName = "King Ymiron", bossDead = false,
            undyingBonusVal = 0.5,
            modifiers = "3:5",
        }
        lastUpdate = GetTime()
        f:SetAlpha(1)
        f:Show()
        UpdateDisplay()
        print("|cffa11585[MythicPlusHUD]|r Test: mid-run display.")
    elseif msg == "testdone" then
        state = {
            level = 5, timeLimit = 2700, elapsed = 1847,
            deaths = 2, deathPenalty = 15,
            onTime = false, done = true,
            tier = "Gold", multiplier = 2.0, undying = false,
            affixes = "2:5",
            platTime = 1350, goldTime = 2025, silverTime = 2700,
            bossName = "King Ymiron", bossDead = true,
            undyingBonusVal = 0.5,
            modifiers = "",
        }
        lastUpdate = GetTime()
        f:SetAlpha(1)
        f:Show()
        UpdateDisplay()
        print("|cffa11585[MythicPlusHUD]|r Test: completed display.")
    elseif msg == "testlate" then
        MPHUD_MODIFIER_DATA = MPHUD_MODIFIER_DATA or {}
        MPHUD_MODIFIER_DATA[1] = {id=1,type=0,name="Ethereal Fortitude",description="+30% max HP",rewardMult=-0.20}
        MPHUD_MODIFIER_DATA[6] = {id=6,type=1,name="Hubris",description="+40% boss damage",rewardMult=0.60}
        state = {
            level = 3, timeLimit = 2700, elapsed = 2400,
            deaths = 3, deathPenalty = 15,
            onTime = false, done = false,
            tier = "Bronze", multiplier = 1.0, undying = false,
            affixes = "1:3:7:8",
            platTime = 1350, goldTime = 2025, silverTime = 2700,
            bossName = "Ingvar the Plunderer", bossDead = false,
            undyingBonusVal = 0.5,
            modifiers = "1:6",
        }
        lastUpdate = GetTime()
        f:SetAlpha(1)
        f:Show()
        UpdateDisplay()
        print("|cffa11585[MythicPlusHUD]|r Test: overtime display.")
    elseif msg == "debug" then
        print("|cffa11585[MythicPlusHUD]|r state.modifiers = [" .. tostring(state.modifiers) .. "]")
        local count = 0
        if MPHUD_MODIFIER_DATA then
            for k in pairs(MPHUD_MODIFIER_DATA) do count = count + 1 end
        end
        print("|cffa11585[MythicPlusHUD]|r MPHUD_MODIFIER_DATA entries: " .. count)
        if state.modifiers and state.modifiers ~= "" then
            local parts = { strsplit(":", state.modifiers) }
            for _, idStr in ipairs(parts) do
                local id = tonumber(idStr)
                local info = MPHUD_MODIFIER_DATA and MPHUD_MODIFIER_DATA[id]
                print("  id=" .. tostring(id) .. " info=" .. (info and info.name or "nil"))
            end
        end
    elseif msg == "hide" then
        f:Hide()
        lastUpdate = 0
        state = {}
        print("|cffa11585[MythicPlusHUD]|r Hidden.")
    else
        print("|cffa11585[MythicPlusHUD]|r Commands: /mphud reset | test | testdone | testlate | debug | hide")
    end
end
