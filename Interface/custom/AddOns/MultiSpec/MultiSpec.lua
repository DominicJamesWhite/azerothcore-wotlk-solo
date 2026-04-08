-- MultiSpec: 8-spec talent window for Alonecraft
-- Takes over the Blizzard talent frame to provide seamless 8-spec support.
-- Server sends max 2 specs per packet: slot 0 = active, slot 1 = preview.
-- The addon controls which spec is previewed via .spec preview N.

local MAX_SPECS = 8

-- ============================================================
-- Real spec state (from server MULTISPEC messages)
-- ============================================================
local realActiveSpec = 1   -- 1-based
local realSpecCount = 1
local realPreviewSpec = 1  -- which spec is currently in client slot 1
local selectedTab = nil    -- which of our tabs the user clicked (1-8)

-- ============================================================
-- Spec tabs
-- ============================================================
local specTabs = {}
local initialized = false

local function SendCommand(cmd)
    SendChatMessage(cmd, "SAY")
end

-- ============================================================
-- Tab visual updates
-- ============================================================
local function UpdateAllTabs()
    for i = 1, MAX_SPECS do
        local tab = specTabs[i]
        if not tab then return end

        if i <= realSpecCount then
            tab:Show()

            -- Green number for active, gold for others, bright for selected
            if i == realActiveSpec then
                tab.label:SetTextColor(1, 0.82, 0)
                tab.activeIndicator:Show()
            else
                tab.label:SetTextColor(0.8, 0.8, 0.8)
                tab.activeIndicator:Hide()
            end

            -- Check mark for the currently selected/viewed tab
            tab:SetChecked(i == selectedTab)
        else
            tab:Hide()
        end
    end
end

-- ============================================================
-- Talent frame takeover
-- ============================================================
local function UpdateFrameForSpec(specNum)
    if not PlayerTalentFrame then return end

    selectedTab = specNum

    -- Determine which client slot has this spec's data
    if specNum == realActiveSpec then
        -- Active spec is always in client slot 0 → talentGroup 1
        PlayerTalentFrame.talentGroup = 1
    else
        -- Request the server to put this spec in client slot 1
        -- When the server responds, PLAYER_TALENT_UPDATE fires and we refresh
        if realPreviewSpec ~= specNum then
            SendCommand(".spec preview " .. specNum)
            -- Don't refresh yet — wait for PLAYER_TALENT_UPDATE from server
            UpdateAllTabs()
            return
        end
        -- Preview spec is already loaded in slot 1 → talentGroup 2
        PlayerTalentFrame.talentGroup = 2
    end

    PlayerTalentFrame.pet = false
    PlayerTalentFrame.unit = "player"

    -- Update title
    local titleText = _G["PlayerTalentFrameTitleText"]
    if titleText then
        if specNum == realActiveSpec then
            titleText:SetText("Spec " .. specNum .. " (Active)")
        else
            titleText:SetText("Spec " .. specNum)
        end
    end

    -- Refresh the talent tree display
    PlayerTalentFrame_Refresh()

    -- Show/hide activate button
    if specNum == realActiveSpec then
        PlayerTalentFrameActivateButton:Hide()
        if realSpecCount > 1 then
            PlayerTalentFrameStatusFrame:Show()
            local statusText = _G["PlayerTalentFrameStatusFrameStatusText"]
            if statusText then
                statusText:SetText("This is your active spec")
            end
        else
            PlayerTalentFrameStatusFrame:Hide()
        end
    else
        PlayerTalentFrameActivateButton:Show()
        PlayerTalentFrameStatusFrame:Hide()
    end

    UpdateAllTabs()
end

