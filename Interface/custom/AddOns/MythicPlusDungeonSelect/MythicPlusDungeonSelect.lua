-- MythicPlusDungeonSelect: Dark arcane dungeon selection UI.
-- Clean tooltip backdrop with purple tint and arcane accent overlays.

local ADDON_PREFIX = "MPHUD"

-- ----------------------------------------------------------------
--  Data stores
-- ----------------------------------------------------------------
local dungeons = {}
local levels = {}
local affixes = {}
local modifiers = {}
local selectedModifiers = {}
local rewardConfig = {}  -- platMult, goldMult, silverMult, bronzeMult, undyingBonus
local currentLevel = 0
local dataReady = false
local sortedDungeonsBySector = {}
local sortedLevels = {}

local selectedDungeon = nil
local selectedLevel = nil
local activeSector = 0

-- Shared global so MythicPlusHUD can look up modifier names
MPHUD_MODIFIER_DATA = MPHUD_MODIFIER_DATA or {}

local SECTOR_NAMES = {
    [0] = "Eastern Kingdoms",
    [1] = "Kalimdor",
    [2] = "Outland",
    [3] = "Northrend",
}
local NUM_SECTORS = 4
local DUNGEON_BUTTON_HEIGHT = 20
local MAX_VISIBLE_DUNGEONS = 16

-- ----------------------------------------------------------------
--  Palette
-- ----------------------------------------------------------------
local C_ARCANE      = { 0.65, 0.50, 0.90 }
local C_ARCANE_GLOW = { 0.78, 0.60, 1.00 }
local C_ARCANE_DIM  = { 0.40, 0.30, 0.60 }
local C_GOLD        = { 1.00, 0.82, 0.00 }
local C_WHITE       = { 1.00, 1.00, 1.00 }
local C_OFFWHITE    = { 0.85, 0.82, 0.90 }
local C_SILVER      = { 0.72, 0.70, 0.78 }
local C_DIM         = { 0.45, 0.42, 0.52 }
local C_LABEL       = { 0.62, 0.58, 0.72 }
local C_BOON        = { 0.30, 0.90, 0.30 }
local C_CURSE       = { 0.90, 0.30, 0.30 }

local function FormatTime(sec)
    sec = math.max(0, math.floor(sec))
    return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end

-- ================================================================
--  MAIN FRAME — Glyph-panel style
-- ================================================================
-- Use proportions close to the glyph frame so the texture works naturally.
local FRAME_WIDTH = 520
local FRAME_HEIGHT = 620
local LEFT_WIDTH = 220

local f = CreateFrame("Frame", "MythicPlusDungeonSelectFrame", UIParent)
f:SetSize(FRAME_WIDTH, FRAME_HEIGHT)
f:SetPoint("CENTER", UIParent, "CENTER", 0, 40)
f:SetFrameStrata("DIALOG")
f:SetMovable(true)
f:EnableMouse(true)
f:SetClampedToScreen(true)
f:RegisterForDrag("LeftButton")
f:SetScript("OnDragStart", f.StartMoving)
f:SetScript("OnDragStop", f.StopMovingOrSizing)
f:Hide()

-- Backdrop: tooltip bg tinted dark purple, tooltip border tinted purple
f:SetBackdrop({
    bgFile   = "Interface\\Tooltips\\UI-Tooltip-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 16,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
f:SetBackdropColor(0.07, 0.05, 0.13, 0.95)
f:SetBackdropBorderColor(0.50, 0.35, 0.75, 0.9)

-- Rune watermark in the detail pane area
local runeWatermark = f:CreateTexture(nil, "ARTWORK", nil, -1)
runeWatermark:SetTexture("Interface\\Spellbook\\UI-Glyph-Rune1")
runeWatermark:SetSize(140, 140)
runeWatermark:SetPoint("CENTER", f, "CENTER", 100, -10)
runeWatermark:SetAlpha(0.06)
runeWatermark:SetBlendMode("ADD")

-- Title
local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", f, "TOP", 0, -14)
title:SetText("War in the Ether")
title:SetTextColor(C_ARCANE_GLOW[1], C_ARCANE_GLOW[2], C_ARCANE_GLOW[3])

local subtitle = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
subtitle:SetPoint("TOP", title, "BOTTOM", 0, -2)
subtitle:SetText("Choose your challenge")
subtitle:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])

-- Close button
local closeBtn = CreateFrame("Button", nil, f, "UIPanelCloseButton")
closeBtn:SetPoint("TOPRIGHT", -4, -4)
closeBtn:SetScript("OnClick", function() f:Hide() end)

tinsert(UISpecialFrames, "MythicPlusDungeonSelectFrame")

-- ================================================================
--  SECTOR TABS
-- ================================================================
local sectorTabs = {}
local CONTENT_TOP = -52

-- Tab widths sized to fit text with padding
local TAB_WIDTHS = { [0] = 105, [1] = 62, [2] = 54, [3] = 68 }

