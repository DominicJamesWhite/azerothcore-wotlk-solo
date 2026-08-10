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

#include "DBCStores.h"
#include "Formulas.h"
#include "WorldMock.h"
#include "gtest/gtest.h"

using namespace Acore::Honor;
using namespace Acore::Rage;
using namespace Acore::XP;

TEST(FormulasTest, hk_honor_at_level)
{
    EXPECT_EQ(hk_honor_at_level(80), 124);
    EXPECT_EQ(hk_honor_at_level(80, 2), 248);
    EXPECT_EQ(hk_honor_at_level(80, 0.5), 62);
    EXPECT_EQ(hk_honor_at_level(1), 2);
    EXPECT_EQ(hk_honor_at_level(1, 10), 16);
    EXPECT_EQ(hk_honor_at_level(2), 4);
    EXPECT_EQ(hk_honor_at_level(3), 5);
}

TEST(FormulasTest, GetRageConversion)
{
    EXPECT_NEAR(GetRageConversion(20), 72.42f, 0.01f);
    EXPECT_NEAR(GetRageConversion(40), 147.87f, 0.01f);
    EXPECT_NEAR(GetRageConversion(60), 230.60f, 0.01f);
    EXPECT_NEAR(GetRageConversion(80), 453.32f, 0.01f);

    // The linear tail starts above 70, not at it
    EXPECT_NEAR(GetRageConversion(70), 274.70f, 0.01f);
    EXPECT_NEAR(GetRageConversion(71), 292.48f, 0.01f);
}

TEST(FormulasTest, GetAttackerRage)
{
    float const rc80 = GetRageConversion(80);

    // A 3.6 speed main hand contributes 3.5 * 3.6 = 12.6. Normalized rage
    // is that term alone, so this damage value is where the retail formula
    // and Rage.Normalized agree at level 80. If this moves, every number in
    // the rage balance table moves with it.
    EXPECT_NEAR(GetAttackerRage(762, 12.6f, rc80), 12.6f, 0.05f);

    // Above the break even point the damage term dominates
    EXPECT_NEAR(GetAttackerRage(2000, 12.6f, rc80), 22.85f, 0.05f);

    // Below it, the cap at twice the damage term stops a slow weapon
    // landing a trivial hit from paying out
    EXPECT_NEAR(GetAttackerRage(10, 12.6f, rc80), 0.33f, 0.01f);
}

TEST(FormulasTest, GetGrayLevel)
{
    EXPECT_EQ(GetGrayLevel(0), 0);
    EXPECT_EQ(GetGrayLevel(5), 0);
    EXPECT_EQ(GetGrayLevel(6), 1);
    EXPECT_EQ(GetGrayLevel(39), 31);
    EXPECT_EQ(GetGrayLevel(40), 31);
    EXPECT_EQ(GetGrayLevel(59), 47);
    EXPECT_EQ(GetGrayLevel(60), 51);
    EXPECT_EQ(GetGrayLevel(80), 71);
}

TEST(FormulasTest, GetColorCode)
{
    EXPECT_EQ(GetColorCode(60, 80), XP_RED);
    EXPECT_EQ(GetColorCode(60, 65), XP_RED);
    EXPECT_EQ(GetColorCode(60, 64), XP_ORANGE);
    EXPECT_EQ(GetColorCode(60, 63), XP_ORANGE);
    EXPECT_EQ(GetColorCode(60, 62), XP_YELLOW);
    EXPECT_EQ(GetColorCode(60, 58), XP_YELLOW);
    EXPECT_EQ(GetColorCode(60, 57), XP_GREEN);
    EXPECT_EQ(GetColorCode(60, 52), XP_GREEN);
    EXPECT_EQ(GetColorCode(60, 51), XP_GRAY);
    EXPECT_EQ(GetColorCode(60, 1), XP_GRAY);
}

TEST(FormulasTest, GetZeroDifference)
{
    EXPECT_EQ(GetZeroDifference(1), 5);
    EXPECT_EQ(GetZeroDifference(7), 5);
    EXPECT_EQ(GetZeroDifference(8), 6);
    EXPECT_EQ(GetZeroDifference(9), 6);
    EXPECT_EQ(GetZeroDifference(10), 7);
    EXPECT_EQ(GetZeroDifference(11), 7);
    EXPECT_EQ(GetZeroDifference(12), 8);
    EXPECT_EQ(GetZeroDifference(15), 8);
    EXPECT_EQ(GetZeroDifference(16), 9);
    EXPECT_EQ(GetZeroDifference(19), 9);
    EXPECT_EQ(GetZeroDifference(20), 11);
    EXPECT_EQ(GetZeroDifference(29), 11);
    EXPECT_EQ(GetZeroDifference(30), 12);
    EXPECT_EQ(GetZeroDifference(39), 12);
    EXPECT_EQ(GetZeroDifference(40), 13);
    EXPECT_EQ(GetZeroDifference(44), 13);
    EXPECT_EQ(GetZeroDifference(45), 14);
    EXPECT_EQ(GetZeroDifference(49), 14);
    EXPECT_EQ(GetZeroDifference(50), 15);
    EXPECT_EQ(GetZeroDifference(54), 15);
    EXPECT_EQ(GetZeroDifference(55), 16);
    EXPECT_EQ(GetZeroDifference(59), 16);
    EXPECT_EQ(GetZeroDifference(60), 17);
    EXPECT_EQ(GetZeroDifference(80), 17);
}

