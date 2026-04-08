-- TransmogUI: Retail-style transmogrification UI.
-- Replaces the gossip menu with a proper frame featuring 3D model preview,
-- equipment slot buttons, scrollable appearance grid, and live try-on.

local ADDON_PREFIX = "TMOG"
-- RegisterAddonMessagePrefix does not exist in 3.3.5a (added in 4.0)
if RegisterAddonMessagePrefix then
    RegisterAddonMessagePrefix(ADDON_PREFIX)
end

-- ----------------------------------------------------------------
--  Data stores
-- ----------------------------------------------------------------
local slotData = {}
local appearances = {}
local presets = {}
local config = {}
local selectedSlot = nil
local selectedAppearance = nil
local slotCost = 0
local slotTotal = 0
local pendingItemInfo = {}

-- Hidden tooltip used to force the client to cache item data in 3.3.5a.
-- GetItemInfo alone doesn't reliably trigger a server fetch; SetHyperlink does.
local cacheTip = CreateFrame("GameTooltip", "TransmogCacheTip", UIParent, "GameTooltipTemplate")
cacheTip:SetOwner(UIParent, "ANCHOR_NONE")

local function ForceCache(itemId)
    if itemId and itemId > 0 then
        cacheTip:SetHyperlink("item:" .. itemId)
    end
end

-- ----------------------------------------------------------------
--  Slot definitions (transmog-eligible slots only)
-- ----------------------------------------------------------------
local SLOT_ORDER = { 0, 2, 4, 14, 3, 8, 5, 6, 9, 7, 15, 16, 17 }

local SLOT_NAMES = {
    [0]  = "Head",
    [2]  = "Shoulder",
    [3]  = "Back",
    [4]  = "Chest",
    [5]  = "Waist",
    [6]  = "Legs",
    [7]  = "Feet",
    [8]  = "Wrist",
    [9]  = "Hands",
    [14] = "Shirt",
    [15] = "Main Hand",
    [16] = "Off Hand",
    [17] = "Ranged",
}

local SLOT_ICONS = {
    [0]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Head",
    [2]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Shoulder",
    [3]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Chest",
    [4]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Chest",
    [5]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Waist",
    [6]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Legs",
    [7]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Feet",
    [8]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Wrists",
    [9]  = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Hands",
    [14] = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Shirt",
    [15] = "Interface\\PaperDoll\\UI-PaperDoll-Slot-MainHand",
    [16] = "Interface\\PaperDoll\\UI-PaperDoll-Slot-SecondaryHand",
    [17] = "Interface\\PaperDoll\\UI-PaperDoll-Slot-Ranged",
}

-- ----------------------------------------------------------------
--  Quality colors
-- ----------------------------------------------------------------
local QUALITY_COLORS = {
    [0] = { 0.62, 0.62, 0.62 }, -- Poor (grey)
    [1] = { 1.00, 1.00, 1.00 }, -- Common (white)
    [2] = { 0.12, 1.00, 0.00 }, -- Uncommon (green)
    [3] = { 0.00, 0.44, 0.87 }, -- Rare (blue)
    [4] = { 0.64, 0.21, 0.93 }, -- Epic (purple)
    [5] = { 1.00, 0.50, 0.00 }, -- Legendary (orange)
    [6] = { 0.90, 0.80, 0.50 }, -- Artifact
    [7] = { 0.00, 0.80, 1.00 }, -- Heirloom
}

-- ----------------------------------------------------------------
--  Palette
-- ----------------------------------------------------------------
local C_GOLD    = { 1.00, 0.82, 0.00 }
local C_WHITE   = { 1.00, 1.00, 1.00 }
local C_DIM     = { 0.50, 0.50, 0.50 }
local C_LABEL   = { 0.75, 0.70, 0.85 }
local C_SUCCESS = { 0.30, 1.00, 0.30 }
local C_ERROR   = { 1.00, 0.30, 0.30 }

-- ----------------------------------------------------------------
--  Money formatting
-- ----------------------------------------------------------------
local function FormatMoney(copper)
    if not copper or copper == 0 then return "Free" end
    local gold = math.floor(copper / 10000)
    local silver = math.floor((copper % 10000) / 100)
    local cop = copper % 100
    local str = ""
    if gold > 0 then
        str = str .. "|cffffd700" .. gold .. "|r|TInterface\\MoneyFrame\\UI-GoldIcon:12:12:2:0|t "
    end
    if silver > 0 then
        str = str .. "|cffc7c7cf" .. silver .. "|r|TInterface\\MoneyFrame\\UI-SilverIcon:12:12:2:0|t "
    end
    if cop > 0 or str == "" then
        str = str .. "|cffeda55f" .. cop .. "|r|TInterface\\MoneyFrame\\UI-CopperIcon:12:12:2:0|t"
    end
    return str