for i = 0, NUM_SECTORS - 1 do
    local tab = CreateFrame("Button", "MPDSSectorTab" .. i, f)
    tab:SetSize(TAB_WIDTHS[i], 22)
    if i == 0 then
        tab:SetPoint("TOPLEFT", f, "TOPLEFT", 14, CONTENT_TOP)
    else
        tab:SetPoint("LEFT", sectorTabs[i - 1], "RIGHT", 1, 0)
    end

    tab.bg = tab:CreateTexture(nil, "ARTWORK")
    tab.bg:SetAllPoints()
    tab.bg:SetTexture("Interface\\Buttons\\UI-Listbox-Highlight2")

    -- Active indicator line
    tab.glow = tab:CreateTexture(nil, "ARTWORK", nil, 1)
    tab.glow:SetPoint("BOTTOMLEFT", 1, 0)
    tab.glow:SetPoint("BOTTOMRIGHT", -1, 0)
    tab.glow:SetHeight(2)
    tab.glow:SetTexture(C_ARCANE_GLOW[1], C_ARCANE_GLOW[2], C_ARCANE_GLOW[3], 0.8)
    tab.glow:Hide()

    tab.highlight = tab:CreateTexture(nil, "HIGHLIGHT")
    tab.highlight:SetAllPoints()
    tab.highlight:SetTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
    tab.highlight:SetBlendMode("ADD")
    tab.highlight:SetVertexColor(0.5, 0.4, 0.8, 0.25)

    tab.text = tab:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    tab.text:SetPoint("CENTER", 0, 1)
    tab.text:SetText(SECTOR_NAMES[i])

    tab.sectorId = i
    tab:SetScript("OnClick", function(self)
        activeSector = self.sectorId
        selectedDungeon = nil
        UpdateTabs()
        UpdateDungeonList()
        UpdateDetailPanel()
    end)

    sectorTabs[i] = tab
end

function UpdateTabs()
    for i = 0, NUM_SECTORS - 1 do
        local tab = sectorTabs[i]
        if i == activeSector then
            tab.bg:SetVertexColor(0.35, 0.25, 0.55, 0.7)
            tab.glow:Show()
            tab.text:SetTextColor(C_ARCANE_GLOW[1], C_ARCANE_GLOW[2], C_ARCANE_GLOW[3])
        else
            tab.bg:SetVertexColor(0.18, 0.14, 0.28, 0.45)
            tab.glow:Hide()
            tab.text:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])
        end
    end
end

-- ================================================================
--  LEFT PANEL — Dungeon List
-- ================================================================
local leftPanel = CreateFrame("Frame", nil, f)
leftPanel:SetPoint("TOPLEFT", f, "TOPLEFT", 14, CONTENT_TOP - 26)
leftPanel:SetSize(LEFT_WIDTH, FRAME_HEIGHT - 82)

-- Separator
local sep = f:CreateTexture(nil, "ARTWORK")
sep:SetPoint("TOPLEFT", leftPanel, "TOPRIGHT", 6, 4)
sep:SetPoint("BOTTOMLEFT", leftPanel, "BOTTOMRIGHT", 6, -4)
sep:SetWidth(1)
sep:SetTexture(C_ARCANE_DIM[1], C_ARCANE_DIM[2], C_ARCANE_DIM[3], 0.30)

-- Scroll frame
local scrollFrame = CreateFrame("ScrollFrame", "MPDSScrollFrame", leftPanel, "FauxScrollFrameTemplate")
scrollFrame:SetPoint("TOPLEFT", 0, 0)
scrollFrame:SetPoint("BOTTOMRIGHT", -22, 0)

local dungeonButtons = {}
for i = 1, MAX_VISIBLE_DUNGEONS do
    local btn = CreateFrame("Button", "MPDSDungeonBtn" .. i, leftPanel)
    btn:SetSize(LEFT_WIDTH - 24, DUNGEON_BUTTON_HEIGHT)
    if i == 1 then
        btn:SetPoint("TOPLEFT", leftPanel, "TOPLEFT", 2, -1)
    else
        btn:SetPoint("TOPLEFT", dungeonButtons[i - 1], "BOTTOMLEFT", 0, 0)
    end

    if i % 2 == 0 then
        btn.stripe = btn:CreateTexture(nil, "BACKGROUND")
        btn.stripe:SetAllPoints()
        btn.stripe:SetTexture(0.25, 0.18, 0.38, 0.08)
    end

    btn.highlight = btn:CreateTexture(nil, "HIGHLIGHT")
    btn.highlight:SetAllPoints()
    btn.highlight:SetTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
    btn.highlight:SetBlendMode("ADD")
    btn.highlight:SetVertexColor(0.55, 0.40, 0.85, 0.30)

    btn.selected = btn:CreateTexture(nil, "BACKGROUND", nil, 1)
    btn.selected:SetAllPoints()
    btn.selected:SetTexture("Interface\\Buttons\\UI-Listbox-Highlight2")
    btn.selected:SetVertexColor(0.55, 0.40, 0.85, 0.35)
    btn.selected:Hide()

    btn.nameText = btn:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    btn.nameText:SetPoint("LEFT", 6, 0)
    btn.nameText:SetPoint("RIGHT", -20, 0)
    btn.nameText:SetJustifyH("LEFT")
    btn.nameText:SetWordWrap(false)

    btn.lockIcon = btn:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    btn.lockIcon:SetPoint("RIGHT", -4, 0)

    btn.mapId = nil
    btn.unlocked = true

    btn:SetScript("OnClick", function(self)
        if self.dungeonKey and self.unlocked then
            selectedDungeon = self.dungeonKey
            UpdateDungeonList()
            UpdateDetailPanel()
        end
    end)

    dungeonButtons[i] = btn
