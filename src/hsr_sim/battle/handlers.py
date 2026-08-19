"""Action 실행 처리기.

Action(데이터) -> 실제 전투 처리. 새 행동 유형은 여기에 함수를 추가하고
`ACTION_HANDLERS` 에 등록하기만 하면 된다.

자원(스킬 포인트/에너지) 규칙의 근거는 docs/mechanics.md 3~4장.
"""

from __future__ import annotations

from typing import List, Optional

from ..core.enums import Side, SkillKind
from ..registries import ACTION_HANDLERS, UNIT_DEFINITIONS
from ..stats.stat import Stat
from .actions import BasicAttackAction, SkillAction, SkipAction, UltimateAction, UseSkillAction
from .damage import DamageContext
from . import status
from .resources import change_skill_points, gain_energy, spend_energy
from .targeting import resolve_hit_targets

#: 적을 쓰러뜨렸을 때 시전자가 얻는 에너지. 근거: docs/mechanics.md 4.1
ENERGY_ON_KILL = 10.0


def _skill_of(actor, skill_id: str):
    definition = UNIT_DEFINITIONS.get(actor.definition_id)
    return definition, definition.skills[skill_id]


def execute_skill(engine, state, action) -> None:
    """일반 공격 / 전투 스킬 / 필살기의 공통 실행 경로.

    세 행동의 차이는 전부 `SkillDefinition` 의 데이터(자원 소모/획득)로 표현되므로
    실행 코드는 하나로 충분하다. 새 행동 유형도 대개 이 함수를 재사용한다.
    """
    actor = state.unit(action.actor_uid)
    if not actor.alive:
        return

    definition, skill = _skill_of(actor, action.skill_id)
    element = skill.element or definition.element

    # 스킬마다 행동 게이지 배수가 다르다 (게임 데이터 DelayRatio). docs/mechanics.md 7.5
    # 필살기는 턴을 소모하지 않으므로 제외한다.
    if skill.kind is not SkillKind.ULTIMATE:
        actor.pending_delay_ratio = skill.delay_ratio

    # --- 자원 소모 -------------------------------------------------------
    if skill.sp_cost and actor.side is Side.ALLY:
        change_skill_points(engine, state, -skill.sp_cost, f"{actor.uid} 스킬 사용")
    if skill.energy_cost:
        spend_energy(engine, state, actor, skill.energy_cost)

    # --- 대상 판정 -------------------------------------------------------
    primary = state.units.get(action.target_uid)
    if primary is None or not primary.alive:
        living = state.living(actor.side.opposite)
        primary = living[0] if living else None
    targets: List = []
    if primary is not None:
        targets = [u for u in resolve_hit_targets(state, actor, primary, skill.target_rule) if u.alive]

    alive_before = {u.uid for u in state.living(actor.side.opposite)}

    # --- 피해 -----------------------------------------------------------
    for target in targets:
        if not target.alive:
            continue
        multiplier = skill.multiplier
        if target.uid != primary.uid and skill.adjacent_multiplier is not None:
            multiplier = skill.adjacent_multiplier
        # 시전자의 피해 증가 = 전 속성 + 해당 속성 (행적/광추/유물에서 온다)
        elemental = (actor.extra.get("elemental_dmg_bonus") or {}).get(
            element.value if element else "", 0.0
        )
        ctx = DamageContext(
            attacker=actor,
            defender=target,
            element=element,
            dmg_bonus=actor.stat(Stat.DMG_BONUS) + elemental,
            multiplier=multiplier,
            scaling=skill.scaling,
            flat_bonus=skill.flat_bonus,
            tags=(skill.tag,),
            skill_id=skill.skill_id,
        )
        engine.deal_damage(state, ctx)
        for effect_id, base_chance in skill.inflicts:
            status.try_apply_effect(
                engine, state, target, effect_id, source=actor, base_chance=base_chance
            )
        if skill.energy_grant_to_target:
            gain_energy(
                engine, state, target, skill.energy_grant_to_target, reason="피격"
            )

    for effect_id in skill.self_effects:
        status.apply_effect(engine, state, actor, effect_id, source=actor)

    # --- 자원 획득 -------------------------------------------------------
    if skill.sp_gain and actor.side is Side.ALLY:
        change_skill_points(engine, state, skill.sp_gain, f"{actor.uid} 일반 공격")
    if skill.energy_gain:
        gain_energy(engine, state, actor, skill.energy_gain, reason=skill.kind.value)

    defeated = alive_before - {u.uid for u in state.living(actor.side.opposite)}
    if defeated:
        gain_energy(
            engine, state, actor, ENERGY_ON_KILL * len(defeated), reason="처치"
        )


def handle_skip(engine, state, action: SkipAction) -> None:
    state.log.add(
        state.elapsed_av, state.cycle, "action", action.describe(), uid=action.actor_uid
    )


ACTION_HANDLERS.register("BasicAttackAction", execute_skill)
ACTION_HANDLERS.register("SkillAction", execute_skill)
ACTION_HANDLERS.register("UltimateAction", execute_skill)
ACTION_HANDLERS.register("UseSkillAction", execute_skill)
ACTION_HANDLERS.register("SkipAction", handle_skip)
