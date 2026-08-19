"""필살기 규칙 테스트. 근거: docs/mechanics.md 4.3

핵심: 필살기는 턴을 소모하지 않고, 자기 턴이 아닐 때도 발동하며, 연쇄 가능하다.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle.actions import BasicAttackAction, UltimateAction
from hsr_sim.battle.engine import never_ultimate_policy
from hsr_sim.battle.resources import gain_energy
from hsr_sim.entities.unit import ACTION_GAUGE_FULL


def make(allies=("test_ally_a",), enemies=("test_enemy_a",), **kwargs):
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def fill(engine, state, uid):
    unit = state.unit(uid)
    gain_energy(engine, state, unit, unit.max_energy)
    return unit


def test_ultimate_unavailable_until_energy_is_full():
    engine, state = make()
    assert engine.available_ultimates(state) == []
    gain_energy(engine, state, state.unit("A1"), 119.0)
    assert engine.available_ultimates(state) == []
    gain_energy(engine, state, state.unit("A1"), 1.0)
    assert len(engine.available_ultimates(state)) == 1


def test_ultimate_consumes_energy_and_grants_five_back():
    engine, state = make()
    fill(engine, state, "A1")
    engine.use_ultimate(state, UltimateAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("A1").energy == pytest.approx(5.0)


def test_ultimate_does_not_consume_a_turn_or_action_gauge():
    engine, state = make()
    fill(engine, state, "A1")
    engine.advance_to_next_turn(state)
    gauge_before = state.unit("A1").action_gauge
    av_before = state.elapsed_av
    turns_before = state.turn_count

    engine.use_ultimate(state, UltimateAction(actor_uid="A1", target_uid="E1"))

    assert state.unit("A1").action_gauge == gauge_before
    assert state.elapsed_av == av_before
    assert state.turn_count == turns_before
    assert state.active_uid == "A1"  # 턴은 그대로 유지된다


def test_ultimate_can_be_used_outside_own_turn():
    engine, state = make(allies=("test_ally_a", "test_ally_b"))
    fill(engine, state, "A1")
    engine.advance_to_next_turn(state)
    assert state.active_uid == "A2"  # A2 가 더 빠르다

    before = state.unit("E1").current_hp
    engine.resolve_ultimates(state)
    assert state.unit("E1").current_hp < before
    assert state.active_uid == "A2"  # A2 의 턴은 그대로


def test_multiple_ultimates_chain():
    engine, state = make(allies=("test_ally_a", "test_ally_b"))
    fill(engine, state, "A1")
    fill(engine, state, "A2")
    used = engine.resolve_ultimates(state)
    assert used == 2
    assert state.unit("A1").energy == pytest.approx(5.0)
    assert state.unit("A2").energy == pytest.approx(5.0)


def test_ultimate_after_turn_still_allows_normal_action_that_turn():
    """자기 턴에 필살기를 써도 그 턴의 일반 공격/스킬은 그대로 할 수 있다."""
    engine, state = make()
    fill(engine, state, "A1")
    engine.advance_to_next_turn(state)
    engine.use_ultimate(state, UltimateAction(actor_uid="A1", target_uid="E1"))
    hp_after_ult = state.unit("E1").current_hp
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.unit("E1").current_hp < hp_after_ult
    engine.end_turn(state)
    assert state.turn_count == 1


def test_never_policy_leaves_energy_untouched():
    engine, state = make()
    fill(engine, state, "A1")
    used = engine.resolve_ultimates(state, never_ultimate_policy)
    assert used == 0
    assert state.unit("A1").energy == pytest.approx(120.0)


def test_auto_policy_is_used_during_run_and_is_deterministic():
    results = []
    for _ in range(2):
        engine, state = make(
            allies=("test_ally_a", "test_ally_b"),
            enemies=("test_enemy_a", "test_enemy_b"),
            seed=5,
        )
        engine.run(state)
        results.append((state.outcome, state.turn_count, state.skill_points))
    assert results[0] == results[1]


def test_dead_unit_cannot_ultimate():
    engine, state = make()
    fill(engine, state, "A1")
    state.unit("A1").alive = False
    assert engine.available_ultimates(state) == []