end

scrollFrame:SetScript("OnVerticalScroll", function(self, offset)
    FauxScrollFrame_OnVerticalScroll(self, offset, DUNGEON_BUTTON_HEIGHT, UpdateDungeonList)
end)

function UpdateDungeonList()
    local dungeonList = sortedDungeonsBySector[activeSector] or {}
    local numDungeons = #dungeonList
    FauxScrollFrame_Update(scrollFrame, numDungeons, MAX_VISIBLE_DUNGEONS, DUNGEON_BUTTON_HEIGHT)
    local offset = FauxScrollFrame_GetOffset(scrollFrame)

    for i = 1, MAX_VISIBLE_DUNGEONS do
        local btn = dungeonButtons[i]
        local idx = i + offset
        if idx <= numDungeons then
            local dg = dungeonList[idx]
            btn.dungeonKey = dg.key
            btn.unlocked = dg.unlocked
            btn.nameText:SetText(dg.name)

            if dg.unlocked then
                btn.nameText:SetTextColor(C_OFFWHITE[1], C_OFFWHITE[2], C_OFFWHITE[3])
            else
                btn.nameText:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])
            end

            if dg.key == selectedDungeon then
                btn.selected:Show()
                btn.nameText:SetTextColor(C_WHITE[1], C_WHITE[2], C_WHITE[3])
                btn.lockIcon:SetText("")
            else
                btn.selected:Hide()
                btn.lockIcon:SetText(dg.unlocked and "" or "|TInterface\\LFGFrame\\UI-LFG-ICON-LOCK:12|t")
            end
            btn:Show()
        else
            btn.dungeonKey = nil
            btn:Hide()
        end
    end
end

-- ================================================================
--  RIGHT PANEL
-- ================================================================
local rightPanel = CreateFrame("Frame", nil, f)
rightPanel:SetPoint("TOPLEFT", leftPanel, "TOPRIGHT", 16, 0)
rightPanel:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -16, 14)

local placeholder = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormal")
placeholder:SetPoint("CENTER", 0, 20)
placeholder:SetText("Select a dungeon")
placeholder:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])

-- Dungeon name
local detailName = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
detailName:SetPoint("TOPLEFT", 0, -2)
detailName:SetPoint("TOPRIGHT", 0, -2)
detailName:SetJustifyH("LEFT")
detailName:SetWordWrap(false)
detailName:SetTextColor(C_WHITE[1], C_WHITE[2], C_WHITE[3])

local nameSep = rightPanel:CreateTexture(nil, "ARTWORK")
nameSep:SetPoint("TOPLEFT", detailName, "BOTTOMLEFT", 0, -5)
nameSep:SetPoint("TOPRIGHT", detailName, "BOTTOMRIGHT", 0, -5)
nameSep:SetHeight(1)
nameSep:SetTexture(C_ARCANE_DIM[1], C_ARCANE_DIM[2], C_ARCANE_DIM[3], 0.3)

-- ----------------------------------------------------------------
--  Level dropdown
-- ----------------------------------------------------------------
local levelLabel = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
levelLabel:SetPoint("TOPLEFT", nameSep, "BOTTOMLEFT", 0, -12)
levelLabel:SetText("Difficulty")
levelLabel:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local levelDropdown = CreateFrame("Frame", "MPDSLevelDropdown", rightPanel, "UIDropDownMenuTemplate")
levelDropdown:SetPoint("TOPLEFT", levelLabel, "BOTTOMLEFT", -16, -2)

local function LevelDropdown_OnClick(self)
    selectedLevel = self.value
    UIDropDownMenu_SetSelectedValue(levelDropdown, selectedLevel)
    UpdateDetailPanel()
end

local function LevelDropdown_Initialize(self, level)
    for _, lv in ipairs(sortedLevels) do
        local info = UIDropDownMenu_CreateInfo()
        local affixStr = lv.affixCount > 0
            and (lv.affixCount .. " affix" .. (lv.affixCount > 1 and "es" or ""))
            or "no affixes"
        info.text = string.format("Mythic +%d  (%sx, %s)", lv.level, lv.multiplier, affixStr)
        info.value = lv.level
        info.func = LevelDropdown_OnClick
        info.checked = (lv.level == selectedLevel)
        UIDropDownMenu_AddButton(info)
    end
end

