/*
 * This file is part of the AzerothCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "Formulas.h"
#include "AreaDefines.h"
#include "Battleground.h"
#include "Creature.h"
#include "Log.h"
#include "Player.h"
#include "ScriptMgr.h"
#include "World.h"
#include <algorithm>

namespace
{
    float GetXPLowLevelRangeMultiplier()
    {
        // The config validator enforces >= 1, but a reload racing a read is
        // cheap to guard against and a multiplier below 1 would narrow the
        // window rather than widen it.
        return std::max(1.0f, sWorld->getFloatConfig(RATE_XP_LOW_LEVEL_RANGE));
    }
}

uint8 Acore::XP::GetXPGrayLevel(uint8 pl_level)
{
    uint8 const grayLevel = GetGrayLevel(pl_level);

    // Below level 6 there is no gray band at all; scaling zero stays zero.
    if (!grayLevel)
        return 0;

    // Widen the band, not the cutoff, and floor it: the band is a whole number
    // of levels, and rounding it up would cost a level of eligible content at
    // every half-step multiplier.
    uint32 const band = static_cast<uint32>(std::floor((pl_level - grayLevel) * GetXPLowLevelRangeMultiplier()));
    if (band >= pl_level)
        return 0;

    return static_cast<uint8>(pl_level - band);
}

uint8 Acore::XP::GetXPZeroDifference(uint8 pl_level)
{
    // Widened in step with the gray band. If it were not, a gray band wider
    // than the zero difference would make BaseGain's falloff factor negative
    // for the mobs the wider band just made eligible.
    float const zeroDiff = GetZeroDifference(pl_level) * GetXPLowLevelRangeMultiplier();
    return static_cast<uint8>(std::min(zeroDiff, 255.0f));
}

uint32 Acore::XP::BaseGain(uint8 pl_level, uint8 mob_level, ContentLevels content)
{
    uint32 baseGain;
    uint32 nBaseExp;

    switch (content)
    {
    case CONTENT_1_60:
        nBaseExp = 45;
        break;
    case CONTENT_61_70:
        nBaseExp = 235;
        break;
    case CONTENT_71_80:
        nBaseExp = 580;
        break;
    default:
        LOG_ERROR("misc", "BaseGain: Unsupported content level {}", content);
        nBaseExp = 45;
        break;
    }

    if (mob_level >= pl_level)
    {
        uint8 nLevelDiff = mob_level - pl_level;
        if (nLevelDiff > 4)
            nLevelDiff = 4;

        baseGain = ((pl_level * 5 + nBaseExp) * (20 + nLevelDiff) / 10 + 1) / 2;
    }
    else
    {
        uint8 gray_level = GetXPGrayLevel(pl_level);
        if (mob_level > gray_level)
        {
            uint8 ZD = GetXPZeroDifference(pl_level);

            // Signed on purpose: ZD + mob_level - pl_level goes negative once
            // the mob is more than ZD levels down, and the old expression
            // assigned that straight to a uint32.
            int32 falloff = int32(ZD) + int32(mob_level) - int32(pl_level);
            baseGain = falloff > 0 ? uint32(int32(pl_level * 5 + nBaseExp) * falloff / ZD) : 0;
        }
        else
            baseGain = 0;
    }

    //sScriptMgr->OnBaseGainCalculation(baseGain, pl_level, mob_level, content); // pussywizard: optimization
    return baseGain;
}

uint32 Acore::XP::Gain(Player* player, Unit* unit, bool isBattleGround /*= false*/)
{
    Creature* creature = unit->ToCreature();
    uint32 gain = 0;

    if (!creature || (!creature->IsTotem() && !creature->IsPet() && !creature->IsCritter() &&
        !creature->HasFlagsExtra(CREATURE_FLAG_EXTRA_NO_XP)))
    {
        float xpMod = 1.0f;

        uint8 playerLevel = player->GetLevel();
        sScriptMgr->OnPlayerBeforeGetLevelForXPGain(player, playerLevel);
        gain = BaseGain(playerLevel, unit->GetLevel(), GetContentLevelsForMapAndZone(unit->GetMapId(), unit->GetZoneId()));

        if (gain && creature)
        {
            if (creature->isElite())
                xpMod *= 2.0f;

            // Instanced mobs (particularly bosses) oftentimes have higher bonuses, especially in later content levels
            xpMod *= creature->GetCreatureTemplate()->ModExperience;
        }

        if (isBattleGround)
        {
            switch (player->GetMapId())
            {
                case MAP_ALTERAC_VALLEY:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_AV);
                    break;
                case MAP_WARSONG_GULCH:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_WSG);
                    break;
                case MAP_ARATHI_BASIN:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_AB);
                    break;
                case MAP_EYE_OF_THE_STORM:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_EOTS);
                    break;
                case MAP_STRAND_OF_THE_ANCIENTS:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_SOTA);
                    break;
                case MAP_ISLE_OF_CONQUEST:
                    xpMod *= sWorld->getRate(RATE_XP_BG_KILL_IC);
                    break;
            }
        }
        else
        {
            xpMod *= sWorld->getRate(RATE_XP_KILL);
        }

        // if players dealt less than 50% of the damage and were credited anyway (due to CREATURE_FLAG_EXTRA_NO_PLAYER_DAMAGE_REQ), scale XP gained appropriately (linear scaling)
        if (creature && creature->GetPlayerDamageReq())
        {
            xpMod *= 1.0f - 2.0f * creature->GetPlayerDamageReq() / creature->GetMaxHealth();
        }

        gain = uint32(gain * xpMod);
    }

    //sScriptMgr->OnGainCalculation(gain, player, u); // pussywizard: optimization
    return gain;
}
