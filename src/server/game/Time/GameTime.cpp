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

#include "GameTime.h"
#include "Timer.h"

namespace GameTime
{
    using namespace std::chrono;

    Seconds const StartTime = GetEpochTime();

    Seconds GameTime = GetEpochTime();
    Milliseconds GameMSTime = 0ms;

    SystemTimePoint GameTimeSystemPoint = SystemTimePoint::min();
    TimePoint GameTimeSteadyPoint = TimePoint::min();

    Seconds GetStartTime()
    {
        return StartTime;
    }

    Seconds GetGameTime()
    {
        return GameTime;
    }

    Milliseconds GetGameTimeMS()
    {
        return GameMSTime;
    }

    SystemTimePoint GetSystemTime()
    {
        return GameTimeSystemPoint;
    }

    TimePoint Now()
    {
        return GameTimeSteadyPoint;
    }

    Seconds GetUptime()
    {
        return GameTime - StartTime;
    }

    // 0 means "read the OS clock", i.e. every build that is not running --sim.
    uint32 VirtualStepMS = 0;

    void EnableVirtualClock(uint32 stepMs)
    {
        VirtualStepMS = stepMs;

        // Prime the cached points from the real clock, once.
        //
        // Upstream initialises them to *::min() and relies on the first
        // UpdateGameTimers to overwrite them wholesale. The virtual branch only
        // ever *adds* a step, so without this they stay anchored at
        // TimePoint::min() for the life of the process -- and "now" is then
        // about nine billion seconds before the epoch.
        //
        // That is not a cosmetic difference. Aura::m_procCooldown has no
        // initialiser, so it default-constructs to epoch 0, which under a clock
        // running at minus nine quintillion is far in the *future*: every aura
        // that has never had AddProcCooldown called on it reads as permanently
        // on proc cooldown, and Aura::GetProcEffectMask drops it. The result was
        // that most talent procs silently never fired -- Improved Scorch, Ignite
        // and Deep Wounds among them -- while item and enchant procs kept
        // working, because Player.cpp writes those cooldowns explicitly from
        // GameTime::Now(). A fire mage cast Scorch 157 times in two minutes and
        // Fireball not once, because its bot rotation waits for a debuff that
        // could never be applied.
        GameTimeSystemPoint = system_clock::now();
        GameTimeSteadyPoint = steady_clock::now();
        GameTime            = duration_cast<Seconds>(GameTimeSystemPoint.time_since_epoch());
        GameMSTime          = GetTimeMS();
    }

    bool IsVirtualClock()
    {
        return VirtualStepMS != 0;
    }

    void UpdateGameTimers()
    {
        if (VirtualStepMS)
        {
            // The cached points were primed from the real clock during startup,
            // so absolute timestamps captured before the simulator began remain
            // in the past rather than jumping to the epoch.
            Milliseconds const step(VirtualStepMS);

            GameMSTime += step;
            GameTimeSteadyPoint += step;
            GameTimeSystemPoint += step;
            GameTime = duration_cast<Seconds>(GameTimeSystemPoint.time_since_epoch());

            // getMSTime() is not routed through here -- it reads the OS clock
            // directly, and spell cooldowns are compared against it
            // (Player::HasSpellCooldown). Left alone, every cooldown would run
            // at wall-clock speed while the fight ran at 10-40x that, so a
            // 4-second ability came up about once per fight. Publishing the
            // virtual value here is what puts cooldowns on the same clock as
            // everything else.
            VirtualMSTime.store(uint32(GameMSTime.count()), std::memory_order_relaxed);
            return;
        }

        GameTime = GetEpochTime();
        GameMSTime = GetTimeMS();
        GameTimeSystemPoint = system_clock::now();
        GameTimeSteadyPoint = steady_clock::now();
    }
}