UIDropDownMenu_SetWidth(levelDropdown, 190)
UIDropDownMenu_Initialize(levelDropdown, LevelDropdown_Initialize)

-- ----------------------------------------------------------------
--  Enemy scaling: health + damage with icons
-- ----------------------------------------------------------------
-- LFGRole atlas: DPS sword = left quarter, Healer cross = right quarter
local ICON_SWORD  = "|TInterface\\LFGFrame\\LFGRole:14:14:0:0:64:16:16:32:0:16|t"
local ICON_HEALTH = "|TInterface\\LFGFrame\\LFGRole:14:14:0:0:64:16:48:64:0:16|t"

local healthLine = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
healthLine:SetPoint("TOPLEFT", levelDropdown, "BOTTOMLEFT", 20, -8)
healthLine:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local damageLine = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
damageLine:SetPoint("TOPLEFT", healthLine, "BOTTOMLEFT", 0, -4)
damageLine:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

-- ----------------------------------------------------------------
--  Time limit
-- ----------------------------------------------------------------
local timeLabel = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
timeLabel:SetPoint("TOPLEFT", damageLine, "BOTTOMLEFT", 0, -4)
timeLabel:SetText("Time Limit")
timeLabel:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local timeValue = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
timeValue:SetPoint("LEFT", timeLabel, "RIGHT", 8, 0)

-- ----------------------------------------------------------------
--  Affix section
-- ----------------------------------------------------------------
local affixSep = rightPanel:CreateTexture(nil, "ARTWORK")
affixSep:SetPoint("TOPLEFT", timeLabel, "BOTTOMLEFT", 0, -10)
affixSep:SetSize(200, 1)
affixSep:SetTexture(C_ARCANE_DIM[1], C_ARCANE_DIM[2], C_ARCANE_DIM[3], 0.2)

local affixHeader = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
affixHeader:SetPoint("TOPLEFT", affixSep, "BOTTOMLEFT", 0, -6)
affixHeader:SetText("Random Affixes")
affixHeader:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

-- Affix slots: small rune-styled circles
local affixSlots = {}
for i = 1, 4 do
    local slot = CreateFrame("Frame", nil, rightPanel)
    slot:SetSize(28, 28)
    slot:EnableMouse(true)

    -- Circular ring border
    slot.ring = slot:CreateTexture(nil, "ARTWORK")
    slot.ring:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    slot.ring:SetAllPoints()
    slot.ring:SetVertexColor(C_ARCANE[1], C_ARCANE[2], C_ARCANE[3], 0.7)

    -- Question mark text
    slot.text = slot:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    slot.text:SetPoint("CENTER", 0, 0)
    slot.text:SetText("?")
    slot.text:SetTextColor(C_ARCANE_GLOW[1], C_ARCANE_GLOW[2], C_ARCANE_GLOW[3])

    slot.affixId = nil
    slot:Hide()

    slot:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText("Random Affix", C_ARCANE_GLOW[1], C_ARCANE_GLOW[2], C_ARCANE_GLOW[3])
        GameTooltip:AddLine("One will be chosen when the run begins.", 0.7, 0.7, 0.7, true)
        GameTooltip:AddLine(" ")
        for _, info in pairs(affixes) do
            GameTooltip:AddDoubleLine(
                info.name, info.desc,
                C_ARCANE[1], C_ARCANE[2], C_ARCANE[3],
                0.7, 0.7, 0.7)
        end
        GameTooltip:Show()
    end)
    slot:SetScript("OnLeave", function() GameTooltip:Hide() end)

    affixSlots[i] = slot
end

local affixNoneText = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
affixNoneText:SetText("None at this level")
affixNoneText:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])
affixNoneText:Hide()

-- ----------------------------------------------------------------
--  BOONS & CURSES SECTION
-- ----------------------------------------------------------------
local modSep = rightPanel:CreateTexture(nil, "ARTWORK")
modSep:SetSize(200, 1)
modSep:SetTexture(C_ARCANE_DIM[1], C_ARCANE_DIM[2], C_ARCANE_DIM[3], 0.2)

local modHeader = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
modHeader:SetText("Boons & Curses")
modHeader:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local MAX_MODIFIER_ROWS = 8
local MOD_TEXT_WIDTH = 210  -- available width after checkbox
local modRows = {}
for i = 1, MAX_MODIFIER_ROWS do
    local row = CreateFrame("CheckButton", "MPDSModRow" .. i, rightPanel, "UICheckButtonTemplate")
    row:SetSize(20, 28)
    row:Hide()

    -- Line 1: name + reward on the same line
    row.nameText = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    row.nameText:SetPoint("TOPLEFT", row, "TOPRIGHT", 2, -1)
    row.nameText:SetJustifyH("LEFT")
    row.nameText:SetWordWrap(false)

    row.rewardText = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    row.rewardText:SetPoint("LEFT", row.nameText, "RIGHT", 6, 0)
    row.rewardText:SetJustifyH("LEFT")

    -- Line 2: description as subtitle
    row.descText = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    row.descText:SetPoint("TOPLEFT", row.nameText, "BOTTOMLEFT", 0, -1)
    row.descText:SetWidth(MOD_TEXT_WIDTH)
    row.descText:SetJustifyH("LEFT")
    row.descText:SetWordWrap(false)

    row.modId = nil
    row:SetScript("OnClick", function(self)
        if self.modId then
            selectedModifiers[self.modId] = (self:GetChecked() == 1) or false
            UpdateModSummary()
        end
    end)

    modRows[i] = row
