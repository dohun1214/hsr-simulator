"""행동 순서 / Action Value 스케줄러.

모든 근거는 docs/mechanics.md 1장 참고.

핵심 설계: **AV 가 아니라 Action Gauge(AG) 를 상태로 저장한다.**

    AV_남은시간 = AG / SPD
    1 AV 경과   -> AG -= SPD
    행동 종료   -> AG = 10000

AV 를 직접 저장하면 턴 도중 SPD 가 변할 때 남은 시간을 어떻게 환산할지
임의로 정해야 한다. AG 를 저장하면 게임 내부 동작과 동일하게 자동 재계산된다.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..entities.unit import ACTION_GAUGE_FULL, Unit

#: 첫 번째 사이클 길이 (AV). 근거: docs/mechanics.md 1.6
FIRST_CYCLE_AV = 150.0
#: 이후 사이클 길이 (AV)
CYCLE_AV = 100.0

#: 부동소수 오차로 순서가 흔들리는 것을 막기 위한 동점 판정 폭.
AV_EPSILON = 1e-9


def base_action_value(spd: float) -> float:
    """SPD 로부터 기본 Action Value. 근거: docs/mechanics.md 1.1"""
    return ACTION_GAUGE_FULL / max(spd, 1e-9)


def action_value(unit: Unit) -> float:
    """이 유닛의 다음 턴까지 남은 AV."""
    return unit.action_gauge / unit.spd


def reset_gauge(unit: Unit, ratio: float = 1.0) -> None:
    """행동을 마친 유닛의 게이지를 되돌린다. 근거: docs/mechanics.md 1.2

    ``ratio`` 는 게임 데이터의 DelayRatio 로, 1보다 크면 다음 턴이 늦게 온다
    (docs/mechanics.md 7.5). 기본값 1.0 이면 기존 동작과 같다.
    """
    unit.action_gauge = ACTION_GAUGE_FULL * max(0.0, ratio)


def modify_gauge(unit: Unit, advance: float = 0.0, delay: float = 0.0) -> None:
    """행동 앞당기기 / 늦추기.

        New AG = max(0, AG - 10000 * (advance - delay))

    근거: docs/mechanics.md 1.5.
    ``advance`` / ``delay`` 는 비율 (25% -> 0.25).
    """
    unit.action_gauge = max(0.0, unit.action_gauge - ACTION_GAUGE_FULL * (advance - delay))


def force_immediate_action(unit: Unit) -> None:
    """'즉시 행동' 효과: 비율이 아니라 AG 를 0 으로 강제 설정. 근거: docs/mechanics.md 1.5"""
    unit.action_gauge = 0.0


def cycle_of(elapsed_av: float) -> int:
    """누적 AV 로부터 현재 사이클 번호(1부터).

    첫 사이클 150 AV, 이후 100 AV. 근거: docs/mechanics.md 1.6
    """
    if elapsed_av < FIRST_CYCLE_AV - AV_EPSILON:
        return 1
    return 2 + int((elapsed_av - FIRST_CYCLE_AV + AV_EPSILON) // CYCLE_AV)


def advance_time(units: List[Unit], delta_av: float) -> None:
    """시간을 delta_av 만큼 흘린다: 각 유닛의 AG 에서 (SPD x delta_av) 를 뺀다."""
    if delta_av <= 0.0:
        return
    for unit in units:
        if not unit.alive:
            continue
        unit.action_gauge = max(0.0, unit.action_gauge - unit.spd * delta_av)


def pick_next_actor(
    units: List[Unit],
    tie_break_order: List[str],
) -> Optional[Tuple[Unit, float]]:
    """다음에 행동할 유닛과, 그때까지 흘러야 하는 AV 를 반환.

    동점 처리는 **미확인 규칙**이다 (docs/mechanics.md 1.7).
    여기서는 ``tie_break_order`` (기본: 아군 파티 순서 -> 적 순서) 를 사용해
    최소한 **결정론**을 보장한다. 실제 게임과의 일치는 향후 실측 검증 대상.
    """
    best: Optional[Tuple[float, int, Unit]] = None
    for unit in units:
        if not unit.alive:
            continue
        av = action_value(unit)
        try:
            rank = tie_break_order.index(unit.uid)
        except ValueError:
            rank = len(tie_break_order)
        if best is None:
            best = (av, rank, unit)
            continue
        if av < best[0] - AV_EPSILON:
            best = (av, rank, unit)
        elif abs(av - best[0]) <= AV_EPSILON and rank < best[1]:
            best = (av, rank, unit)
    if best is None:
        return None
    return best[2], best[0]
