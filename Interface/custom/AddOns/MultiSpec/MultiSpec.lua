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

-- Cached spec icons: specIconCache[specNum] = texture path
-- Cached talent distributions: specDistCache[specNum] = "X/Y/Z"
-- Cached spec names: specNameCache[specNum] = "Holy", "Arms", etc.
-- All persisted via SavedVariablesPerCharacter
local specIconCache = {}
local specDistCache = {}
local specNameCache = {}

-- ============================================================
-- Spec tabs
-- ============================================================
local specTabs = {}
local initialized = false

local function SendCommand(cmd)
    SendChatMessage(cmd, "SAY")
end

-- Suppress MULTISPEC responses from appearing in chat
ChatFrame_AddMessageEventFilter("CHAT_MSG_SYSTEM", function(self, event, msg, ...)
    if msg and msg:match("^MULTISPEC[_%w]*:") then
        return true
    end
end)

-- Get the name and icon for a talent tree tab (class-wide, independent of spec)
local function GetTreeInfo(tabIndex)
    local name, iconTexture = GetTalentTabInfo(tabIndex, false, false, 1)
    return name, iconTexture
end

-- ============================================================
-- Detect dominant talent tree icon for a spec
-- ============================================================
local function CacheSpecIcon(specNum, talentGroup)
    -- Cache talent distribution (e.g., "51/10/10")
    local parts = {}
    local total = 0
    for tab = 1, GetNumTalentTabs() do
        local _, _, pointsSpent = GetTalentTabInfo(tab, false, false, talentGroup)
        local pts = pointsSpent or 0
        parts[tab] = pts
        total = total + pts
    end

    -- Skip empty specs — leave them as question marks
    if total == 0 then return end

    if #parts > 0 then
        local dist = table.concat(parts, "/")
        specDistCache[specNum] = dist
        MultiSpec_SpecDist[specNum] = dist
    end

    local bestTab, bestPoints = 1, parts[1] or 0
    for tab = 2, #parts do
        if parts[tab] > bestPoints then
            bestTab = tab
            bestPoints = parts[tab]
        end
    end

    local name, icon = GetTalentTabInfo(bestTab, false, false, talentGroup)
    if icon then
        specIconCache[specNum] = icon
        MultiSpec_SpecIcons[specNum] = icon
        if specTabs[specNum] then
            specTabs[specNum]:GetNormalTexture():SetTexture(icon)
        end
    end
    if name then
        specNameCache[specNum] = name
        MultiSpec_SpecNames[specNum] = name
    end
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
        local name = specNameCache[specNum] or ("Spec " .. specNum)
        if specNum == realActiveSpec then
            titleText:SetText(name .. " (Active)")
        else
            titleText:SetText(name)
        end
    end

    -- Refresh the talent tree display
    PlayerTalentFrame_Refresh()

    -- Cache the dominant-tree icon for this spec now that talent data is loaded
    CacheSpecIcon(specNum, PlayerTalentFrame.talentGroup)

    -- Button/status state is handled by our PlayerTalentFrame_UpdateControls override

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

    -- Override Blizzard's controls update — it uses its own 2-spec logic
    -- which conflicts with our 8-spec system
    PlayerTalentFrame_UpdateControls = function()
        if not selectedTab then return end
        if selectedTab == realActiveSpec then
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
    end

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
        ntex:SetTexture(specIconCache[i] or "Interface\\Icons\\INV_Misc_QuestionMark")
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

        -- Spec number (hidden, kept for tooltip/state tracking)
        local label = tab:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
        label:SetPoint("CENTER", 0, 0)
        label:SetText(tostring(i))
        label:SetTextColor(1, 0.82, 0)
        label:Hide()
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
            local name = specNameCache[i] or ("Spec " .. i)
            if i == realActiveSpec then
                GameTooltip:AddLine(name .. " (Active)", 0, 1, 0)
            elseif i <= realSpecCount then
                GameTooltip:AddLine(name)
            else
                GameTooltip:AddLine("Spec " .. i .. " (Locked)", 0.5, 0.5, 0.5)
            end
            if specDistCache[i] then
                GameTooltip:AddLine(specDistCache[i], 1, 1, 1)
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

    -- Cache the active spec icon immediately (talent group 1 = active)
    CacheSpecIcon(realActiveSpec, 1)

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
    if event == "ADDON_LOADED" and arg1 == "MultiSpec" then
        -- Load persisted spec icons and distributions
        if not MultiSpec_SpecIcons then
            MultiSpec_SpecIcons = {}
        end
        if not MultiSpec_SpecDist then
            MultiSpec_SpecDist = {}
        end
        if not MultiSpec_SpecNames then
            MultiSpec_SpecNames = {}
        end
        specIconCache = MultiSpec_SpecIcons
        specDistCache = MultiSpec_SpecDist
        specNameCache = MultiSpec_SpecNames
    end
    if event == "ADDON_LOADED" and (arg1 == "Blizzard_TalentUI" or arg1 == "MultiSpec") then
        if PlayerTalentFrame then
            CreateSpecTabs()
        end
    elseif event == "PLAYER_ENTERING_WORLD" then
        -- Server sends MULTISPEC + MULTISPEC_TALENTS on login automatically
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

        -- Parse "MULTISPEC_TALENTS:spec:p1:p2:p3"
        local spec, p1, p2, p3 = arg1:match("^MULTISPEC_TALENTS:(%d+):(%d+):(%d+):(%d+)$")
        if spec then
            local specNum = tonumber(spec)
            p1, p2, p3 = tonumber(p1), tonumber(p2), tonumber(p3)

            -- Cache distribution
            local dist = p1 .. "/" .. p2 .. "/" .. p3
            specDistCache[specNum] = dist
            MultiSpec_SpecDist[specNum] = dist

            -- Derive icon and name from the tree with the most points
            local bestTab, bestPoints = 1, p1
            if p2 > bestPoints then bestTab, bestPoints = 2, p2 end
            if p3 > bestPoints then bestTab = 3 end
            local name, icon = GetTreeInfo(bestTab)
            if icon then
                specIconCache[specNum] = icon
                MultiSpec_SpecIcons[specNum] = icon
                if specTabs[specNum] then
                    specTabs[specNum]:GetNormalTexture():SetTexture(icon)
                end
            end
            if name then
                specNameCache[specNum] = name
                MultiSpec_SpecNames[specNum] = name
            end

            UpdateAllTabs()
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