end

local modSummary = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
modSummary:SetJustifyH("LEFT")
modSummary:Hide()

function UpdateModSummary()
    local total = 0
    for id, sel in pairs(selectedModifiers) do
        if sel and modifiers[id] then
            total = total + modifiers[id].rewardMult
        end
    end
    if total == 0 then
        modSummary:Hide()
    else
        local sign = total > 0 and "+" or ""
        local color = total > 0 and "|cff4de94d" or "|cffff4444"
        modSummary:SetText("Reward modifier: " .. color .. sign .. string.format("%.1f", total) .. "x|r")
        modSummary:Show()
    end
    UpdateRewardPreview()
end

-- ----------------------------------------------------------------
--  REWARD PREVIEW
-- ----------------------------------------------------------------
local rewardSep = rightPanel:CreateTexture(nil, "ARTWORK")
rewardSep:SetSize(200, 1)
rewardSep:SetTexture(C_ARCANE_DIM[1], C_ARCANE_DIM[2], C_ARCANE_DIM[3], 0.2)

local rewardHeader = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
rewardHeader:SetText("Reward Preview")
rewardHeader:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local rewardBestLine = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
rewardBestLine:SetJustifyH("LEFT")
rewardBestLine:SetWidth(220)

local rewardWorstLine = rightPanel:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
rewardWorstLine:SetJustifyH("LEFT")
rewardWorstLine:SetWidth(220)

function UpdateRewardPreview()
    if not rewardConfig.platMult then
        rewardSep:Hide(); rewardHeader:Hide()
        rewardBestLine:Hide(); rewardWorstLine:Hide()
        return
    end

    local modTotal = 0
    for id, sel in pairs(selectedModifiers) do
        if sel and modifiers[id] then
            modTotal = modTotal + modifiers[id].rewardMult
        end
    end

    local best = rewardConfig.platMult + rewardConfig.undyingBonus + modTotal
    local worst = rewardConfig.bronzeMult + modTotal

    -- Clamp to 0
    if best < 0 then best = 0 end
    if worst < 0 then worst = 0 end

    local tc = { 0.88, 0.93, 1.00 } -- Platinum color
    rewardBestLine:SetText(
        string.format("|cffe0edff%.1fx|r  Platinum + Undying", best))

    rewardWorstLine:SetText(
        string.format("|cffcc8033%.1fx|r  Bronze", worst))

    rewardSep:Show(); rewardHeader:Show()
    rewardBestLine:Show(); rewardWorstLine:Show()
end

-- ----------------------------------------------------------------
--  ENTER BUTTON
-- ----------------------------------------------------------------
local enterBtn = CreateFrame("Button", "MPDSEnterButton", rightPanel, "UIPanelButtonTemplate")
enterBtn:SetSize(170, 26)
enterBtn:SetPoint("BOTTOM", rightPanel, "BOTTOM", 0, 8)
enterBtn:SetText("Enter the Ether")
enterBtn:Disable()

-- Glow behind button
local enterGlow = rightPanel:CreateTexture(nil, "BACKGROUND")
enterGlow:SetTexture("Interface\\Spellbook\\SpellBook-SkillLineTab-Glow")
enterGlow:SetSize(200, 50)
enterGlow:SetPoint("CENTER", enterBtn, "CENTER", 0, 0)
enterGlow:SetBlendMode("ADD")
enterGlow:SetVertexColor(C_ARCANE[1], C_ARCANE[2], C_ARCANE[3], 0.5)
enterGlow:Hide()

-- Pulse
local glowDir = 1
enterBtn:SetScript("OnUpdate", function(self, elapsed)
    if not enterGlow:IsShown() then return end
    local a = enterGlow:GetAlpha()
    a = a + elapsed * 0.35 * glowDir
    if a >= 0.50 then a = 0.50; glowDir = -1 end
    if a <= 0.18 then a = 0.18; glowDir = 1 end
    enterGlow:SetAlpha(a)
end)

enterBtn:SetScript("OnClick", function()
    if selectedDungeon and selectedLevel then
        local dg = dungeons[selectedDungeon]
        if dg then
            local modStr = ""
            local first = true
            for id, sel in pairs(selectedModifiers) do
                if sel then
                    if not first then modStr = modStr .. ":" end
                    modStr = modStr .. id
                    first = false
                end
            end
            if modStr ~= "" then
                SendChatMessage(string.format(".mythic start %d %d %d %s", dg.mapId, dg.wing, selectedLevel, modStr), "SAY")
            else
                SendChatMessage(string.format(".mythic start %d %d %d", dg.mapId, dg.wing, selectedLevel), "SAY")
            end
            f:Hide()
        end
    end
end)