end

-- ================================================================
--  MAIN FRAME
-- ================================================================
local FRAME_WIDTH  = 660
local FRAME_HEIGHT = 500
local LEFT_WIDTH   = 220
local GRID_COLS    = 8
local ICON_SIZE    = 40
local ICON_PAD     = 4

local f = CreateFrame("Frame", "TransmogUIFrame", UIParent)
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

f:SetBackdrop({
    bgFile   = "Interface\\Tooltips\\UI-Tooltip-Background",
    edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
    tile = true, tileSize = 16, edgeSize = 16,
    insets = { left = 4, right = 4, top = 4, bottom = 4 },
})
f:SetBackdropColor(0.06, 0.04, 0.10, 0.95)
f:SetBackdropBorderColor(0.55, 0.40, 0.75, 0.9)

-- Register as special frame so Escape closes it
tinsert(UISpecialFrames, "TransmogUIFrame")

-- Title
local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
title:SetPoint("TOP", f, "TOP", 0, -12)
title:SetText("Transmogrification")
title:SetTextColor(C_GOLD[1], C_GOLD[2], C_GOLD[3])

-- Close button
local closeBtn = CreateFrame("Button", nil, f, "UIPanelCloseButton")
closeBtn:SetPoint("TOPRIGHT", f, "TOPRIGHT", -2, -2)

-- Separator line between left and right panels
local sep = f:CreateTexture(nil, "ARTWORK")
sep:SetTexture("Interface\\Tooltips\\UI-Tooltip-Border")
sep:SetWidth(2)
sep:SetPoint("TOP", f, "TOPLEFT", LEFT_WIDTH + 10, -36)
sep:SetPoint("BOTTOM", f, "BOTTOMLEFT", LEFT_WIDTH + 10, 50)
sep:SetAlpha(0.3)

-- ================================================================
--  LEFT PANEL: 3D Model + Slot Buttons
-- ================================================================

-- 3D Character Model
local model = CreateFrame("DressUpModel", "TransmogUIModel", f)
model:SetSize(180, 230)
model:SetPoint("TOP", f, "TOPLEFT", LEFT_WIDTH / 2 + 6, -38)

local function RefreshModel()
    model:SetUnit("player")
    model:Dress()
    -- Re-apply active transmogs
    for slot, data in pairs(slotData) do
        if data.fakeEntry and data.fakeEntry > 0 and data.fakeEntry ~= 1 then
            model:TryOn("item:" .. data.fakeEntry)
        end
    end
end

model:SetScript("OnShow", function(self)
    RefreshModel()
    self:SetRotation(0)
end)

-- Model rotation buttons
local rotLeft = CreateFrame("Button", nil, f)
rotLeft:SetSize(24, 24)
rotLeft:SetPoint("BOTTOMLEFT", model, "BOTTOMLEFT", 10, -2)
rotLeft:SetNormalTexture("Interface\\Buttons\\UI-RotationLeft-Button-Up")
rotLeft:SetPushedTexture("Interface\\Buttons\\UI-RotationLeft-Button-Down")
rotLeft:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Round", "ADD")
local rotLeftTimer = nil
rotLeft:SetScript("OnMouseDown", function()
    rotLeftTimer = true
end)
rotLeft:SetScript("OnMouseUp", function()
    rotLeftTimer = nil
end)

local rotRight = CreateFrame("Button", nil, f)
rotRight:SetSize(24, 24)
rotRight:SetPoint("BOTTOMRIGHT", model, "BOTTOMRIGHT", -10, -2)
rotRight:SetNormalTexture("Interface\\Buttons\\UI-RotationRight-Button-Up")
rotRight:SetPushedTexture("Interface\\Buttons\\UI-RotationRight-Button-Down")
rotRight:SetHighlightTexture("Interface\\Buttons\\ButtonHilight-Round", "ADD")
local rotRightTimer = nil
rotRight:SetScript("OnMouseDown", function()
    rotRightTimer = true
end)
rotRight:SetScript("OnMouseUp", function()
    rotRightTimer = nil
end)

