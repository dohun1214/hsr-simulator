"""행동 순서 테스트.

SPD 만으로 결정되는 순서를 손계산과 대조한다.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, build_battle, definitions
from hsr_sim.battle import scheduler
from hsr_sim.core.enums import Side
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier
from hsr_sim.entities.unit import Unit


def turn_sequence(state, engine, count):
    """실제 행동은 하지 않고 스케줄러만 돌려 순서를 뽑는다."""
    order = []
    for _ in range(count):
        uid = engine.advance_to_next_turn(state)
        if uid is None:
            break
        order.append(uid)
        engine.end_turn(state)
    return order


def test_turn_order_matches_hand_calculation():
    """SPD: A1=100, A2=134, E1=90, E2=110

    기본 AV: A2 74.63 < E2 90.91 < A1 100 < E1 111.11
    A2 는 행동 후 149.25 로 이동하므로 4순위 뒤로 간다.
    기대 순서: A2, E2, A1, E1, A2, E2
    """
    config = BattleConfig(log_enabled=False)
    state = build_battle(
        allies=definitions("test_ally_a", "test_ally_b"),
        enemies=definitions("test_enemy_a", "test_enemy_b"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    assert turn_sequence(state, engine, 6) == ["A2", "E2", "A1", "E1", "A2", "E2"]


def test_elapsed_av_matches_hand_calculation():
    config = BattleConfig(log_enabled=False)
    state = build_battle(
        allies=definitions("test_ally_a", "test_ally_b"),
        enemies=definitions("test_enemy_a", "test_enemy_b"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    engine.advance_to_next_turn(state)  # A2 (SPD 134)
    assert state.elapsed_av == pytest.approx(10000.0 / 134.0)
    engine.end_turn(state)

    engine.advance_to_next_turn(state)  # E2 (SPD 110)
    assert state.elapsed_av == pytest.approx(10000.0 / 110.0)
    engine.end_turn(state)


def test_faster_unit_takes_more_turns():
    config = BattleConfig(log_enabled=False)
    state = build_battle(
        allies=definitions("test_ally_a", "test_ally_b"),
        enemies=definitions("test_enemy_a"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    seq = turn_sequence(state, engine, 40)
    assert seq.count("A2") > seq.count("A1") > seq.count("E1")


def test_tie_break_is_deterministic_and_follows_registration_order():
    """동점 규칙은 게임 자료에서 확인되지 않았다 (docs/mechanics.md 1.7).

    우리 구현이 보장하는 것은 '항상 같은 결과'와 '등록 순서 우선' 뿐이다.
    """
    config = BattleConfig(log_enabled=False)
    state = build_battle(
        allies=definitions("test_ally_a"),
        enemies=definitions("test_enemy_a"),
        config=config,
    )
    # 두 유닛의 SPD 를 동일하게 맞춘다
    state.unit("E1").base_stats[Stat.SPD] = state.unit("A1").base_stats[Stat.SPD]

    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    first_runs = []
    for _ in range(3):
        clone = state.clone()
        first_runs.append(turn_sequence(clone, engine, 4))
    assert first_runs[0] == first_runs[1] == first_runs[2]
    assert first_runs[0][0] == "A1"  # 등록 순서상 아군이 먼저


def test_cycle_advances_during_battle():
    config = BattleConfig(log_enabled=False)
    state = build_battle(
        allies=definitions("test_ally_a"),
        enemies=definitions("test_enemy_a"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    assert state.cycle == 1

    turn_sequence(state, engine, 4)  # A1 100, E1 111.11, A1 200, E1 222.22
    assert state.elapsed_av > 150.0
    assert state.cycle == scheduler.cycle_of(state.elapsed_av)
    assert state.cycle >= 2
