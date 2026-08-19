"""Action 실행 처리기.

Action(데이터) -> 실제 전투 처리. 새 행동 유형은 여기에 함수를 추가하고
`ACTION_HANDLERS` 에 등록하기만 하면 된다.
"""

from __future__ import annotations

from ..core.enums import DamageTag
from ..registries import ACTION_HANDLERS, UNIT_DEFINITIONS
from .actions import BasicAttackAction, SkipAction
from .damage import DamageContext
from .targeting import resolve_hit_targets


def handle_basic_attack(engine, state, action: BasicAttackAction) -> None:
    actor = state.unit(action.actor_uid)
    target = state.units.get(action.target_uid)
    if target is None or not target.alive:
        return

    definition = UNIT_DEFINITIONS.get(actor.definition_id)
    skill = definition.skills[action.skill_id]
    element = skill.element or definition.element

    for hit_target in resolve_hit_targets(state, actor, target, skill.target_rule):
        if not hit_target.alive:
            continue
        ctx = DamageContext(
            attacker=actor,
            defender=hit_target,
            element=element,
            multiplier=skill.multiplier,
            scaling=skill.scaling,
            flat_bonus=skill.flat_bonus,
            tags=(skill.tag,),
            skill_id=skill.skill_id,
        )
        engine.deal_damage(state, ctx)


def handle_skip(engine, state, action: SkipAction) -> None:
    state.log.add(
        state.elapsed_av, state.cycle, "action", action.describe(), uid=action.actor_uid
    )


ACTION_HANDLERS.register("BasicAttackAction", handle_basic_attack)
ACTION_HANDLERS.register("SkipAction", handle_skip)