-- ============================================================
-- Create the spec tabs on the talent frame
-- ============================================================
local function CreateSpecTabs()
    if initialized then return end
    if not PlayerTalentFrame then return end
    initialized = true

    -- Hide Blizzard's spec tabs — we replace them entirely
    if PlayerSpecTab1 then PlayerSpecTab1:Hide(); PlayerSpecTab1.Show = function() end end
    if PlayerSpecTab2 then PlayerSpecTab2:Hide(); PlayerSpecTab2.Show = function() end end
    if PlayerSpecTab3 then PlayerSpecTab3:Hide(); PlayerSpecTab3.Show = function() end end

    for i = 1, MAX_SPECS do
        local tab = CreateFrame("CheckButton", "MultiSpecTab" .. i, PlayerTalentFrame)
        tab:SetWidth(32)
        tab:SetHeight(32)

        -- Background (matches Blizzard skill line tab style)
        local bg = tab:CreateTexture("MultiSpecTab" .. i .. "Background", "BACKGROUND")
        bg:SetTexture("Interface\\SpellBook\\SpellBook-SkillLineTab")
        bg:SetWidth(64)
        bg:SetHeight(64)
        bg:SetPoint("TOPLEFT", tab, "TOPLEFT", -3, 11)

        -- Icon
        local ntex = tab:CreateTexture(nil, "ARTWORK")
        ntex:SetAllPoints()
        ntex:SetTexture("Interface\\Icons\\INV_Misc_QuestionMark")
        tab:SetNormalTexture(ntex)

        -- Checked glow (viewing this spec)
        local ctex = tab:CreateTexture(nil, "ARTWORK")
        ctex:SetTexture("Interface\\Buttons\\CheckButtonHilight")
        ctex:SetBlendMode("ADD")
        ctex:SetAllPoints()
        tab:SetCheckedTexture(ctex)

        -- Hover highlight
        local htex = tab:CreateTexture(nil, "HIGHLIGHT")
        htex:SetTexture("Interface\\Buttons\\ButtonHilight-Square")
        htex:SetBlendMode("ADD")
        htex:SetAllPoints()
        tab:SetHighlightTexture(htex)

        -- Active spec indicator: pushed-out gold tab background (same as Blizzard active spec)
        local activeBg = tab:CreateTexture(nil, "BACKGROUND")
        activeBg:SetTexture("Interface\\TalentFrame\\UI-TalentFrame-SpecTab")
        activeBg:SetWidth(64)
        activeBg:SetHeight(64)
        activeBg:SetPoint("TOPLEFT", tab, "TOPLEFT", -13, 11)
        activeBg:Hide()
        tab.activeIndicator = activeBg

        -- Spec number
        local label = tab:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        label:SetPoint("CENTER", 0, 0)
        label:SetText(tostring(i))
        label:SetTextColor(1, 0.82, 0)
        tab.label = label

        -- Position: stack vertically on the right side of the talent frame
        if i == 1 then
            tab:SetPoint("TOPLEFT", PlayerTalentFrame, "TOPRIGHT", -32, -65)
        else
            tab:SetPoint("TOPLEFT", specTabs[i - 1], "BOTTOMLEFT", 0, -16)
        end

        -- Click: preview this spec
        tab:SetScript("OnClick", function(self)
            PlaySound("igCharacterInfoTab")
            UpdateFrameForSpec(i)
        end)

        -- Tooltip
        tab:SetScript("OnEnter", function(self)
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            if i == realActiveSpec then
                GameTooltip:AddLine("Spec " .. i .. " (Active)", 0, 1, 0)
            elseif i <= realSpecCount then
                GameTooltip:AddLine("Spec " .. i)
                GameTooltip:AddLine("Click to preview", 0.5, 0.5, 0.5)
            else
                GameTooltip:AddLine("Spec " .. i .. " (Locked)", 0.5, 0.5, 0.5)
            end
            GameTooltip:Show()
        end)
        tab:SetScript("OnLeave", function() GameTooltip:Hide() end)

        tab:Hide()
        specTabs[i] = tab
    end

    -- ============================================================
    -- Hook the Activate button
    -- ============================================================
    PlayerTalentFrameActivateButton:SetScript("OnClick", function(self)
        if selectedTab and selectedTab ~= realActiveSpec then
            SendCommand(".spec " .. selectedTab)
        end
    end)

    -- ============================================================
    -- Hook talent frame events
    -- ============================================================
    PlayerTalentFrame:HookScript("OnShow", function()
        -- Query server for real state and select active spec tab
        SendCommand(".spec query")
        selectedTab = realActiveSpec
        UpdateFrameForSpec(realActiveSpec)
    end)

    PlayerTalentFrame:HookScript("OnHide", function()
        selectedTab = nil
    end)

    -- Hook talent update to refresh after server sends new data
    local eventFrame = CreateFrame("Frame")
    eventFrame:RegisterEvent("PLAYER_TALENT_UPDATE")
    eventFrame:SetScript("OnEvent", function()
        if PlayerTalentFrame and PlayerTalentFrame:IsShown() and selectedTab then
            -- Server sent new talent data, refresh our view
            UpdateFrameForSpec(selectedTab)
        end
    end)

    -- Select the active spec on first open
    selectedTab = realActiveSpec
    UpdateAllTabs()
end

-- ============================================================
-- Event handler
-- ============================================================
local loader = CreateFrame("Frame")
loader:RegisterEvent("ADDON_LOADED")
loader:RegisterEvent("PLAYER_ENTERING_WORLD")
loader:RegisterEvent("CHAT_MSG_SYSTEM")

loader:SetScript("OnEvent", function(self, event, arg1)
    if event == "ADDON_LOADED" and (arg1 == "Blizzard_TalentUI" or arg1 == "MultiSpec") then
        if PlayerTalentFrame then
            CreateSpecTabs()
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- Query server for real spec state on login
        SendCommand(".spec query")
        if PlayerTalentFrame then
            CreateSpecTabs()
        end
    elseif event == "CHAT_MSG_SYSTEM" then
        -- Parse "MULTISPEC:active:count:preview"
        local active, count, preview = arg1:match("^MULTISPEC:(%d+):(%d+):(%d+)$")
        if active and count and preview then
            realActiveSpec = tonumber(active)
            realSpecCount = tonumber(count)
            realPreviewSpec = tonumber(preview)
            UpdateAllTabs()
            -- If talent frame is open and we were waiting for preview data, refresh
            if PlayerTalentFrame and PlayerTalentFrame:IsShown() and selectedTab then
                UpdateFrameForSpec(selectedTab)
            end
        end
    end
end)

-- ============================================================
-- Slash commands
-- ============================================================
SLASH_MULTISPEC1 = "/ms"
SLASH_MULTISPEC2 = "/multispec"
SlashCmdList["MULTISPEC"] = function(msg)
    local num = tonumber(msg)
    if num and num >= 1 and num <= MAX_SPECS then
        SendCommand(".spec " .. num)
    else
        DEFAULT_CHAT_FRAME:AddMessage("|cff00ccffMultiSpec:|r /ms <1-" .. MAX_SPECS .. "> to switch specs")
    end
end
