"""상태 효과 (버프 / 디버프 / 지속 피해).

규칙과 근거는 docs/mechanics.md 5장.

설계 요점

- `StatusEffect` 인스턴스는 유닛에 붙는 **순수 데이터**다 (효과 id, 중첩, 남은 턴).
- 실제 내용(중첩 상한, 스탯 수정자, DoT 설정)은 `STATUS_EFFECTS` 레지스트리의 정의에만 있다.
- 스탯 수정자는 효과가 바뀔 때마다 `source_id="effect:..."` 로 다시 만들어 유닛에 반영한다.
  덕분에 `Unit.stat()` 은 레지스트리를 몰라도 되고, BattleState 는 계속 순수 데이터로 남는다.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..core.enums import (
    CritMode,
    DamageTag,
    DebuffKind,
    DurationTiming,
    EffectCategory,
    RefreshPolicy,
    ScalingStat,
)
from ..core.events import DotTick, StatusApplied, StatusRemoved, StatusResisted
from ..entities.unit import StatusEffect, Unit
from ..registries import STATUS_EFFECTS
from ..stats.stat import Stat, StatModifier

#: 효과가 만들어낸 스탯 수정자를 구분하기 위한 접두사
EFFECT_MODIFIER_PREFIX = "effect:"


def definition_of(effect_id: str):
    return STATUS_EFFECTS.get(effect_id)


# ---------------------------------------------------------------------------
# 스탯 수정자 동기화
# ---------------------------------------------------------------------------


def rebuild_effect_modifiers(unit: Unit) -> None:
    """유닛의 상태 효과로부터 스탯 수정자를 다시 만든다.

    효과가 붙거나 떨어지거나 중첩이 변할 때마다 호출한다.
    (효과 목록이 진실의 원본이고 수정자는 파생물)
    """
    unit.modifiers = [
        m for m in unit.modifiers if not m.source_id.startswith(EFFECT_MODIFIER_PREFIX)
    ]
    for effect in unit.effects:
        definition = STATUS_EFFECTS.try_get(effect.effect_id)
        if definition is None:
            continue
        for template in definition.stat_modifiers:
            unit.modifiers.append(
                StatModifier(
                    stat=template.stat,
                    kind=template.kind,
                    value=template.value * effect.stacks,
                    source_id=f"{EFFECT_MODIFIER_PREFIX}{effect.effect_id}",
                    stack_key=effect.effect_id,
                )
            )


# ---------------------------------------------------------------------------
# 적용 확률
# ---------------------------------------------------------------------------


def debuff_resistance(target: Unit, effect_id: str) -> float:
    """대상의 이 효과에 대한 개별 저항.

    게임 데이터의 `DebuffResist` 는 효과 id 가 아니라 **태그** 단위다
    (`STAT_CTRL`, `STAT_CTRL_Frozen`, `STAT_DOT_Burn` ...). docs/mechanics.md 7.6

    효과에 붙은 태그들과 효과 id 자체를 모두 조회하고 **가장 큰 값**을 쓴다.
    합산인지 최댓값인지는 **[미확인]**.
    """
    if not target.debuff_res:
        return 0.0
    definition = STATUS_EFFECTS.try_get(effect_id)
    keys = [effect_id]
    if definition is not None:
        keys.extend(definition.resist_tags)
    return max((target.debuff_res.get(k, 0.0) for k in keys), default=0.0)


def application_chance(source: Optional[Unit], target: Unit, effect_id: str, base_chance: float) -> float:
    """디버프 적용 확률.

        실제 확률 = 기본 확률 x (1 + 효과 명중) x (1 - 효과 저항) x (1 - 디버프 저항)

    근거: docs/mechanics.md 5.4 (부분 확인). 최종 확률은 1.0 으로 상한.
    """
    ehr = source.stat(Stat.EFFECT_HIT_RATE) if source is not None else 0.0
    effect_res = target.stat(Stat.EFFECT_RES)
    debuff_res = debuff_resistance(target, effect_id)
    chance = base_chance * (1.0 + ehr) * (1.0 - effect_res) * (1.0 - debuff_res)
    return min(max(chance, 0.0), 1.0)


# ---------------------------------------------------------------------------
# 부여 / 제거
# ---------------------------------------------------------------------------


def dot_base_per_stack(engine, source: Optional[Unit], target: Unit, dot) -> float:
    """DoT 1중첩당 기본 피해.

    일반 DoT 는 시전자의 스탯에 배율을 곱한다.
    격파 효과는 기준이 다르다 — 격파 기본 피해(공격자 레벨) 또는 **대상**의 최대 HP다.
    docs/mechanics.md 5.6 / 8.6
    """
    from . import toughness

    if dot.scaling is ScalingStat.BREAK_BASE:
        if source is None:
            return 0.0
        table = getattr(engine.config, "break_base_damage_table", None)
        value = dot.multiplier * toughness.break_base_damage(source.level, table)
    elif dot.scaling is ScalingStat.TARGET_MAX_HP:
        multiplier = dot.multiplier
        if dot.elite_multiplier is not None and toughness.is_elite(target):
            multiplier = dot.elite_multiplier
        value = multiplier * target.max_hp
    elif source is None:
        return 0.0
    elif dot.scaling is ScalingStat.ATK:
        value = dot.multiplier * source.stat(Stat.ATK)
    elif dot.scaling is ScalingStat.DEF:
        value = dot.multiplier * source.stat(Stat.DEF)
    else:
        value = dot.multiplier * source.stat(Stat.MAX_HP)

    if dot.use_toughness_multiplier:
        value *= toughness.max_toughness_multiplier(target)

    # 상한은 격파 특효를 곱하기 **전**의 기본 피해에 걸린다 (열상)
    if dot.cap_break_multiplier is not None and source is not None:
        table = getattr(engine.config, "break_base_damage_table", None)
        cap = (
            dot.cap_break_multiplier
            * toughness.break_base_damage(source.level, table)
            * toughness.max_toughness_multiplier(target)
        )
        value = min(value, cap)

    if dot.use_break_effect and source is not None:
        value *= 1.0 + source.stat(Stat.BREAK_EFFECT)
    return value


def _dot_snapshot(engine, state, source: Optional[Unit], target: Unit, definition):
    """DoT 부여 시점의 시전자 정보를 고정한다. docs/mechanics.md 5.6"""
    if definition.dot is None or source is None:
        return None
    return {
        "base_per_stack": dot_base_per_stack(engine, source, target, definition.dot),
        "level": float(source.level),
        "dmg_bonus": 0.0,
    }


def apply_effect(
    engine,
    state,
    target: Unit,
    effect_id: str,
    source: Optional[Unit] = None,
    duration: Optional[int] = None,
    stacks: int = 1,
) -> bool:
    """판정 없이 상태 효과를 부여/갱신한다. 실제로 변화가 있었으면 True."""
    if not target.alive:
        return False
    definition = definition_of(effect_id)
    duration = definition.base_duration if duration is None else duration

    existing = target.effect(effect_id)
    if existing is None:
        state.effect_seq += 1
        effect = StatusEffect(
            effect_id=effect_id,
            source_uid=source.uid if source is not None else "",
            stacks=min(stacks, definition.max_stacks),
            remaining_turns=duration,
            applied_seq=state.effect_seq,
            snapshot=_dot_snapshot(engine, state, source, target, definition)
            if state_uses_snapshot(engine)
            else None,
        )
        target.effects.append(effect)
    else:
        policy = definition.refresh
        if policy is RefreshPolicy.IGNORE:
            return False
        if policy in (RefreshPolicy.STACK, RefreshPolicy.STACK_AND_REFRESH):
            existing.stacks = min(existing.stacks + stacks, definition.max_stacks)
        if policy in (RefreshPolicy.REFRESH, RefreshPolicy.STACK_AND_REFRESH):
            existing.remaining_turns = duration
        if source is not None:
            existing.source_uid = source.uid
            if state_uses_snapshot(engine):
                existing.snapshot = _dot_snapshot(engine, state, source, target, definition)

    rebuild_effect_modifiers(target)
    effect = target.effect(effect_id)
    state.log.add(
        state.elapsed_av, state.cycle, "status",
        f"{target.uid} <- {definition.name} ({effect.stacks}중첩, {effect.remaining_turns}턴)",
        uid=target.uid, effect_id=effect_id,
    )
    engine.bus.emit(
        engine, state,
        StatusApplied(
            uid=target.uid,
            effect_id=effect_id,
            stacks=effect.stacks,
            source_uid=effect.source_uid,
        ),
    )
    return True


def state_uses_snapshot(engine) -> bool:
    return getattr(engine.config, "dot_snapshot", True)


def try_apply_effect(
    engine,
    state,
    target: Unit,
    effect_id: str,
    source: Optional[Unit] = None,
    base_chance: float = 1.0,
    duration: Optional[int] = None,
    stacks: int = 1,
) -> bool:
    """확률 판정을 거쳐 상태 효과를 부여한다.

    버프는 판정하지 않는다 (docs/mechanics.md 5.4).
    """
    definition = definition_of(effect_id)
    if definition.category is not EffectCategory.DEBUFF:
        return apply_effect(engine, state, target, effect_id, source, duration, stacks)

    chance = application_chance(source, target, effect_id, base_chance)
    if chance < 1.0 and state.rng.random() >= chance:
        state.log.add(
            state.elapsed_av, state.cycle, "status",
            f"{target.uid} 가 {definition.name} 저항 (확률 {chance:.1%})",
            uid=target.uid, effect_id=effect_id,
        )
        engine.bus.emit(
            engine, state, StatusResisted(uid=target.uid, effect_id=effect_id, chance=chance)
        )
        return False
    return apply_effect(engine, state, target, effect_id, source, duration, stacks)


def remove_effect(engine, state, unit: Unit, effect_id: str, reason: str = "") -> bool:
    effect = unit.effect(effect_id)
    if effect is None:
        return False
    unit.effects.remove(effect)
    rebuild_effect_modifiers(unit)
    state.log.add(
        state.elapsed_av, state.cycle, "status",
        f"{unit.uid} 의 {definition_of(effect_id).name} 해제" + (f" ({reason})" if reason else ""),
        uid=unit.uid, effect_id=effect_id,
    )
    engine.bus.emit(engine, state, StatusRemoved(uid=unit.uid, effect_id=effect_id, reason=reason))
    return True


def cleanse(engine, state, unit: Unit, category: EffectCategory, count: int = 1) -> int:
    """해제 가능한 효과를 오래된 것부터 제거한다. 근거: docs/mechanics.md 5.2"""
    removable = [
        e
        for e in sorted(unit.effects, key=lambda e: e.applied_seq)
        if STATUS_EFFECTS.get(e.effect_id).category is category
        and STATUS_EFFECTS.get(e.effect_id).removable
    ]
    removed = 0
    for effect in removable[:count]:
        if remove_effect(engine, state, unit, effect.effect_id, reason="해제"):
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# 행동 불능
# ---------------------------------------------------------------------------


def is_action_blocked(unit: Unit) -> bool:
    """행동 불능(CC) 디버프가 걸려 있는가.

    V0.3 은 "주 행동을 하지 못한다"까지만 구현한다.
    빙결의 추가 피해, 부여 시 행동 지연 같은 개별 규칙은 아직 미구현.
    """
    for effect in unit.effects:
        definition = STATUS_EFFECTS.try_get(effect.effect_id)
        if definition is not None and definition.debuff_kind is DebuffKind.CROWD_CONTROL:
            return True
    return False


# ---------------------------------------------------------------------------
# 턴 진행 훅
# ---------------------------------------------------------------------------


def _tick_dots(engine, state, unit: Unit) -> None:
    """대상의 턴 시작 시 지속 피해를 부여 순서대로 발동한다.

    근거: docs/mechanics.md 5.6 (발동 시점, 처리 순서, 치명타 불가)
    """
    from .damage import DamageContext

    dots = [
        e
        for e in unit.effects
        if (STATUS_EFFECTS.try_get(e.effect_id) or None) is not None
        and STATUS_EFFECTS.get(e.effect_id).dot is not None
    ]
    for effect in sorted(dots, key=lambda e: e.applied_seq):
        if not unit.alive:
            return
        definition = STATUS_EFFECTS.get(effect.effect_id)
        dot = definition.dot
        source = state.units.get(effect.source_uid)
        stacks = effect.stacks if dot.per_stack else 1

        if effect.snapshot is not None:
            base = effect.snapshot["base_per_stack"] * stacks
            level = int(effect.snapshot["level"])
            dmg_bonus = effect.snapshot["dmg_bonus"]
        elif source is not None:
            base = dot_base_per_stack(engine, source, unit, dot) * stacks
            level = source.level
            dmg_bonus = 0.0
        else:
            continue

        ctx = DamageContext(
            attacker=source if source is not None else unit,
            defender=unit,
            element=dot.element,
            multiplier=0.0,
            tags=(DamageTag.DOT,),
            skill_id=effect.effect_id,
            dmg_bonus=dmg_bonus,
            base_damage_override=base,
            attacker_level_override=level,
        )
        result = engine.deal_damage(state, ctx, crit_mode=CritMode.NEVER)
        engine.bus.emit(
            engine, state,
            DotTick(uid=unit.uid, effect_id=effect.effect_id, amount=result.amount),
        )


def _decrement(engine, state, unit: Unit, timing: DurationTiming) -> None:
    expired: List[str] = []
    for effect in unit.effects:
        definition = STATUS_EFFECTS.try_get(effect.effect_id)
        if definition is None or definition.duration_timing is not timing:
            continue
        if effect.remaining_turns < 0:
            continue  # 무한 지속
        effect.remaining_turns -= 1
        if effect.remaining_turns <= 0:
            expired.append(effect.effect_id)
    for effect_id in expired:
        remove_effect(engine, state, unit, effect_id, reason="지속시간 종료")
        _on_expire(engine, state, unit, effect_id)


def _on_expire(engine, state, unit: Unit, effect_id: str) -> None:
    """효과가 지속시간을 다 채우고 끝날 때의 부수 효과.

    빙결이 그렇다. 게임 데이터의 빙결 정의는 소유자의 턴에
    `ModifyCurrentSkillDelayCost = Set 0.5` 를 한다 — 행동을 못 한 대신
    다음 턴 진입 비용이 1.0 이 아니라 0.5 가 된다. docs/mechanics.md 8.6

    효과별로 코드를 늘리지 않으려고 정의의 `extra` 로 데이터화했다.
    해제(dispel)로 사라질 때는 호출되지 않는다 — 게임도 소유자의 턴에만 처리한다.
    """
    from ..entities.unit import ACTION_GAUGE_FULL

    definition = STATUS_EFFECTS.try_get(effect_id)
    if definition is None:
        return
    ratio = definition.extra.get("expire_action_gauge")
    if ratio is None:
        return
    unit.action_gauge = ACTION_GAUGE_FULL * float(ratio)
    state.log.add(
        state.elapsed_av, state.cycle, "status",
        f"{unit.uid} {definition.name} 해제 -> 행동 게이지 {float(ratio):.0%}",
        uid=unit.uid, effect_id=effect_id,
    )


def on_turn_start(engine, state, unit: Unit) -> None:
    _tick_dots(engine, state, unit)
    if unit.alive:
        _decrement(engine, state, unit, DurationTiming.OWNER_TURN_START)


def on_turn_end(engine, state, unit: Unit) -> None:
    _decrement(engine, state, unit, DurationTiming.OWNER_TURN_END)