-- ================================================================
--  Update detail panel
-- ================================================================
local detailElements = { detailName, nameSep, levelLabel, levelDropdown,
    healthLine, damageLine, timeLabel, timeValue,
    affixSep, affixHeader }

function UpdateDetailPanel()
    if not selectedDungeon then
        for _, el in ipairs(detailElements) do el:Hide() end
        for _, s in ipairs(affixSlots) do s:Hide() end
        affixNoneText:Hide()
        modSep:Hide(); modHeader:Hide(); modSummary:Hide()
        rewardSep:Hide(); rewardHeader:Hide(); rewardBestLine:Hide(); rewardWorstLine:Hide()
        for _, row in ipairs(modRows) do
            row:Hide(); row.nameText:SetText(""); row.descText:SetText(""); row.rewardText:SetText("")
        end
        enterBtn:Disable()
        enterGlow:Hide()
        placeholder:Show()
        return
    end

    placeholder:Hide()
    for _, el in ipairs(detailElements) do el:Show() end

    local dg = selectedDungeon and dungeons[selectedDungeon]
    if dg then detailName:SetText(dg.name) end

    if not selectedLevel then
        selectedLevel = currentLevel > 0 and currentLevel or 1
    end

    UIDropDownMenu_Initialize(levelDropdown, LevelDropdown_Initialize)
    UIDropDownMenu_SetSelectedValue(levelDropdown, selectedLevel)

    local lv = levels[selectedLevel]
    if lv then
        UIDropDownMenu_SetText(levelDropdown, string.format("Mythic +%d", lv.level))
        timeValue:SetText(FormatTime(lv.timeLimit))

        -- Health and damage scaling (multiplier applies to both)
        local mult = tonumber(lv.multiplier) or 1
        local pctIncrease = math.floor((mult - 1) * 100 + 0.5)
        healthLine:SetText(ICON_HEALTH .. " Health  |cffffffff+" .. pctIncrease .. "%|r")
        damageLine:SetText(ICON_SWORD .. " Damage  |cffffffff+" .. pctIncrease .. "%|r")

        -- Affix slots
        local count = lv.affixCount
        if count == 0 then
            for _, s in ipairs(affixSlots) do s:Hide() end
            affixNoneText:SetPoint("TOPLEFT", affixHeader, "BOTTOMLEFT", 0, -6)
            affixNoneText:Show()
        else
            affixNoneText:Hide()
            for idx = 1, 4 do
                local slot = affixSlots[idx]
                if idx <= count then
                    if idx == 1 then
                        slot:SetPoint("TOPLEFT", affixHeader, "BOTTOMLEFT", 4, -6)
                    else
                        slot:SetPoint("LEFT", affixSlots[idx - 1], "RIGHT", 6, 0)
                    end
                    slot:Show()
                else
                    slot:Hide()
                end
            end
        end
    end

    -- Boons & Curses
    -- Always anchor to affixHeader to avoid horizontal drift from affix slots
    local modAnchor = affixHeader
    local modAnchorYOff = -10
    if lv and lv.affixCount > 0 then
        modAnchorYOff = -40  -- clear the 28px affix slots + padding
    elseif affixNoneText:IsShown() then
        modAnchor = affixNoneText
        modAnchorYOff = -10
    end

    -- Sort modifiers: boons first, then curses
    local sortedMods = {}
    for _, mod in pairs(modifiers) do
        table.insert(sortedMods, mod)
    end
    table.sort(sortedMods, function(a, b)
        if a.type ~= b.type then return a.type < b.type end
        return a.id < b.id
    end)

    local hasModifiers = (#sortedMods > 0)
    if hasModifiers then
        modSep:ClearAllPoints()
        modSep:SetPoint("TOPLEFT", modAnchor, "BOTTOMLEFT", -4, modAnchorYOff)
        modSep:Show()

        modHeader:ClearAllPoints()
        modHeader:SetPoint("TOPLEFT", modSep, "BOTTOMLEFT", 0, -6)
        modHeader:Show()

        local prevRow = nil
        for i, mod in ipairs(sortedMods) do
            if i > MAX_MODIFIER_ROWS then break end
            local row = modRows[i]
            row.modId = mod.id

            row:ClearAllPoints()
            if i == 1 then
                row:SetPoint("TOPLEFT", modHeader, "BOTTOMLEFT", 0, -4)
            else
                row:SetPoint("TOPLEFT", modRows[i - 1], "BOTTOMLEFT", 0, -4)
            end

            -- Restore checkbox state
            row:SetChecked(selectedModifiers[mod.id] and true or false)

            -- Line 1: name + reward modifier
            local nc = mod.type == 0 and C_BOON or C_CURSE
            row.nameText:SetText(mod.name)
            row.nameText:SetTextColor(nc[1], nc[2], nc[3])

            local sign = mod.rewardMult > 0 and "+" or ""
            local rc = mod.rewardMult > 0 and C_BOON or C_CURSE
            row.rewardText:SetText("(" .. sign .. string.format("%.1f", mod.rewardMult) .. "x)")
            row.rewardText:SetTextColor(rc[1], rc[2], rc[3])

            -- Line 2: description subtitle
            row.descText:SetText(mod.description)
            row.descText:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])

            row:Show()
            prevRow = row
        end

        -- Hide unused rows
        for i = #sortedMods + 1, MAX_MODIFIER_ROWS do
            modRows[i]:Hide()
            modRows[i].nameText:SetText("")
            modRows[i].descText:SetText("")
            modRows[i].rewardText:SetText("")
        end

        -- Summary line
        modSummary:ClearAllPoints()
        local lastRow = modRows[math.min(#sortedMods, MAX_MODIFIER_ROWS)]
        modSummary:SetPoint("TOPLEFT", lastRow, "BOTTOMLEFT", 22, -4)
        UpdateModSummary()
    else
        modSep:Hide(); modHeader:Hide(); modSummary:Hide()
        for _, row in ipairs(modRows) do
            row:Hide(); row.nameText:SetText(""); row.descText:SetText(""); row.rewardText:SetText("")
        end
    end

    -- Reward preview — anchored just above the enter button
    rewardSep:ClearAllPoints()
    rewardSep:SetPoint("BOTTOMLEFT", enterBtn, "TOPLEFT", -15, 36)
    rewardSep:Show()

    rewardHeader:ClearAllPoints()
    rewardHeader:SetPoint("TOPLEFT", rewardSep, "BOTTOMLEFT", 0, -4)
    rewardHeader:Show()

    rewardBestLine:ClearAllPoints()
    rewardBestLine:SetPoint("TOPLEFT", rewardHeader, "BOTTOMLEFT", 2, -2)

    rewardWorstLine:ClearAllPoints()
    rewardWorstLine:SetPoint("TOPLEFT", rewardBestLine, "BOTTOMLEFT", 0, -1)

    UpdateRewardPreview()

    enterBtn:Enable()
    enterGlow:Show()
end

-- ================================================================
--  Data parsing
-- ================================================================
local function ClearData()
    dungeons = {}; levels = {}; affixes = {}; modifiers = {}; selectedModifiers = {}
    rewardConfig = {}
    currentLevel = 0; dataReady = false
    sortedDungeonsBySector = {}; sortedLevels = {}
    selectedDungeon = nil
end

local function SortData()
    sortedDungeonsBySector = {}
    for _, dg in pairs(dungeons) do
        local sid = dg.sectorId
        if not sortedDungeonsBySector[sid] then sortedDungeonsBySector[sid] = {} end
        table.insert(sortedDungeonsBySector[sid], dg)
    end
    for _, list in pairs(sortedDungeonsBySector) do
        table.sort(list, function(a, b) return a.name < b.name end)
    end
    sortedLevels = {}
    for _, lv in pairs(levels) do table.insert(sortedLevels, lv) end
    table.sort(sortedLevels, function(a, b) return a.level < b.level end)
end

local function OnAddonMessage(prefix, msg, channel, sender)
    if prefix ~= ADDON_PREFIX then return end
    local msgType = msg:sub(1, 1)

    if msgType == "D" then
        -- D|mapId|wing|sectorId|name|unlocked
        local _, mapId, wing, sectorId, name, unlocked = strsplit("|", msg)
        mapId = tonumber(mapId); wing = tonumber(wing) or 0; sectorId = tonumber(sectorId)
        if mapId and sectorId then
            local key = mapId .. ":" .. wing
            dungeons[key] = { mapId=mapId, wing=wing, sectorId=sectorId,
                name=name or "Unknown", unlocked=(unlocked=="1"), key=key }
        end
    elseif msgType == "L" then
        local _, level, timeLimit, affixCount, multiplier = strsplit("|", msg)
        level = tonumber(level)
        if level then
            levels[level] = { level=level, timeLimit=tonumber(timeLimit) or 2400,
                affixCount=tonumber(affixCount) or 0, multiplier=multiplier or "1.00" }
        end
    elseif msgType == "A" then
        local _, affixType, name, desc = strsplit("|", msg)
        affixType = tonumber(affixType)
        if affixType then
            affixes[affixType] = { id=affixType, name=name or "Unknown", desc=desc or "" }
        end
    elseif msgType == "M" then
        local _, id, mtype, name, desc, rewardMult = strsplit("|", msg)
        id = tonumber(id)
        if id then
            local mod = {
                id = id,
                type = tonumber(mtype) or 0,
                name = name or "Unknown",
                description = desc or "",
                rewardMult = tonumber(rewardMult) or 0,
            }
            modifiers[id] = mod
            MPHUD_MODIFIER_DATA[id] = mod
        end
    elseif msgType == "R" then
        -- R|platMult|goldMult|silverMult|bronzeMult|undyingBonus
        local _, platMult, goldMult, silverMult, bronzeMult, undyingBonus = strsplit("|", msg)
        rewardConfig = {
            platMult = tonumber(platMult) or 3.0,
            goldMult = tonumber(goldMult) or 2.0,
            silverMult = tonumber(silverMult) or 1.5,
            bronzeMult = tonumber(bronzeMult) or 1.0,
            undyingBonus = tonumber(undyingBonus) or 0.5,
        }
    elseif msgType == "C" then
        local _, lvl = strsplit("|", msg)
        currentLevel = tonumber(lvl) or 0
        selectedLevel = currentLevel > 0 and currentLevel or 1
    elseif msgType == "E" then
        dataReady = true
        SortData()
        activeSector = 0
        for i = 0, NUM_SECTORS - 1 do
            if sortedDungeonsBySector[i] and #sortedDungeonsBySector[i] > 0 then
                activeSector = i; break
            end
        end
        UpdateTabs(); UpdateDungeonList(); UpdateDetailPanel()
        f:Show()
    end
end

-- ================================================================
--  Events
-- ================================================================
local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("CHAT_MSG_ADDON")
eventFrame:SetScript("OnEvent", function(self, event, ...)
    if event == "CHAT_MSG_ADDON" then OnAddonMessage(...) end
end)
-- RegisterAddonMessagePrefix does not exist in 3.3.5a (added in 4.0)
if RegisterAddonMessagePrefix then RegisterAddonMessagePrefix(ADDON_PREFIX) end

-- ================================================================
--  Slash commands
-- ================================================================
SLASH_MPDS1 = "/mpds"
SlashCmdList["MPDS"] = function(msg)
    if msg == "test" then
        ClearData()
        local td = {
            {574,3,"Utgarde Keep"},{575,3,"Utgarde Pinnacle"},{576,3,"The Nexus"},
            {578,3,"The Oculus"},{601,3,"Azjol-Nerub"},{619,3,"Ahn'kahet"},
            {600,3,"Drak'Tharon Keep"},{604,3,"Gundrak"},{602,3,"Halls of Lightning"},
            {599,3,"Halls of Stone"},{595,3,"Culling of Stratholme"},{608,3,"Violet Hold"},
            {36,0,"Deadmines"},{33,0,"Shadowfang Keep"},{34,0,"Stormwind Stockade"},
            {43,1,"Wailing Caverns"},{389,1,"Ragefire Chasm"},{90,1,"Gnomeregan"},
            {540,2,"Hellfire Ramparts"},{542,2,"Blood Furnace"},{543,2,"Shattered Halls"},
        }
        for _, d in ipairs(td) do
            local w = d[4] or 0
            local key = d[1] .. ":" .. w
            dungeons[key] = { mapId=d[1], wing=w, sectorId=d[2], name=d[3], unlocked=true, key=key }
        end
        for i = 1, 20 do
            local ac = math.floor(i / 5)
            levels[i] = { level=i, timeLimit=i<=4 and 2700 or (i<=12 and 2400 or 2100),
                affixCount=ac, multiplier=string.format("%.2f", 1+0.1*i+0.005*i*i) }
        end
        affixes[0]={id=0,name="Fortified",desc="All enemies have increased health"}
        affixes[1]={id=1,name="Bolstering",desc="Trash mobs have increased health"}
        affixes[2]={id=2,name="Tyrannical",desc="Bosses have increased health"}
        affixes[3]={id=3,name="Teeming",desc="Trash mobs can spawn copies"}
        affixes[4]={id=4,name="Raging",desc="All enemies deal more damage"}
        affixes[5]={id=5,name="Volcanic",desc="Random explosions damage players"}
        affixes[6]={id=6,name="Storming",desc="Lightning spheres spawn periodically"}
        affixes[7]={id=7,name="Enrage",desc="Enemies can randomly enrage"}
        affixes[8]={id=8,name="Entangling",desc="Enemies cast roots on players"}
        modifiers[1]={id=1,type=0,name="Ethereal Fortitude",description="+30% max HP",rewardMult=-0.20}
        modifiers[2]={id=2,type=0,name="Time Dilation",description="+20% time limit",rewardMult=-0.30}
        modifiers[3]={id=3,type=1,name="Frailty",description="-25% max HP",rewardMult=0.50}
        modifiers[4]={id=4,type=1,name="Swarming",description="+50% trash density",rewardMult=0.40}
        modifiers[5]={id=5,type=1,name="Entropy",description="-30% healing",rewardMult=0.30}
        modifiers[6]={id=6,type=1,name="Hubris",description="+40% boss damage",rewardMult=0.60}
        MPHUD_MODIFIER_DATA = modifiers
        selectedModifiers = {}
        rewardConfig = { platMult=3.0, goldMult=2.0, silverMult=1.5, bronzeMult=1.0, undyingBonus=0.5 }
        currentLevel=5; selectedLevel=5; dataReady=true
        SortData(); activeSector=0
        UpdateTabs(); UpdateDungeonList(); UpdateDetailPanel()
        f:Show()
    elseif msg == "hide" then
        f:Hide()
    end
end