f:SetScript("OnUpdate", function(self, elapsed)
    local ROT_SPEED = 1.5
    if rotLeftTimer then
        model:SetRotation(model:GetFacing() + elapsed * ROT_SPEED)
    end
    if rotRightTimer then
        model:SetRotation(model:GetFacing() - elapsed * ROT_SPEED)
    end
end)

-- Slot buttons
local slotButtons = {}
local SLOT_BTN_SIZE = 36
local SLOT_BTN_PAD = 3
local SLOTS_PER_ROW = 4

local slotContainer = CreateFrame("Frame", nil, f)
slotContainer:SetPoint("TOP", model, "BOTTOM", 0, -6)
slotContainer:SetSize(LEFT_WIDTH - 20, 120)

for i, slot in ipairs(SLOT_ORDER) do
    local row = math.floor((i - 1) / SLOTS_PER_ROW)
    local col = (i - 1) % SLOTS_PER_ROW
    local xOff = col * (SLOT_BTN_SIZE + SLOT_BTN_PAD)
    local yOff = -row * (SLOT_BTN_SIZE + SLOT_BTN_PAD)

    local btn = CreateFrame("Button", "TransmogSlotBtn" .. slot, slotContainer)
    btn:SetSize(SLOT_BTN_SIZE, SLOT_BTN_SIZE)
    btn:SetPoint("TOPLEFT", slotContainer, "TOPLEFT", xOff, yOff)
    btn.slot = slot

    -- Background
    local bg = btn:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetTexture("Interface\\Tooltips\\UI-Tooltip-Background")
    bg:SetVertexColor(0.15, 0.12, 0.22, 0.8)
    btn.bg = bg

    -- Icon
    local icon = btn:CreateTexture(nil, "ARTWORK")
    icon:SetPoint("TOPLEFT", 2, -2)
    icon:SetPoint("BOTTOMRIGHT", -2, 2)
    icon:SetTexture(SLOT_ICONS[slot] or "Interface\\Icons\\INV_Misc_QuestionMark")
    btn.icon = icon

    -- Border for selected/transmogged state
    local border = btn:CreateTexture(nil, "OVERLAY")
    border:SetPoint("TOPLEFT", -10, 10)
    border:SetPoint("BOTTOMRIGHT", 10, -10)
    border:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    border:SetBlendMode("ADD")
    border:SetAlpha(0)
    btn.border = border

    -- Highlight
    local hl = btn:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    hl:SetAlpha(0.3)

    -- Tooltip
    btn:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        local name = SLOT_NAMES[self.slot] or "Slot " .. self.slot
        GameTooltip:SetText(name, C_WHITE[1], C_WHITE[2], C_WHITE[3])
        local data = slotData[self.slot]
        if data and data.itemId > 0 then
            GameTooltip:AddLine(" ")
            GameTooltip:SetHyperlink("item:" .. data.itemId)
        end
        if data and data.fakeEntry > 0 and data.fakeEntry ~= 1 then
            GameTooltip:AddLine("Transmogrified to:", C_GOLD[1], C_GOLD[2], C_GOLD[3])
            local tName = GetItemInfo(data.fakeEntry)
            if tName then
                GameTooltip:AddLine(tName, 0.5, 1.0, 0.5)
            end
        elseif data and data.fakeEntry == 1 then
            GameTooltip:AddLine("Hidden", C_DIM[1], C_DIM[2], C_DIM[3])
        end
        GameTooltip:Show()
    end)
    btn:SetScript("OnLeave", function()
        GameTooltip:Hide()
    end)

    -- Click handler: select this slot
    btn:SetScript("OnClick", function(self)
        selectedSlot = self.slot
        selectedAppearance = nil
        appearances[self.slot] = nil
        UpdateSlotHighlights()
        SendChatMessage(".transmog select " .. self.slot, "SAY")
    end)

    slotButtons[slot] = btn
end

