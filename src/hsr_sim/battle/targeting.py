"""대상 지정 규칙.

V0.1 은 단일 대상만 필요하지만, 확산/전체 공격이 들어올 자리를 미리 만들어 둔다.
"""

from __future__ import annotations

from typing import List

from ..core.enums import Side
from ..entities.definitions import TargetRule
from ..entities.unit import Unit


def candidate_targets(state, actor: Unit, rule: TargetRule) -> List[Unit]:
    """규칙에 맞는 선택 가능한 대상 목록 (생존 유닛만)."""
    if rule.side == "self":
        return [actor] if actor.alive else []
    side = actor.side.opposite if rule.side == "enemy" else actor.side
    return state.living(side)


def resolve_hit_targets(state, actor: Unit, primary: Unit, rule: TargetRule) -> List[Unit]:
    """실제로 타격되는 대상 목록.

    - single : 주 대상만
    - blast  : 주 대상 + 슬롯상 인접 (V0.1 미사용, 자리만 마련)
    - aoe    : 해당 진영 전체
    """
    if rule.shape == "aoe":
        return candidate_targets(state, actor, rule)
    if rule.shape == "blast":
        pool = sorted(candidate_targets(state, actor, rule), key=lambda u: u.slot)
        result = []
        for unit in pool:
            if unit.uid == primary.uid or abs(unit.slot - primary.slot) == 1:
                result.append(unit)
        return result
    return [primary]
