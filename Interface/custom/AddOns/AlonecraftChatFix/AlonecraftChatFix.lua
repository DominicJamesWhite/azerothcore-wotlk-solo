-- Alonecraft Chat Fix
--
-- ChatFrame.lua's CHANNEL_NOTICE / CHANNEL_NOTICE_USER branches look up
-- _G["CHAT_"..arg1.."_NOTICE"] and pass it straight to format(). The server's
-- ChatNotify enum (Channel.h) contains types the 3.3.5a client has no global
-- string for -- MODE_CHANGE (0x0C) and NOT_IN_LFG (0x21) -- so the lookup
-- returns nil and format() throws:
--   ChatFrame.lua:2802: bad argument #1 to 'format' (string expected, got nil)
--
-- MODE_CHANGE is broadcast by Channel::SetOwner whenever channel ownership or
-- moderator flags change, which happens constantly while playerbot / llm-chatter
-- bots join and leave the channels we are in. The notice carries no text a player
-- needs, so we drop any notice we cannot format.

local AlonecraftChatFix = {}
_G.AlonecraftChatFix = AlonecraftChatFix

-- Set to true (or /run AlonecraftChatFix.debug = true) to log which notice types
-- are being dropped instead of silently swallowing them.
AlonecraftChatFix.debug = false

local reported = {}

local function HasFormatString(notice)
    if type(notice) ~= "string" then
        return false
    end
    return _G["CHAT_" .. notice .. "_NOTICE_BN"] ~= nil
        or _G["CHAT_" .. notice .. "_NOTICE"] ~= nil
end

local function Filter(_, _, arg1)
    if HasFormatString(arg1) then
        return false
    end

    if AlonecraftChatFix.debug and not reported[tostring(arg1)] then
        reported[tostring(arg1)] = true
        DEFAULT_CHAT_FRAME:AddMessage(
            "|cff44ddffAlonecraftChatFix|r: dropped unknown channel notice '"
                .. tostring(arg1) .. "'", 1, 1, 1)
    end

    return true
end

ChatFrame_AddMessageEventFilter("CHAT_MSG_CHANNEL_NOTICE", Filter)
ChatFrame_AddMessageEventFilter("CHAT_MSG_CHANNEL_NOTICE_USER", Filter)
