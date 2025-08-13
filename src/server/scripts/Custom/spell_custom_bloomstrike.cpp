/*
 * This file is part of the AzerothCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU Affero General Public License as published by the
 * Free Software Foundation; either version 3 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"
#include "SpellScriptLoader.h"

enum CustomDruidSpells
{
    SPELL_DRUID_BLOOMSTRIKE_R1 = 17111,
    SPELL_DRUID_BLOOMSTRIKE_R2 = 17112,
    SPELL_DRUID_BLOOMSTRIKE_R3 = 17113,
    SPELL_DRUID_BLOOMSTRIKE_DAMAGE_EFFECT = 200000
};

class spell_dru_bloomstrike : public AuraScript
{
    PrepareAuraScript(spell_dru_bloomstrike);

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return eventInfo.GetActionTarget() && eventInfo.GetActionTarget()->IsAlive() && eventInfo.GetActor();
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        Unit* caster = eventInfo.GetActor();
        if (!caster)
            return;

        uint32 activeHots = 0;
        if (caster->GetAuraEffect(SPELL_AURA_PERIODIC_HEAL, SPELLFAMILY_DRUID, 0x00000040, 0, 0, caster->GetGUID())) // Rejuvenation
            activeHots++;
        if (caster->GetAuraEffect(SPELL_AURA_PERIODIC_HEAL, SPELLFAMILY_DRUID, 0x00000800, 0, 0, caster->GetGUID())) // Regrowth
            activeHots++;
        if (caster->GetAuraEffect(SPELL_AURA_PERIODIC_HEAL, SPELLFAMILY_DRUID, 0x00000000, 0x00000002, 0, caster->GetGUID())) // Lifebloom
            activeHots++;
        if (caster->GetAuraEffect(SPELL_AURA_PERIODIC_HEAL, SPELLFAMILY_DRUID, 0x00000000, 0x00000000, 0x00000008, caster->GetGUID())) // Wild Growth
            activeHots++;

        if (activeHots == 0)
            return;

        int32 damage = 0;
        if (eventInfo.GetDamageInfo())
            damage = eventInfo.GetDamageInfo()->GetDamage();

        int32 bonusDamage = CalculatePct(damage, aurEff->GetAmount() * activeHots);

        if (caster->IsPlayer())
        {
            int32 spellPower = caster->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_NATURE);
            bonusDamage += (spellPower * activeHots * 0.5); // 50% spell power scaling per HoT
        }

        caster->CastCustomSpell(eventInfo.GetActionTarget(), SPELL_DRUID_BLOOMSTRIKE_DAMAGE_EFFECT, &bonusDamage, nullptr, nullptr, true, nullptr, aurEff);
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_dru_bloomstrike::CheckProc);
        OnEffectProc += AuraEffectProcFn(spell_dru_bloomstrike::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

void AddSC_custom_bloomstrike_scripts()
{
    RegisterSpellScript(spell_dru_bloomstrike);
}
