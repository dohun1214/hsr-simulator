"""데미지 공식 테스트. 근거: docs/mechanics.md 2장

모든 기대값은 손계산으로 검증한다.
"""

import pytest

from hsr_sim.battle.damage import (
    DamageContext,
    compute_damage,
    damage_step_names,
    default_base_def,
)
from hsr_sim.core.enums import CritMode, DamageTag, Element, ScalingStat, Side
from hsr_sim.core.rng import RngState
from hsr_sim.entities.unit import Unit
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def attacker(level=80, atk=1000.0, crit_rate=0.0, crit_dmg=0.5):
    return Unit(
        uid="A1", definition_id="a", side=Side.ALLY, slot=0, level=level,
        base_stats={
            Stat.MAX_HP: 1000.0, Stat.ATK: atk, Stat.DEF: 500.0, Stat.SPD: 100.0,
            Stat.CRIT_RATE: crit_rate, Stat.CRIT_DMG: crit_dmg,
        },
        current_hp=1000.0,
    )


def defender(level=80, defense=1000.0, weaknesses=(Element.PHYSICAL,), toughness=60.0):
    """적 1체. 인성치 게이지를 가지므로 미격파 상태에서 10% 범용 피해 감소가 적용된다."""
    return Unit(
        uid="E1", definition_id="e", side=Side.ENEMY, slot=0, level=level,
        base_stats={Stat.MAX_HP: 10000.0, Stat.ATK: 500.0, Stat.DEF: defense, Stat.SPD: 90.0},
        current_hp=10000.0,
        weaknesses=frozenset(weaknesses),
        max_toughness=toughness,
        current_toughness=toughness,
    )


def ctx_of(atk_unit, def_unit, **kwargs):
    kwargs.setdefault("element", Element.PHYSICAL)
    kwargs.setdefault("multiplier", 1.0)
    return DamageContext(attacker=atk_unit, defender=def_unit,
                         tags=(DamageTag.BASIC_ATK,), **kwargs)


def test_pipeline_contains_all_documented_steps():
    assert damage_step_names() == [
        "dmg_boost", "weaken", "def", "res", "vulnerability",
        "mitigation", "broken", "extra",
    ]


def test_default_base_def_formula():
    assert default_base_def(80) == 1000.0
    assert default_base_def(1) == 210.0


def test_basic_damage_hand_calculation():
    """base 1000 x DEF 0.5 x RES 1.0 x broken 0.9 = 450"""
    result = compute_damage(ctx_of(attacker(), defender()), crit_mode=CritMode.NEVER)
    assert result.breakdown["def"] == pytest.approx(0.5)
    assert result.breakdown["res"] == pytest.approx(1.0)
    assert result.breakdown["broken"] == pytest.approx(0.9)
    assert result.amount == pytest.approx(450.0)


def test_non_weakness_element_applies_20_percent_res():
    """DEF 800 -> 1 - 800/1800 = 5/9,  RES 0.2 -> 0.8,  broken 0.9
    1000 x 5/9 x 0.8 x 0.9 = 400
    """
    target = defender(defense=800.0, weaknesses=(Element.FIRE,))
    result = compute_damage(ctx_of(attacker(), target), crit_mode=CritMode.NEVER)
    assert result.breakdown["res"] == pytest.approx(0.8)
    assert result.amount == pytest.approx(400.0)


def test_broken_target_removes_10_percent_reduction():
    target = defender()
    target.toughness_broken = True
    result = compute_damage(ctx_of(attacker(), target), crit_mode=CritMode.NEVER)
    assert result.breakdown["broken"] == pytest.approx(1.0)
    assert result.amount == pytest.approx(500.0)


def test_crit_modes():
    atk = attacker(crit_rate=0.5, crit_dmg=1.0)
    always = compute_damage(ctx_of(atk, defender()), crit_mode=CritMode.ALWAYS)
    never = compute_damage(ctx_of(atk, defender()), crit_mode=CritMode.NEVER)
    average = compute_damage(ctx_of(atk, defender()), crit_mode=CritMode.AVERAGE)

    assert always.amount == pytest.approx(never.amount * 2.0)
    assert average.amount == pytest.approx(never.amount * 1.5)
    assert always.is_crit is True
    assert never.is_crit is False


def test_crit_rate_is_clamped_to_100_percent():
    atk = attacker(crit_rate=1.5, crit_dmg=1.0)
    result = compute_damage(ctx_of(atk, defender()), crit_mode=CritMode.AVERAGE)
    assert result.breakdown["crit"] == pytest.approx(2.0)


def test_crit_roll_is_deterministic_for_same_seed():
    atk = attacker(crit_rate=0.5, crit_dmg=1.0)
    rolls_a = [
        compute_damage(ctx_of(atk, defender()), CritMode.ROLL, RngState(seed=7, counter=i)).is_crit
        for i in range(20)
    ]
    rolls_b = [
        compute_damage(ctx_of(atk, defender()), CritMode.ROLL, RngState(seed=7, counter=i)).is_crit
        for i in range(20)
    ]
    assert rolls_a == rolls_b
    assert any(rolls_a) and not all(rolls_a)  # 실제로 갈리는지


