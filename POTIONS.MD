# Potion Cooldown Implementation in AzerothCore

This document outlines the implementation of the potion cooldown system in AzerothCore. The system is designed to make potions usable only once per encounter by delaying the cooldown until the player is out of combat.

## Core Logic

The core logic of the potion cooldown system is as follows:

1.  When a player uses a potion, the ID of the potion item is stored.
2.  The system checks if the player is in combat.
3.  If the player is **not** in combat, the cooldown for the potion is triggered immediately.
4.  If the player **is** in combat, the cooldown is not triggered. Instead, the system waits until the player leaves combat.
5.  The cooldown is checked and potentially triggered every time a spell cast finishes. This means that after combat, the next spell cast will trigger the potion cooldown.

## Implementation Details

The implementation is spread across three main files: `Spell.cpp`, `Player.h`, and `PlayerUpdates.cpp`.

### `Spell.cpp`

When a spell is cast from a potion item, `Spell::SendSpellCooldown` is called. This function sets the last used potion ID for the player.

```cpp
// src/server/game/Spells/Spell.cpp

void Spell::SendSpellCooldown()
{
    // ...
    // mana/health/etc potions, disabled by client (until combat out as declarate)
    if (m_CastItem && (m_CastItem->IsPotion() || m_spellInfo->IsCooldownStartedOnEvent()))
    {
        // need in some way provided data for Spell::finish SendCooldownEvent
        _player->SetLastPotionId(m_CastItem->GetEntry());
        return;
    }
    // ...
}
```

When the spell finishes, `Spell::finish` calls `Player::UpdatePotionCooldown`.

```cpp
// src/server/game/Spells/Spell.cpp

void Spell::finish(bool ok)
{
    // ...
    // potions disabled by client, send event "not in combat" if need
    if (m_caster->IsPlayer() && !m_triggeredByAuraSpell)
        m_caster->ToPlayer()->UpdatePotionCooldown(this);
    // ...
}
```

### `Player.h`

The `UpdatePotionCooldown` function is declared in `Player.h`.

```cpp
// src/server/game/Entities/Player/Player.h

class Player : public Unit, public GridObject<Player>
{
    // ...
    void UpdatePotionCooldown(Spell* spell = nullptr);
    // ...
};
```

### `PlayerUpdates.cpp`

The implementation of `UpdatePotionCooldown` is in `PlayerUpdates.cpp`. This function contains the core logic for the potion cooldown system.

```cpp
// src/server/game/Entities/Player/PlayerUpdates.cpp

void Player::UpdatePotionCooldown(Spell* spell)
{
    // no potion used i combat or still in combat
    if (!GetLastPotionId() || IsInCombat())
        return;

    // Call not from spell cast, send cooldown event for item spells if no in
    // combat
    if (!spell)
    {
        // spell/item pair let set proper cooldown (except not existed charged
        // spell cooldown spellmods for potions)
        if (ItemTemplate const* proto =
                sObjectMgr->GetItemTemplate(GetLastPotionId()))
            for (uint8 idx = 0; idx < MAX_ITEM_SPELLS; ++idx)
                if (proto->Spells[idx].SpellId &&
                    proto->Spells[idx].SpellTrigger == ITEM_SPELLTRIGGER_ON_USE)
                    if (SpellInfo const* spellInfo =
                            sSpellMgr->GetSpellInfo(proto->Spells[idx].SpellId))
                        SendCooldownEvent(spellInfo, GetLastPotionId());
    }
    // from spell cases (m_lastPotionId set in Spell::SendSpellCooldown)
    else
    {
        if (spell->IsIgnoringCooldowns())
            return;

        SendCooldownEvent(spell->m_spellInfo, m_lastPotionId, spell);
    }

    SetLastPotionId(0);
}
```

This implementation ensures that potions can only be used once per combat encounter, providing a balanced gameplay mechanic. Any modifications to this system should be done with care to maintain this balance.
