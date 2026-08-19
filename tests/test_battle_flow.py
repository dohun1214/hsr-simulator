"""전투 흐름: 행동 -> HP 감소 -> 사망 -> 전투 종료"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, BattleOutcome, CritMode, build_battle, definitions
from hsr_sim.battle.actions import BasicAttackAction, SkipAction
from hsr_sim.core.enums import Side
from hsr_sim.stats.stat import Stat


def make(allies=("test_ally_a",), enemies=("test_enemy_a",), **kwargs):
    config = BattleConfig(log_enabled=kwargs.pop("log", False), **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def test_units_start_at_full_hp():
    _, state = make()
    for unit in state.all_units():
        assert unit.current_hp == unit.max_hp
        assert unit.alive


def test_basic_attack_reduces_hp_by_expected_amount():
    """A1: ATK 1000, 배율 1.0. E1: DEF 1000, 물리 약점, 미격파.
    1000 x 0.5(DEF) x 1.0(RES) x 0.9(broken) = 450
    """
    engine, state = make(crit_mode=CritMode.NEVER)
    engine.advance_to_next_turn(state)
    state.active_uid = "A1"  # 대상을 고정하기 위해 직접 지정
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    enemy = state.unit("E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(450.0)


def test_legal_actions_lists_one_action_per_living_enemy():
    engine, state = make(enemies=("test_enemy_a", "test_enemy_b"))
    actions = engine.legal_actions(state, "A1")
    assert {a.target_uid for a in actions} == {"E1", "E2"}
    assert all(isinstance(a, BasicAttackAction) for a in actions)

    state.unit("E1").alive = False
    actions = engine.legal_actions(state, "A1")
    assert {a.target_uid for a in actions} == {"E2"}

    # 적 유닛은 아군을 대상으로 삼는다
    enemy_actions = engine.legal_actions(state, "E2")
    assert {a.target_uid for a in enemy_actions} == {"A1"}


def test_unit_dies_at_zero_hp_and_stops_acting():
    engine, state = make(crit_mode=CritMode.NEVER, enemies=("test_enemy_a", "test_enemy_b"))
    target = state.unit("E1")
    target.current_hp = 100.0

    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert target.current_hp == 0.0
    assert target.alive is False

    # 사망한 유닛은 행동 순서에 나타나지 않는다
    seen = set()
    for _ in range(20):
        uid = engine.advance_to_next_turn(state)
        if uid is None:
            break
        seen.add(uid)
        engine.end_turn(state)
    assert "E1" not in seen


def test_hp_cannot_go_below_zero():
    engine, state = make(crit_mode=CritMode.NEVER)
    enemy = state.unit("E1")
    engine.apply_hp_change(state, enemy, -999999.0)
    assert enemy.current_hp == 0.0


def test_victory_when_all_enemies_defeated():
    engine, state = make(crit_mode=CritMode.NEVER)
    state.unit("E1").current_hp = 1.0
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert state.outcome is BattleOutcome.VICTORY
    assert state.is_over


def test_defeat_when_all_allies_defeated():
    engine, state = make(crit_mode=CritMode.NEVER)
    engine.apply_hp_change(state, state.unit("A1"), -99999.0)
    assert state.outcome is BattleOutcome.DEFEAT


def test_no_turns_after_battle_ends():
    engine, state = make(crit_mode=CritMode.NEVER)
    engine.apply_hp_change(state, state.unit("E1"), -99999.0)
    assert engine.advance_to_next_turn(state) is None


def test_full_battle_runs_to_completion():
    engine, state = make(
        allies=("test_ally_a", "test_ally_b"),
        enemies=("test_enemy_a", "test_enemy_b"),
        crit_mode=CritMode.NEVER,
        seed=42,
        log=True,
    )
    outcome = engine.run(state)
    assert outcome in (BattleOutcome.VICTORY, BattleOutcome.DEFEAT, BattleOutcome.DRAW)
    assert state.turn_count > 0
    assert state.log.entries
    if outcome is BattleOutcome.VICTORY:
        assert not state.living(Side.ENEMY)


def test_skip_action_when_no_targets():
    engine, state = make()
    state.unit("E1").alive = False
    state.outcome = state.outcome  # 종료 판정과 무관하게 행동 생성만 확인
    actions = engine.legal_actions(state, "A1")
    assert len(actions) == 1 and isinstance(actions[0], SkipAction)