// GetXPGrayLevel, GetXPZeroDifference and BaseGain read
// XP.LowLevelRangeMultiplier, so they need a world to read it from.
class XPRangeTest : public ::testing::Test
{
protected:
    void SetUp() override
    {
        _previousWorld = std::move(sWorld);
        _worldMock = new ::testing::NiceMock<WorldMock>();
        SetMultiplier(1.0f);
        sWorld.reset(_worldMock);
    }

    void TearDown() override
    {
        sWorld = std::move(_previousWorld);
    }

    void SetMultiplier(float value)
    {
        ON_CALL(*_worldMock, getFloatConfig(RATE_XP_LOW_LEVEL_RANGE)).WillByDefault(::testing::Return(value));
    }

    std::unique_ptr<IWorld> _previousWorld;
    ::testing::NiceMock<WorldMock>* _worldMock = nullptr;
};

TEST_F(XPRangeTest, BaseGain)
{
    EXPECT_EQ(BaseGain(60, 40, CONTENT_1_60), 0);
    EXPECT_EQ(BaseGain(60, 60, CONTENT_1_60), 345);
    EXPECT_EQ(BaseGain(50, 60, CONTENT_1_60), 354);
    EXPECT_EQ(BaseGain(65, 66, CONTENT_61_70), 588);
    EXPECT_EQ(BaseGain(79, 78, CONTENT_71_80), 917);

    // check outError() has been called after passing an invalid ContentLevels content
    EXPECT_EQ(BaseGain(79, 1, ContentLevels(999)), 0);
}

// At the default multiplier the XP variants must reproduce the retail formulas
// exactly, or every unmodified realm silently changes behaviour.
TEST_F(XPRangeTest, XPVariantsMatchRetailAtDefault)
{
    for (uint8 level = 0; level <= 80; ++level)
    {
        EXPECT_EQ(GetXPGrayLevel(level), GetGrayLevel(level)) << "level " << uint32(level);
        EXPECT_EQ(GetXPZeroDifference(level), GetZeroDifference(level)) << "level " << uint32(level);
    }
}

TEST_F(XPRangeTest, GetXPGrayLevelWidens)
{
    SetMultiplier(1.5f);

    // Band widens, cutoff moves down: level 40 has a 9 level band (40 -> 31),
    // floored to 13 at 1.5x.
    EXPECT_EQ(GetXPGrayLevel(40), 27);
    EXPECT_EQ(GetXPGrayLevel(60), 47);
    EXPECT_EQ(GetXPGrayLevel(80), 67);

    // Levels with no gray band at all keep none.
    EXPECT_EQ(GetXPGrayLevel(0), 0);
    EXPECT_EQ(GetXPGrayLevel(5), 0);

    // A band wider than the player's level saturates at 0 rather than wrapping.
    SetMultiplier(20.0f);
    EXPECT_EQ(GetXPGrayLevel(6), 0);
    EXPECT_EQ(GetXPGrayLevel(80), 0);
}

TEST_F(XPRangeTest, GetXPZeroDifferenceWidens)
{
    SetMultiplier(1.5f);

    EXPECT_EQ(GetXPZeroDifference(40), 19);
    EXPECT_EQ(GetXPZeroDifference(80), 25);

    // uint8 return, so a large multiplier must clamp rather than wrap.
    SetMultiplier(100.0f);
    EXPECT_EQ(GetXPZeroDifference(80), 255);
}

// The old BaseGain assigned a signed falloff to a uint32. With a gray band wide
// enough to admit mobs further down than the zero difference, that underflowed
// to an enormous XP award instead of zero.
TEST_F(XPRangeTest, BaseGainNeverUnderflowsBelowZeroDifference)
{
    SetMultiplier(20.0f);

    // Gray band is saturated at 0, so every mob level is "eligible", but any
    // mob further than the zero difference below the player must still pay 0.
    EXPECT_EQ(GetXPGrayLevel(80), 0);
    for (uint8 mobLevel = 1; mobLevel <= 80 - GetXPZeroDifference(80); ++mobLevel)
        EXPECT_EQ(BaseGain(80, mobLevel, CONTENT_71_80), 0u) << "mob level " << uint32(mobLevel);
}

TEST_F(XPRangeTest, BaseGainWidensRatherThanInflates)
{
    uint32 const onLevel = BaseGain(40, 40, CONTENT_1_60);

    // A mob past the retail gray cutoff pays nothing by default...
    EXPECT_EQ(BaseGain(40, 30, CONTENT_1_60), 0u);

    SetMultiplier(1.5f);

    // ...and pays a reduced amount once the range widens...
    uint32 const widened = BaseGain(40, 30, CONTENT_1_60);
    EXPECT_GT(widened, 0u);
    EXPECT_LT(widened, onLevel);

    // ...without changing what an on-level kill is worth.
    EXPECT_EQ(BaseGain(40, 40, CONTENT_1_60), onLevel);
}

TEST(FormulasTest, Gain)
{
    auto worldMock = new WorldMock();
    sWorld.reset((worldMock));
    /// @todo: create mocks of Player and Creature
    // Gain(nullptr, nullptr);
}
