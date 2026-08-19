"""스탯 계산 테스트: 최종값 = 기본 x (1 + %합) + 고정합"""

import pytest

from hsr_sim.stats.stat import (
    ModifierKind,
    Stat,
    StatModifier,
    compute_stat,
    stat_components,
)


def test_percent_modifiers_are_additive():
    mods = [
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.5),
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.3),
    ]
    assert compute_stat(Stat.ATK, 1000.0, mods) == pytest.approx(1800.0)


def test_flat_applied_after_percent():
    mods = [
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.5),
        StatModifier(Stat.ATK, ModifierKind.FLAT, 200.0),
    ]
    assert compute_stat(Stat.ATK, 1000.0, mods) == pytest.approx(1700.0)


def test_modifiers_for_other_stats_ignored():
    mods = [StatModifier(Stat.SPD, ModifierKind.FLAT, 50.0)]
    assert compute_stat(Stat.ATK, 1000.0, mods) == pytest.approx(1000.0)


def test_stat_components_split():
    mods = [
        StatModifier(Stat.DEF, ModifierKind.PERCENT_OF_BASE, 0.2),
        StatModifier(Stat.DEF, ModifierKind.FLAT, 150.0),
    ]
    base, percent, flat = stat_components(Stat.DEF, 800.0, mods)
    assert (base, percent, flat) == pytest.approx((800.0, 0.2, 150.0))
