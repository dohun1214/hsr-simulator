"""어그로(도발치)와 적의 대상 선택.

근거: docs/mechanics.md 6장.

적의 공격 대상은 완전 무작위가 아니라 **운명의 길에 따른 기본 어그로에 비례**한다.

    노려질 확률 = 자신의 어그로 / 살아 있는 아군 어그로 총합
    어그로       = 기본 어그로 x (1 + 수정자 합)

두 번째 식이 우리 스탯 계산식과 동일하므로 어그로를 `Stat.AGGRO` 로 두었다.
덕분에 도발/어그로 감소가 **기존 버프·디버프 시스템으로 그대로 표현**된다.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from ..core.enums import Path
from ..entities.unit import Unit
from ..stats.stat import Stat

#: 운명의 길별 기본 어그로. 근거: docs/mechanics.md 6.1 (3개 자료 교차검증)
PATH_BASE_AGGRO: Dict[Path, float] = {
    Path.PRESERVATION: 150.0,
    Path.DESTRUCTION: 125.0,
    Path.HARMONY: 100.0,
    Path.NIHILITY: 100.0,
    Path.ABUNDANCE: 100.0,
    Path.REMEMBRANCE: 100.0,
    Path.HUNT: 75.0,
    Path.ERUDITION: 75.0,
}

#: 운명의 길이 없는 개체(대부분의 적)의 기본값.
#: 어그로는 캐릭터를 노리는 규칙이므로 적끼리는 의미가 없고, 균등 선택이 되도록 둔다.
DEFAULT_BASE_AGGRO = 100.0


def base_aggro_for(path: Optional[Path], override: Optional[float] = None) -> float:
    if override is not None:
        return override
    if path is None:
        return DEFAULT_BASE_AGGRO
    return PATH_BASE_AGGRO.get(path, DEFAULT_BASE_AGGRO)


def aggro_of(unit: Unit) -> float:
    """현재 어그로 = 기본값 x (1 + 수정자 합). 음수는 0 으로 막는다."""
    return max(0.0, unit.stat(Stat.AGGRO))


def target_weights(candidates: Sequence[Unit]) -> Dict[str, float]:
    """후보별 선택 확률. 근거: docs/mechanics.md 6.2"""
    living = [u for u in candidates if u.alive]
    weights = {u.uid: aggro_of(u) for u in living}
    total = sum(weights.values())
    if total <= 0.0:
        # 전원 어그로 0 이면 균등 분배 (0으로 나누는 것을 막기 위한 안전장치)
        if not living:
            return {}
        share = 1.0 / len(living)
        return {u.uid: share for u in living}
    return {uid: value / total for uid, value in weights.items()}


def _weighted_pick(candidates: Sequence[Unit], rng) -> Optional[Unit]:
    """어그로 가중 추첨.

    결정론을 위해 후보를 (슬롯, uid) 로 정렬한 뒤 누적 확률로 고른다.
    """
    living = sorted((u for u in candidates if u.alive), key=lambda u: (u.slot, u.uid))
    if not living:
        return None
    weights = [aggro_of(u) for u in living]
    total = sum(weights)
    if total <= 0.0:
        return living[rng.randrange(len(living))]
    roll = rng.random() * total
    cumulative = 0.0
    for unit, weight in zip(living, weights):
        cumulative += weight
        if roll < cumulative:
            return unit
    return living[-1]


def select_target(
    state,
    candidates: Sequence[Unit],
    selection: str = "aggro",
) -> Optional[Unit]:
    """자동 행동에서 주 대상을 고른다.

    ``selection`` 은 스킬의 `TargetRule.selection` 값이다 (docs/mechanics.md 6.4).
    """
    living = [u for u in candidates if u.alive]
    if not living:
        return None
    if selection == "uniform":
        pool = sorted(living, key=lambda u: (u.slot, u.uid))
        return pool[state.rng.randrange(len(pool))]
    if selection == "lowest_hp":
        return min(living, key=lambda u: (u.hp_ratio, u.slot, u.uid))
    if selection == "highest_hp":
        return max(living, key=lambda u: (u.hp_ratio, -u.slot))
    return _weighted_pick(living, state.rng)
