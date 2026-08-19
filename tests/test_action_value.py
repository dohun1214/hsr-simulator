"""Action Value / Action Gauge / 사이클 테스트.

근거: docs/mechanics.md 1장
"""

import math

import pytest

from hsr_sim.battle import scheduler
from hsr_sim.entities.unit import ACTION_GAUGE_FULL, Unit
from hsr_sim.core.enums import Side
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def make_unit(uid, spd, slot=0, side=Side.ALLY):
    return Unit(
        uid=uid,
        definition_id="x",
        side=side,
        slot=slot,
        base_stats={Stat.MAX_HP: 100.0, Stat.SPD: spd},
        current_hp=100.0,
    )


def test_base_action_value_is_10000_over_spd():
    assert scheduler.base_action_value(100.0) == pytest.approx(100.0)
    assert scheduler.base_action_value(134.0) == pytest.approx(10000.0 / 134.0)
    assert scheduler.base_action_value(160.0) == pytest.approx(62.5)


def test_unit_starts_with_full_gauge():
    unit = make_unit("A1", 100.0)
    assert unit.action_gauge == ACTION_GAUGE_FULL
    assert scheduler.action_value(unit) == pytest.approx(100.0)


def test_advance_time_subtracts_spd_per_av():
    """1 AV 가 지날 때마다 AG 에서 SPD 만큼 빠진다."""
    unit = make_unit("A1", 134.0)
    scheduler.advance_time([unit], 10.0)
    assert unit.action_gauge == pytest.approx(10000.0 - 1340.0)
    assert scheduler.action_value(unit) == pytest.approx((10000.0 - 1340.0) / 134.0)


def test_gauge_reset_after_turn():
    unit = make_unit("A1", 100.0)
    scheduler.advance_time([unit], 50.0)
    scheduler.reset_gauge(unit)
    assert unit.action_gauge == ACTION_GAUGE_FULL


def test_dead_units_do_not_consume_time():
    alive = make_unit("A1", 100.0)
    dead = make_unit("A2", 100.0)
    dead.alive = False
    scheduler.advance_time([alive, dead], 10.0)
    assert dead.action_gauge == ACTION_GAUGE_FULL
    assert alive.action_gauge == pytest.approx(9000.0)


def test_action_advance_uses_gauge_formula():
    """New AG = max(0, AG - 10000 * (advance - delay))"""
    unit = make_unit("A1", 100.0)
    scheduler.modify_gauge(unit, advance=0.25)
    assert unit.action_gauge == pytest.approx(7500.0)
    assert scheduler.action_value(unit) == pytest.approx(75.0)


def test_action_delay_pushes_gauge_up():
    unit = make_unit("A1", 100.0)
    scheduler.advance_time([unit], 50.0)  # AG 5000
    scheduler.modify_gauge(unit, delay=0.30)
    assert unit.action_gauge == pytest.approx(8000.0)


def test_action_advance_clamped_at_zero():
    unit = make_unit("A1", 100.0)
    scheduler.modify_gauge(unit, advance=2.0)
    assert unit.action_gauge == 0.0


def test_force_immediate_action_sets_gauge_to_zero():
    unit = make_unit("A1", 100.0)
    scheduler.advance_time([unit], 10.0)
    scheduler.force_immediate_action(unit)
    assert unit.action_gauge == 0.0
    assert scheduler.action_value(unit) == 0.0


def test_spd_buff_midflight_rescales_remaining_av():
    """AG 를 저장하기 때문에, 턴 도중 SPD 가 오르면 남은 AV 가 자동으로 줄어든다.

    AV 를 직접 저장했다면 이 동작을 임의 규칙으로 정해야 했을 것이다.
    """
    unit = make_unit("A1", 100.0)
    scheduler.advance_time([unit], 50.0)  # AG 5000, 남은 AV 50
    assert scheduler.action_value(unit) == pytest.approx(50.0)

    unit.modifiers.append(StatModifier(Stat.SPD, ModifierKind.PERCENT_OF_BASE, 0.25))
    assert unit.spd == pytest.approx(125.0)
    assert scheduler.action_value(unit) == pytest.approx(40.0)


def test_cycle_boundaries():
    """첫 사이클 150 AV, 이후 100 AV."""
    assert scheduler.cycle_of(0.0) == 1
    assert scheduler.cycle_of(149.9) == 1
    assert scheduler.cycle_of(150.0) == 2
    assert scheduler.cycle_of(249.9) == 2
    assert scheduler.cycle_of(250.0) == 3
    assert scheduler.cycle_of(350.0) == 4
    assert scheduler.cycle_of(1050.0) == 11
