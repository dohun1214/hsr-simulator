"""스킬 포인트 / 에너지 자원 관리.

규칙과 근거는 docs/mechanics.md 3~4장.

자원 변경을 엔진 곳곳에 흩어 두지 않고 여기 모으는 이유:

- 상한/하한 처리와 이벤트 발행을 한 곳에서 보장하기 위해
- 향후 "스킬 포인트를 소모하지 않는 스킬", "에너지 회복 봉인" 같은 효과가
  이 함수들만 후킹하면 되도록 하기 위해
"""

from __future__ import annotations

from ..core.events import EnergyChanged, SkillPointChanged
from ..entities.unit import Unit
from ..stats.stat import Stat


def energy_regen_multiplier(unit: Unit) -> float:
    """에너지 회복 효율 배수.

    게임 표기 100% 를 스탯 0.0 으로 잡으므로 배수는 1 + stat.
    근거: docs/mechanics.md 4.2
    """
    return 1.0 + unit.stat(Stat.ENERGY_REGEN_RATE)


def gain_energy(
    engine,
    state,
    unit: Unit,
    amount: float,
    apply_err: bool = True,
    reason: str = "",
) -> float:
    """에너지를 지급한다. 실제 증가량을 반환.

    ``apply_err=True`` 는 행동으로 얻는 에너지 (일반 공격/스킬/필살기/피격/처치).
    ``apply_err=False`` 는 특성·광추의 "에너지 N 회복" 같은 고정 회복.
    근거: docs/mechanics.md 4.2
    """
    if unit.max_energy <= 0.0 or not unit.alive or amount == 0.0:
        return 0.0
    effective = amount * (energy_regen_multiplier(unit) if apply_err else 1.0)
    before = unit.energy
    after = min(unit.max_energy, max(0.0, before + effective))
    if after == before:
        return 0.0
    unit.energy = after
    state.log.add(
        state.elapsed_av, state.cycle, "energy",
        f"{unit.uid} 에너지 {before:.1f} -> {after:.1f} ({reason})" if reason
        else f"{unit.uid} 에너지 {before:.1f} -> {after:.1f}",
        uid=unit.uid, before=before, after=after,
    )
    engine.bus.emit(engine, state, EnergyChanged(uid=unit.uid, before=before, after=after))
    return after - before


def spend_energy(engine, state, unit: Unit, amount: float) -> None:
    """필살기 사용 등으로 에너지를 소모한다 (ERR 무관)."""
    before = unit.energy
    unit.energy = max(0.0, before - amount)
    engine.bus.emit(engine, state, EnergyChanged(uid=unit.uid, before=before, after=unit.energy))


def change_skill_points(engine, state, delta: int, reason: str = "") -> int:
    """파티 공유 스킬 포인트를 변경한다. 실제 변화량을 반환.

    상한 초과분은 버려진다 (docs/mechanics.md 3.2, [유도됨]).
    """
    if delta == 0:
        return 0
    before = state.skill_points
    after = min(state.max_skill_points, max(0, before + delta))
    if after == before:
        return 0
    state.skill_points = after
    state.log.add(
        state.elapsed_av, state.cycle, "skill_point",
        f"스킬 포인트 {before} -> {after}" + (f" ({reason})" if reason else ""),
        before=before, after=after,
    )
    engine.bus.emit(
        engine, state, SkillPointChanged(before=before, after=after, delta=after - before)
    )
    return after - before


def can_pay_skill_points(state, cost: int) -> bool:
    return cost <= 0 or state.skill_points >= cost