-- Center the slot grid
local totalRows = math.ceil(#SLOT_ORDER / SLOTS_PER_ROW)
local gridWidth = SLOTS_PER_ROW * (SLOT_BTN_SIZE + SLOT_BTN_PAD) - SLOT_BTN_PAD
slotContainer:SetSize(gridWidth, totalRows * (SLOT_BTN_SIZE + SLOT_BTN_PAD))
-- Re-center relative to left panel
slotContainer:ClearAllPoints()
slotContainer:SetPoint("TOP", model, "BOTTOM", 0, -8)

function UpdateSlotHighlights()
    for slot, btn in pairs(slotButtons) do
        local data = slotData[slot]
        if slot == selectedSlot then
            btn.border:SetVertexColor(1.0, 0.82, 0.0, 1.0)
            btn.border:SetAlpha(0.7)
        elseif data and data.fakeEntry and data.fakeEntry > 0 then
            btn.border:SetVertexColor(0.6, 0.3, 0.9, 1.0)
            btn.border:SetAlpha(0.5)
        else
            btn.border:SetAlpha(0)
        end
    end
end

local function UpdateSlotIcons()
    for slot, btn in pairs(slotButtons) do
        local data = slotData[slot]
        if data and data.itemId > 0 then
            local displayId = data.fakeEntry > 0 and data.fakeEntry ~= 1 and data.fakeEntry or data.itemId
            local _, _, _, _, _, _, _, _, _, texPath = GetItemInfo(displayId)
            if texPath then
                btn.icon:SetTexture(texPath)
            end
        else
            btn.icon:SetTexture(SLOT_ICONS[slot] or "Interface\\Icons\\INV_Misc_QuestionMark")
        end
    end
end

-- ================================================================
--  RIGHT PANEL: Search + Appearance Grid + Actions
-- ================================================================
local rightX = LEFT_WIDTH + 20

-- Search box
local searchBox = CreateFrame("EditBox", "TransmogUISearch", f, "InputBoxTemplate")
searchBox:SetSize(FRAME_WIDTH - rightX - 30, 20)
searchBox:SetPoint("TOPLEFT", f, "TOPLEFT", rightX + 8, -42)
searchBox:SetAutoFocus(false)
searchBox:SetMaxLetters(50)

local searchLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
searchLabel:SetPoint("RIGHT", searchBox, "LEFT", -4, 0)
searchLabel:SetText("Search:")
searchLabel:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

searchBox:SetScript("OnEnterPressed", function(self)
    local text = self:GetText()
    if selectedSlot then
        appearances[selectedSlot] = nil
        if text and text ~= "" then
            SendChatMessage(".transmog search " .. selectedSlot .. " " .. text, "SAY")
        else
            SendChatMessage(".transmog select " .. selectedSlot, "SAY")
        end
    end
    self:ClearFocus()
end)

searchBox:SetScript("OnEscapePressed", function(self)
    self:SetText("")
    self:ClearFocus()
    if selectedSlot then
        appearances[selectedSlot] = nil
        SendChatMessage(".transmog select " .. selectedSlot, "SAY")
    end
end)

-- Status / slot label
local slotLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
slotLabel:SetPoint("TOPLEFT", searchBox, "BOTTOMLEFT", 0, -8)
slotLabel:SetText("Select an equipment slot")
slotLabel:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local countLabel = f:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
countLabel:SetPoint("TOPRIGHT", searchBox, "BOTTOMRIGHT", 0, -8)
countLabel:SetTextColor(C_DIM[1], C_DIM[2], C_DIM[3])

-- Appearance grid scroll area
local GRID_HEIGHT = 290
local scrollFrame = CreateFrame("ScrollFrame", "TransmogUIScrollFrame", f)
scrollFrame:SetPoint("TOPLEFT", slotLabel, "BOTTOMLEFT", 0, -6)
scrollFrame:SetSize(FRAME_WIDTH - rightX - 22, GRID_HEIGHT)

local scrollChild = CreateFrame("Frame", nil, scrollFrame)
scrollChild:SetSize(1, 1) -- Will be resized dynamically
scrollFrame:SetScrollChild(scrollChild)

-- Scrollbar
local scrollBar = CreateFrame("Slider", "TransmogUIScrollBar", scrollFrame, "UIPanelScrollBarTemplate")
scrollBar:SetPoint("TOPRIGHT", scrollFrame, "TOPRIGHT", 16, -16)
scrollBar:SetPoint("BOTTOMRIGHT", scrollFrame, "BOTTOMRIGHT", 16, 16)
scrollBar:SetMinMaxValues(0, 1)
scrollBar:SetValueStep(1)
scrollBar:SetValue(0)
scrollBar:SetWidth(16)

scrollBar:SetScript("OnValueChanged", function(self, value)
    scrollFrame:SetVerticalScroll(value)
end)

scrollFrame:EnableMouseWheel(true)
scrollFrame:SetScript("OnMouseWheel", function(self, delta)
    local cur = scrollBar:GetValue()
    local step = ICON_SIZE + ICON_PAD
    scrollBar:SetValue(cur - delta * step * 2)
end)

-- Grid item buttons (created on demand)
local gridButtons = {}

local function GetOrCreateGridButton(index)
    if gridButtons[index] then return gridButtons[index] end

    local btn = CreateFrame("Button", "TransmogGridBtn" .. index, scrollChild)
    btn:SetSize(ICON_SIZE, ICON_SIZE)

    local bg = btn:CreateTexture(nil, "BACKGROUND")
    bg:SetAllPoints()
    bg:SetTexture("Interface\\Tooltips\\UI-Tooltip-Background")
    bg:SetVertexColor(0.12, 0.10, 0.18, 0.8)
    btn.bg = bg

    local icon = btn:CreateTexture(nil, "ARTWORK")
    icon:SetPoint("TOPLEFT", 2, -2)
    icon:SetPoint("BOTTOMRIGHT", -2, 2)
    icon:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
    btn.icon = icon

    local border = btn:CreateTexture(nil, "OVERLAY")
    border:SetPoint("TOPLEFT", -10, 10)
    border:SetPoint("BOTTOMRIGHT", 10, -10)
    border:SetTexture("Interface\\Buttons\\UI-ActionButton-Border")
    border:SetBlendMode("ADD")
    border:SetAlpha(0)
    btn.border = border

    local hl = btn:CreateTexture(nil, "HIGHLIGHT")
    hl:SetAllPoints()
    hl:SetTexture("Interface\\Buttons\\ButtonHilight-Square", "ADD")
    hl:SetAlpha(0.4)

    btn:SetScript("OnEnter", function(self)
        if self.itemId then
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink("item:" .. self.itemId)
            GameTooltip:Show()
            -- Live preview on model
            model:Undress()
            model:Dress()
            for slot, data in pairs(slotData) do
                if data.fakeEntry and data.fakeEntry > 0 and data.fakeEntry ~= 1 then
                    model:TryOn("item:" .. data.fakeEntry)
                end
            end
            model:TryOn("item:" .. self.itemId)
        end
    end)

    btn:SetScript("OnLeave", function(self)
        GameTooltip:Hide()
        RefreshModel()
    end)

    btn:SetScript("OnClick", function(self)
        if self.itemId then
            selectedAppearance = self.itemId
            UpdateGridSelection()
            UpdateActionButtons()
        end
    end)

    gridButtons[index] = btn
    return btn
end

function UpdateGridSelection()
    for _, btn in pairs(gridButtons) do
        if btn:IsShown() and btn.itemId == selectedAppearance then
            btn.border:SetVertexColor(1.0, 0.82, 0.0, 1.0)
            btn.border:SetAlpha(0.8)
        elseif btn:IsShown() and btn.itemId then
            local qc = QUALITY_COLORS[btn.quality or 1] or QUALITY_COLORS[1]
            btn.border:SetVertexColor(qc[1], qc[2], qc[3], 1.0)
            btn.border:SetAlpha(0.4)
        else
            btn.border:SetAlpha(0)
        end
    end
end

local function PopulateGrid(slot)
    local items = appearances[slot] or {}
    local cols = GRID_COLS
    local totalRows = math.ceil(#items / cols)
    local childHeight = math.max(totalRows * (ICON_SIZE + ICON_PAD), GRID_HEIGHT)
    scrollChild:SetSize(cols * (ICON_SIZE + ICON_PAD), childHeight)

    -- Update scrollbar range
    local maxScroll = math.max(0, childHeight - GRID_HEIGHT)
    scrollBar:SetMinMaxValues(0, maxScroll)
    scrollBar:SetValue(0)

    -- Position buttons
    for i, item in ipairs(items) do
        local btn = GetOrCreateGridButton(i)
        local row = math.floor((i - 1) / cols)
        local col = (i - 1) % cols
        btn:SetPoint("TOPLEFT", scrollChild, "TOPLEFT",
            col * (ICON_SIZE + ICON_PAD), -row * (ICON_SIZE + ICON_PAD))
        btn.itemId = item.itemId
        btn.quality = item.quality

        -- Set icon
        local _, _, _, _, _, _, _, _, _, texPath = GetItemInfo(item.itemId)
        if texPath then
            btn.icon:SetTexture(texPath)
        else
            btn.icon:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
            -- Queue for lazy loading and force client to fetch
            pendingItemInfo[item.itemId] = true
            ForceCache(item.itemId)
        end

        -- Quality border
        local qc = QUALITY_COLORS[item.quality] or QUALITY_COLORS[1]
        btn.border:SetVertexColor(qc[1], qc[2], qc[3], 1.0)
        btn.border:SetAlpha(0.4)

        btn:Show()
    end

    -- Hide excess buttons
    for i = #items + 1, #gridButtons do
        gridButtons[i]:Hide()
    end

    -- Update labels
    slotLabel:SetText(SLOT_NAMES[slot] or ("Slot " .. slot))
    slotLabel:SetTextColor(C_WHITE[1], C_WHITE[2], C_WHITE[3])
    countLabel:SetText(#items .. " appearances")

    UpdateGridSelection()
end

-- ================================================================
--  BOTTOM BAR: Cost + Action Buttons
-- ================================================================
local bottomBar = CreateFrame("Frame", nil, f)
bottomBar:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", rightX, 8)
bottomBar:SetPoint("BOTTOMRIGHT", f, "BOTTOMRIGHT", -8, 8)
bottomBar:SetHeight(38)

local costLabel = bottomBar:CreateFontString(nil, "OVERLAY", "GameFontNormal")
costLabel:SetPoint("LEFT", bottomBar, "LEFT", 8, 0)
costLabel:SetText("")

-- Apply button
local applyBtn = CreateFrame("Button", "TransmogUIApply", bottomBar, "UIPanelButtonTemplate")
applyBtn:SetSize(80, 24)
applyBtn:SetPoint("RIGHT", bottomBar, "RIGHT", -8, 0)
applyBtn:SetText("Apply")
applyBtn:Disable()
applyBtn:SetScript("OnClick", function()
    if selectedSlot and selectedAppearance then
        SendChatMessage(".transmog apply " .. selectedSlot .. " " .. selectedAppearance, "SAY")
    end
end)

-- Remove button
local removeBtn = CreateFrame("Button", "TransmogUIRemove", bottomBar, "UIPanelButtonTemplate")
removeBtn:SetSize(80, 24)
removeBtn:SetPoint("RIGHT", applyBtn, "LEFT", -6, 0)
removeBtn:SetText("Remove")
removeBtn:Disable()
removeBtn:SetScript("OnClick", function()
    if selectedSlot then
        SendChatMessage(".transmog unapply " .. selectedSlot, "SAY")
    end
end)

-- Remove All button (left side of bottom bar)
local removeAllBtn = CreateFrame("Button", "TransmogUIRemoveAll", f, "UIPanelButtonTemplate")
removeAllBtn:SetSize(90, 20)
removeAllBtn:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 12, 12)
removeAllBtn:SetText("Remove All")
removeAllBtn:SetScript("OnClick", function()
    SendChatMessage(".transmog unapplyall", "SAY")
end)

function UpdateActionButtons()
    if selectedSlot and selectedAppearance then
        applyBtn:Enable()
        costLabel:SetText("Cost: " .. FormatMoney(slotCost))
    else
        applyBtn:Disable()
        if selectedSlot then
            costLabel:SetText("Cost: " .. FormatMoney(slotCost))
        else
            costLabel:SetText("")
        end
    end

    if selectedSlot then
        local data = slotData[selectedSlot]
        if data and data.fakeEntry and data.fakeEntry > 0 then
            removeBtn:Enable()
        else
            removeBtn:Disable()
        end

    else
        removeBtn:Disable()
    end
end

-- ================================================================
--  STATUS MESSAGE (overlays the grid briefly)
-- ================================================================
local statusText = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
statusText:SetPoint("CENTER", scrollFrame, "CENTER", 0, 0)
statusText:SetText("")
statusText:Hide()

local statusTimer = 0
local function ShowStatus(msg, color, duration)
    statusText:SetText(msg)
    statusText:SetTextColor(color[1], color[2], color[3])
    statusText:Show()
    statusTimer = duration or 2.0
end

f:HookScript("OnUpdate", function(self, elapsed)
    if statusTimer > 0 then
        statusTimer = statusTimer - elapsed
        if statusTimer <= 0 then
            statusText:Hide()
        end
    end
end)

-- ================================================================
--  PRESET PANEL (dropdown-style, bottom-left area)
-- ================================================================
-- Preset UI is kept minimal: a dropdown + save/load/delete
local presetContainer = CreateFrame("Frame", nil, f)
presetContainer:SetPoint("BOTTOMLEFT", f, "BOTTOMLEFT", 8, 36)
presetContainer:SetSize(LEFT_WIDTH - 10, 22)

local presetLabel = presetContainer:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
presetLabel:SetPoint("LEFT", presetContainer, "LEFT", 2, 0)
presetLabel:SetText("Presets:")
presetLabel:SetTextColor(C_LABEL[1], C_LABEL[2], C_LABEL[3])

local saveSetBtn = CreateFrame("Button", nil, presetContainer, "UIPanelButtonTemplate")
saveSetBtn:SetSize(48, 18)
saveSetBtn:SetPoint("RIGHT", presetContainer, "RIGHT", 0, 0)
saveSetBtn:SetText("Save")
saveSetBtn:SetScript("OnClick", function()
    StaticPopup_Show("TRANSMOG_SAVE_PRESET")
end)

local loadSetBtn = CreateFrame("Button", nil, presetContainer, "UIPanelButtonTemplate")
loadSetBtn:SetSize(48, 18)
loadSetBtn:SetPoint("RIGHT", saveSetBtn, "LEFT", -4, 0)
loadSetBtn:SetText("Load")
loadSetBtn:SetScript("OnClick", function()
    -- Simple: load preset 0 (first one)
    -- TODO: Add a dropdown for preset selection
    local first = nil
    for id, _ in pairs(presets) do
        if not first or id < first then first = id end
    end
    if first then
        SendChatMessage(".transmog loadset " .. first, "SAY")
    end
end)

-- Save preset popup
StaticPopupDialogs["TRANSMOG_SAVE_PRESET"] = {
    text = "Enter a name for this preset:",
    button1 = "Save",
    button2 = "Cancel",
    hasEditBox = true,
    maxLetters = 24,
    OnAccept = function(self)
        local name = self.editBox:GetText()
        if name and name ~= "" then
            SendChatMessage(".transmog saveset " .. name, "SAY")
        end
    end,
    timeout = 0,
    whileDead = true,
    hideOnEscape = true,
    preferredIndex = 3,
}

-- ================================================================
--  MESSAGE HANDLING
-- ================================================================
local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("CHAT_MSG_ADDON")
-- Note: GET_ITEM_INFO_RECEIVED does not exist in 3.3.5a (added in 5.4).
-- We use an OnUpdate poller instead to pick up newly-cached item info.

local function OnAddonMessage(prefix, msg, channel, sender)
    if prefix ~= ADDON_PREFIX then return end

    local msgType = msg:sub(1, 1)

    if msgType == "H" then
        -- Config: H|allowHidden|hiddenIsFree|useCollection
        local _, allowHidden, hiddenFree, useCollection = strsplit("|", msg)
        config.allowHidden = (allowHidden == "1")
        config.hiddenIsFree = (hiddenFree == "1")
        config.useCollection = (useCollection == "1")

    elseif msgType == "S" then
        -- Slot data: S|slot|itemId|fakeEntry
        local _, slotStr, itemIdStr, fakeStr = strsplit("|", msg)
        local slot = tonumber(slotStr)
        local itemId = tonumber(itemIdStr)
        local fakeEntry = tonumber(fakeStr)
        if slot then
            slotData[slot] = { itemId = itemId or 0, fakeEntry = fakeEntry or 0 }
            -- Pre-cache item info
            if itemId and itemId > 0 then ForceCache(itemId) end
            if fakeEntry and fakeEntry > 1 then ForceCache(fakeEntry) end
        end

    elseif msgType == "I" then
        -- Appearance: I|slot|itemId|quality
        local _, slotStr, itemIdStr, qualityStr = strsplit("|", msg)
        local slot = tonumber(slotStr)
        local itemId = tonumber(itemIdStr)
        local quality = tonumber(qualityStr) or 1
        if slot and itemId then
            if not appearances[slot] then appearances[slot] = {} end
            table.insert(appearances[slot], { itemId = itemId, quality = quality })
            -- Pre-cache
            ForceCache(itemId)
        end

    elseif msgType == "F" then
        -- End of appearances: F|slot|totalItems|cost
        local _, slotStr, totalStr, costStr = strsplit("|", msg)
        local slot = tonumber(slotStr)
        slotTotal = tonumber(totalStr) or 0
        slotCost = tonumber(costStr) or 0
        if slot then
            PopulateGrid(slot)
            UpdateActionButtons()
        end

    elseif msgType == "P" then
        -- Preset: P|presetId|name|slot1:entry1|slot2:entry2|...
        local parts = { strsplit("|", msg) }
        local presetId = tonumber(parts[2])
        local name = parts[3] or ""
        if presetId then
            presets[presetId] = { name = name, slots = {} }
            for i = 4, #parts do
                local s, e = strsplit(":", parts[i])
                local sl = tonumber(s)
                local en = tonumber(e)
                if sl and en then
                    presets[presetId].slots[sl] = en
                end
            end
        end

    elseif msgType == "R" then
        -- Result: R|resultCode|slot|newFakeEntry
        local _, codeStr, slotStr, fakeStr = strsplit("|", msg)
        local code = tonumber(codeStr) or 0
        local slot = tonumber(slotStr)
        local newFake = tonumber(fakeStr) or 0

        if code == 0 then
            -- Success
            if slot and slotData[slot] then
                slotData[slot].fakeEntry = newFake
            end
            selectedAppearance = nil
            PlaySound(1204)  -- SOUNDKIT.GS_CHARACTER_CREATION_CLASS
            ShowStatus("Transmogrification complete!", C_SUCCESS, 2.0)
            RefreshModel()
            UpdateSlotIcons()
            UpdateSlotHighlights()
            UpdateActionButtons()
        else
            PlaySound(847)   -- SOUNDKIT.igQuestFailed
            local errorMsg = "Transmogrification failed."
            if code == 11106 then errorMsg = "Not enough gold!" end
            if code == 11108 then errorMsg = "No transmogrification to remove." end
            ShowStatus(errorMsg, C_ERROR, 2.5)
        end

    elseif msgType == "E" then
        -- End of init data -- show the frame
        selectedSlot = nil
        selectedAppearance = nil
        slotLabel:SetText("Select an equipment slot")
        countLabel:SetText("")
        costLabel:SetText("")
        applyBtn:Disable()
        removeBtn:Disable()
        searchBox:SetText("")

        -- Clear appearance data
        for k in pairs(appearances) do appearances[k] = nil end
        -- Hide all grid buttons
        for _, btn in pairs(gridButtons) do btn:Hide() end

        UpdateSlotIcons()
        UpdateSlotHighlights()
        UpdateActionButtons()
        f:Show()
    end
end

-- 3.3.5a poller: retry GetItemInfo on pending items every 0.25s
local POLL_INTERVAL = 0.25
local pollElapsed = 0

eventFrame:SetScript("OnUpdate", function(self, elapsed)
    if not f:IsShown() then return end
    pollElapsed = pollElapsed + elapsed
    if pollElapsed < POLL_INTERVAL then return end
    pollElapsed = 0

    local anyResolved = false
    for itemId in pairs(pendingItemInfo) do
        local _, _, _, _, _, _, _, _, _, texPath = GetItemInfo(itemId)
        if texPath then
            pendingItemInfo[itemId] = nil
            anyResolved = true
            for _, btn in pairs(gridButtons) do
                if btn:IsShown() and btn.itemId == itemId then
                    btn.icon:SetTexture(texPath)
                end
            end
        end
    end
    if anyResolved then
        UpdateSlotIcons()
    end
end)

eventFrame:SetScript("OnEvent", function(self, event, ...)
    if event == "CHAT_MSG_ADDON" then
        OnAddonMessage(...)
    end
end)

-- ================================================================
--  CLEAR STATE ON HIDE
-- ================================================================
f:SetScript("OnHide", function()
    selectedSlot = nil
    selectedAppearance = nil
    for k in pairs(appearances) do appearances[k] = nil end
    for k in pairs(slotData) do slotData[k] = nil end
    for k in pairs(presets) do presets[k] = nil end
    for _, btn in pairs(gridButtons) do btn:Hide() end
    pendingItemInfo = {}
end)

-- ================================================================
--  SLASH COMMAND (manual open for testing)
-- ================================================================
SLASH_TRANSMOGUI1 = "/tmog"
SlashCmdList["TRANSMOGUI"] = function()
    SendChatMessage(".transmog ui", "SAY")
end