def test_def_reduction_applies_to_base_def_only():
    """DEF = BaseDEF x (1 + DEF% - 감소 - 무시) + FlatDEF

    감소/무시는 고정 DEF 에는 곱해지지 않는다.
    """
    target = defender(defense=1000.0)
    target.modifiers.append(StatModifier(Stat.DEF, ModifierKind.FLAT, 200.0))
    # 감소 없음: DEF = 1000 + 200 = 1200 -> 1 - 1200/2200
    plain = compute_damage(ctx_of(attacker(), target), crit_mode=CritMode.NEVER)
    assert plain.breakdown["def"] == pytest.approx(1.0 - 1200.0 / 2200.0)

    # 30% 감소: DEF = 1000 x 0.7 + 200 = 900 -> 1 - 900/1900
    reduced = compute_damage(
        ctx_of(attacker(), target, def_reduction=0.3), crit_mode=CritMode.NEVER
    )
    assert reduced.breakdown["def"] == pytest.approx(1.0 - 900.0 / 1900.0)


def test_def_ignore_and_reduction_stack_additively():
    target = defender(defense=1000.0)
    both = compute_damage(
        ctx_of(attacker(), target, def_reduction=0.2, def_ignore=0.2), crit_mode=CritMode.NEVER
    )
    # DEF = 1000 x 0.6 = 600 -> 1 - 600/1600
    assert both.breakdown["def"] == pytest.approx(1.0 - 600.0 / 1600.0)


def test_def_cannot_go_below_zero():
    target = defender(defense=1000.0)
    result = compute_damage(
        ctx_of(attacker(), target, def_reduction=2.0), crit_mode=CritMode.NEVER
    )
    assert result.breakdown["def"] == pytest.approx(1.0)


def test_res_pen_and_clamping():
    target = defender(weaknesses=(Element.FIRE,))  # 물리 저항 20%
    penned = compute_damage(
        ctx_of(attacker(), target, res_pen=0.2), crit_mode=CritMode.NEVER
    )
    assert penned.breakdown["res"] == pytest.approx(1.0)

    # 저항 관통이 과도해도 유효 저항은 -100% 아래로 내려가지 않는다 -> 배수 최대 2.0
    huge = compute_damage(
        ctx_of(attacker(), target, res_pen=5.0), crit_mode=CritMode.NEVER
    )
    assert huge.breakdown["res"] == pytest.approx(2.0)


def test_dmg_bonus_vulnerability_weaken_mitigation():
    target = defender()
    result = compute_damage(
        ctx_of(
            attacker(), target,
            dmg_bonus=0.5, vulnerability=0.2, weaken=0.1, mitigations=[0.1, 0.2],
        ),
        crit_mode=CritMode.NEVER,
    )
    assert result.breakdown["dmg_boost"] == pytest.approx(1.5)
    assert result.breakdown["vulnerability"] == pytest.approx(1.2)
    assert result.breakdown["weaken"] == pytest.approx(0.9)
    assert result.breakdown["mitigation"] == pytest.approx(0.9 * 0.8)
    expected = 1000.0 * 1.5 * 0.9 * 0.5 * 1.0 * 1.2 * (0.9 * 0.8) * 0.9
    assert result.amount == pytest.approx(expected)


def test_def_multiplier_matches_kqm_level_only_form():
    """적 DEF 가 200 + 10 x 레벨 일 때 KQM 의 레벨 기반 식과 일치해야 한다.

    docs/mechanics.md 2.6 의 유도를 코드로 고정한다.
    """
    for atk_level, def_level in [(80, 80), (80, 95), (60, 80), (1, 1)]:
        target = defender(level=def_level, defense=default_base_def(def_level))
        result = compute_damage(
            ctx_of(attacker(level=atk_level), target), crit_mode=CritMode.NEVER
        )
        kqm = (atk_level + 20) / ((def_level + 20) + (atk_level + 20))
        assert result.breakdown["def"] == pytest.approx(kqm)


def test_scaling_stats():
    atk = attacker()
    hp_ctx = ctx_of(atk, defender(), scaling=ScalingStat.MAX_HP, multiplier=0.5)
    result = compute_damage(hp_ctx, crit_mode=CritMode.NEVER)
    assert result.base_damage == pytest.approx(500.0)

    def_ctx = ctx_of(atk, defender(), scaling=ScalingStat.DEF, multiplier=2.0)
    assert compute_damage(def_ctx, crit_mode=CritMode.NEVER).base_damage == pytest.approx(1000.0)


def test_flat_bonus_added_to_base():
    result = compute_damage(
        ctx_of(attacker(), defender(), flat_bonus=250.0), crit_mode=CritMode.NEVER
    )
    assert result.base_damage == pytest.approx(1250.0)


def test_unbroken_reduction_only_applies_to_targets_with_toughness():
    """캐릭터(인성치 없음)는 10% 범용 피해 감소를 받지 않는다."""
    character = defender(weaknesses=(), toughness=0.0)
    character.side = Side.ALLY
    result = compute_damage(ctx_of(attacker(), character), crit_mode=CritMode.NEVER)
    assert result.breakdown["broken"] == pytest.approx(1.0)
    assert result.breakdown["res"] == pytest.approx(1.0)  # 아군은 기본 저항 0%

    enemy = defender(weaknesses=())
    result = compute_damage(ctx_of(attacker(), enemy), crit_mode=CritMode.NEVER)
    assert result.breakdown["broken"] == pytest.approx(0.9)
