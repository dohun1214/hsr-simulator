"""결정론과 상태 복제 테스트.

요구사항: 동일 상태 + 동일 행동 -> 동일 결과, 그리고 미래 상태 탐색이 원본을 훼손하지 않을 것.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle.actions import BasicAttackAction
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def build(seed=99, crit=CritMode.ROLL, log=False):
    config = BattleConfig(seed=seed, crit_mode=crit, log_enabled=log)
    state = build_battle(
        definitions("test_ally_a", "test_ally_b"),
        definitions("test_enemy_a", "test_enemy_b"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def snapshot(state):
    return (
        state.outcome,
        state.turn_count,
        round(state.elapsed_av, 9),
        tuple(round(u.current_hp, 9) for u in state.all_units()),
        state.rng.counter,
    )


def test_same_seed_gives_identical_battles():
    results = []
    for _ in range(3):
        engine, state = build()
        engine.run(state)
        results.append(snapshot(state))
    assert results[0] == results[1] == results[2]


def test_different_seed_changes_rng_dependent_battle():
    engine_a, state_a = build(seed=1)
    engine_a.run(state_a)
    engine_b, state_b = build(seed=2)
    engine_b.run(state_b)
    assert snapshot(state_a) != snapshot(state_b)


def test_clone_is_independent():
    engine, state = build()
    clone = state.clone()
    clone.unit("E1").current_hp = 1.0
    clone.unit("A1").modifiers.append(
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 1.0)
    )
    clone.unit("A1").extra["flag"] = True
    clone.extra["x"] = 1
    clone.order.append("ghost")

    assert state.unit("E1").current_hp != 1.0
    assert state.unit("A1").modifiers == []
    assert "flag" not in state.unit("A1").extra
    assert "x" not in state.extra
    assert "ghost" not in state.order


def test_simulate_does_not_mutate_original():
    engine, state = build(crit=CritMode.NEVER)
    before = snapshot(state)
    future = engine.simulate(state)
    assert snapshot(state) == before
    assert snapshot(future) != before


def test_simulate_same_action_twice_gives_same_future():
    engine, state = build(crit=CritMode.NEVER)
    engine.advance_to_next_turn(state)
    action = BasicAttackAction(actor_uid=state.active_uid, target_uid="E1")

    a = state.clone()
    b = state.clone()
    engine.perform(a, action)
    engine.perform(b, action)
    assert snapshot(a) == snapshot(b)


def test_branching_search_from_one_state():
    """하나의 상태에서 가능한 모든 행동으로 분기해 서로 다른 미래를 만든다."""
    engine, state = build(crit=CritMode.NEVER)
    engine.advance_to_next_turn(state)
    actions = engine.legal_actions(state)
    # 적 2체 x (일반 공격 + 전투 스킬)
    assert len(actions) == 4
    actions = [a for a in actions if type(a).__name__ == "BasicAttackAction"]
    assert len(actions) == 2

    futures = []
    for action in actions:
        branch = state.clone()
        engine.perform(branch, action)
        engine.end_turn(branch)
        futures.append(branch)

    damaged = [
        {u.uid for u in f.all_units() if u.current_hp < u.max_hp} for f in futures
    ]
    assert damaged[0] != damaged[1]
    # 원본은 그대로
    assert all(u.current_hp == u.max_hp for u in state.all_units())


def test_rng_state_travels_with_clone():
    engine, state = build()
    state.rng.random()
    clone = state.clone()
    assert clone.rng.counter == state.rng.counter
    assert clone.rng.random() == state.rng.random()
