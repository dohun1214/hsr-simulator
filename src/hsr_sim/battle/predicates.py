"""AI 조건(Predicate).

게임의 `CheckPredicateAxis` 안에 들어가는 조건들을 데이터로 표현한다.
근거와 실제 등장 빈도는 docs/mechanics.md 7.3.

조건은 **순수 데이터**(`kind` + `params`)이고 판정 함수는 레지스트리에 있다.
새 조건이 필요하면 함수 하나 작성 + 등록으로 끝난다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

from ..core.registry import Registry

#: kind -> fn(state, unit, params) -> bool
PREDICATES: Registry[Callable[..., bool]] = Registry("AI 조건")


@dataclass(frozen=True)
class Predicate:
    """조건 하나. 불변 데이터이므로 정의에 그대로 넣을 수 있다."""

    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    negate: bool = False

    def evaluate(self, state, unit) -> bool:
        fn = PREDICATES.get(self.kind)
        result = bool(fn(state, unit, self.params))
        return (not result) if self.negate else result


def always(state, unit, params) -> bool:
    return True


def phase_is(state, unit, params) -> bool:
    """현재 페이즈가 지정된 값 중 하나인가. (ByCompareMonsterPhase)"""
    return unit.phase in tuple(params.get("phases", ()))


def counter_compare(state, unit, params) -> bool:
    """AI 내부 카운터 비교. (ByCompareDynamicValue)

    params: key, op(">=", "<=", "==", "<", ">"), value
    """
    current = unit.counters.get(params["key"], 0.0)
    target = params.get("value", 0.0)
    op = params.get("op", "==")
    return {
        "==": current == target,
        "!=": current != target,
        ">=": current >= target,
        "<=": current <= target,
        ">": current > target,
        "<": current < target,
    }[op]


def has_effect(state, unit, params) -> bool:
    """자신 또는 지정 진영에 특정 상태 효과가 있는가. (ByIsContainModifier)"""
    effect_id = params["effect_id"]
    scope = params.get("scope", "self")
    if scope == "self":
        return unit.has_effect(effect_id)
    from ..core.enums import Side

    side = Side.ALLY if scope == "ally" else Side.ENEMY
    if scope == "enemies":
        side = unit.side.opposite
    return any(u.has_effect(effect_id) for u in state.living(side))


def living_character_count(state, unit, params) -> bool:
    """살아 있는 상대 진영 인원 수 비교. (ByCompareCharacterNumber)"""
    count = len(state.living(unit.side.opposite))
    target = params.get("value", 0)
    op = params.get("op", "==")
    return {
        "==": count == target,
        "!=": count != target,
        ">=": count >= target,
        "<=": count <= target,
        ">": count > target,
        "<": count < target,
    }[op]


def hp_ratio_below(state, unit, params) -> bool:
    return unit.hp_ratio < params.get("value", 0.5)


def is_toughness_broken(state, unit, params) -> bool:
    return unit.toughness_broken


def all_of(state, unit, params) -> bool:
    """ByAnd"""
    return all(p.evaluate(state, unit) for p in params.get("children", ()))


def any_of(state, unit, params) -> bool:
    """ByAny"""
    return any(p.evaluate(state, unit) for p in params.get("children", ()))


PREDICATES.register("always", always)
PREDICATES.register("phase_is", phase_is)
PREDICATES.register("counter", counter_compare)
PREDICATES.register("has_effect", has_effect)
PREDICATES.register("living_enemies", living_character_count)
PREDICATES.register("hp_below", hp_ratio_below)
PREDICATES.register("is_broken", is_toughness_broken)
PREDICATES.register("all", all_of)
PREDICATES.register("any", any_of)
