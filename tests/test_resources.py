"""스킬 포인트 / 에너지 테스트. 근거: docs/mechanics.md 3~4장"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle.actions import BasicAttackAction, SkillAction
from hsr_sim.battle.resources import change_skill_points, gain_energy
from hsr_sim.core.enums import Side
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def make(allies=("test_ally_a",), enemies=("test_enemy_a",), **kwargs):
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


# --- 스킬 포인트 ----------------------------------------------------------


def test_battle_starts_with_three_skill_points_and_cap_five():
    _, state = make()
    assert state.skill_points == 3
    assert state.max_skill_points == 5


def test_basic_attack_generates_one_skill_point():
    engine, state = make()
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.skill_points == 4


def test_skill_consumes_one_skill_point():
    engine, state = make()
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    assert state.skill_points == 2


def test_skill_points_clamped_at_cap_and_floor():
    engine, state = make()
    assert change_skill_points(engine, state, +10) == 2  # 3 -> 5
    assert state.skill_points == 5
    assert change_skill_points(engine, state, +1) == 0  # 초과분은 버려진다
    assert change_skill_points(engine, state, -10) == -5
    assert state.skill_points == 0


def test_skill_is_not_legal_without_skill_points():
    engine, state = make()
    state.skill_points = 0
    actions = engine.legal_actions(state, "A1")
    assert all(not isinstance(a, SkillAction) for a in actions)
    assert any(isinstance(a, BasicAttackAction) for a in actions)

    state.skill_points = 1
    actions = engine.legal_actions(state, "A1")
    assert any(isinstance(a, SkillAction) for a in actions)


def test_enemies_do_not_touch_skill_points():
    engine, state = make()
    before = state.skill_points
    state.active_uid = "E1"
    engine.perform(state, BasicAttackAction(actor_uid="E1", target_uid="A1"))
    assert state.skill_points == before


# --- 에너지 ---------------------------------------------------------------


def test_units_start_with_zero_energy():
    _, state = make()
    assert state.unit("A1").energy == 0.0
    assert state.unit("A1").max_energy == 120.0
    assert state.unit("E1").max_energy == 0.0  # 적은 에너지를 쓰지 않는다


def test_basic_attack_gives_20_energy_and_skill_30():
    engine, state = make()
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("A1").energy == pytest.approx(20.0)
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("A1").energy == pytest.approx(50.0)


def test_energy_regen_rate_multiplies_action_energy():
    """ERR 은 게임 표기 100% 를 0.0 으로 잡으므로 배수는 1 + stat."""
    engine, state = make()
    state.unit("A1").modifiers.append(
        StatModifier(Stat.ENERGY_REGEN_RATE, ModifierKind.FLAT, 0.2)
    )
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("A1").energy == pytest.approx(24.0)


def test_flat_energy_recovery_ignores_regen_rate():
    """특성/광추의 '에너지 N 회복' 같은 고정 회복에는 ERR 이 적용되지 않는다."""
    engine, state = make()
    unit = state.unit("A1")
    unit.modifiers.append(StatModifier(Stat.ENERGY_REGEN_RATE, ModifierKind.FLAT, 0.5))
    gain_energy(engine, state, unit, 30.0, apply_err=False)
    assert unit.energy == pytest.approx(30.0)
    gain_energy(engine, state, unit, 30.0, apply_err=True)
    assert unit.energy == pytest.approx(30.0 + 45.0)


def test_energy_is_capped_at_max():
    engine, state = make()
    unit = state.unit("A1")
    gain_energy(engine, state, unit, 500.0)
    assert unit.energy == pytest.approx(unit.max_energy)


def test_being_hit_grants_energy_to_the_target():
    engine, state = make()
    state.active_uid = "E1"
    engine.perform(state, BasicAttackAction(actor_uid="E1", target_uid="A1"))
    assert state.unit("A1").energy == pytest.approx(10.0)


def test_defeating_an_enemy_grants_energy_to_the_attacker():
    engine, state = make(enemies=("test_enemy_a", "test_enemy_b"))
    state.unit("E1").current_hp = 1.0
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    # 일반 공격 20 + 처치 10
    assert state.unit("A1").energy == pytest.approx(30.0)


def test_enemies_never_accumulate_energy():
    engine, state = make()
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("E1").energy == 0.0


def test_clone_keeps_resources_independent():
    engine, state = make()
    clone = state.clone()
    clone.skill_points = 0
    clone.unit("A1").energy = 99.0
    assert state.skill_points == 3
    assert state.unit("A1").energy == 0.0
