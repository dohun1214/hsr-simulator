"""전투 스킬과 대상 지정(단일/확산/전체) 테스트."""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle.actions import SkillAction, UltimateAction
from hsr_sim.battle.resources import gain_energy


def make(allies, enemies, **kwargs):
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def damage_taken(state, uid):
    unit = state.unit(uid)
    return unit.max_hp - unit.current_hp


def test_single_target_skill_hand_calculation():
    """A1 스킬: ATK 1000 x 배율 2.0 = 2000, DEF 0.5, 물리 약점 1.0, 미격파 0.9 -> 900"""
    engine, state = make(("test_ally_a",), ("test_enemy_a",))
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    assert damage_taken(state, "E1") == pytest.approx(900.0)


def test_blast_hits_primary_and_both_neighbours():
    """A2 확산 스킬을 가운데 적에게.

    주 대상 E2: 900 x 1.5 = 1350, DEF(800) 5/9, 화염 약점 1.0, 0.9 -> 675.0
    인접 E1   : 900 x 0.75 = 675, DEF(1000) 0.5, 화염 비약점 0.8, 0.9 -> 243.0
    인접 E3   : 675, DEF(800) 5/9, 화염 약점 1.0, 0.9 -> 337.5
    """
    engine, state = make(
        ("test_ally_b",), ("test_enemy_a", "test_enemy_b", "test_enemy_c")
    )
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E2"))
    assert damage_taken(state, "E2") == pytest.approx(675.0)
    assert damage_taken(state, "E1") == pytest.approx(243.0)
    assert damage_taken(state, "E3") == pytest.approx(337.5)


def test_blast_on_edge_hits_only_two():
    engine, state = make(
        ("test_ally_b",), ("test_enemy_a", "test_enemy_b", "test_enemy_c")
    )
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    assert damage_taken(state, "E1") > 0
    assert damage_taken(state, "E2") > 0
    assert damage_taken(state, "E3") == 0


def test_blast_adjacency_follows_living_units_not_slot_numbers():
    """가운데 적이 쓰러지면 양옆이 서로 인접해진다."""
    engine, state = make(
        ("test_ally_b",), ("test_enemy_a", "test_enemy_b", "test_enemy_c")
    )
    state.unit("E2").alive = False
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    assert damage_taken(state, "E3") > 0


def test_aoe_ultimate_hits_every_living_enemy():
    """A1 필살기: 배율 3.0, 전체 공격."""
    engine, state = make(("test_ally_a",), ("test_enemy_a", "test_enemy_b"))
    gain_energy(engine, state, state.unit("A1"), 120.0)
    engine.use_ultimate(state, UltimateAction(actor_uid="A1", target_uid="E1"))
    # E1: 3000 x 0.5 x 1.0 x 0.9 = 1350 / E2: 3000 x 5/9 x 0.8 x 0.9 = 1200
    assert damage_taken(state, "E1") == pytest.approx(1350.0)
    assert damage_taken(state, "E2") == pytest.approx(1200.0)


def test_aoe_generates_only_one_action_choice():
    engine, state = make(("test_ally_a",), ("test_enemy_a", "test_enemy_b"))
    gain_energy(engine, state, state.unit("A1"), 120.0)
    assert len(engine.available_ultimates(state)) == 1
