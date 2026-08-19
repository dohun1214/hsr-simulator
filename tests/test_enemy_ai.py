"""적 행동 패턴(AI) 테스트. 근거: docs/mechanics.md 7장

게임 데이터에서 관찰된 두 형태를 검증한다.
  1. 고정 스킬 순환 (템플릿 613개 중 158개가 사용)
  2. 효용 기반 결정 (조건 1개 + 점수 1개가 표준)
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import ai, scheduler, status
from hsr_sim.battle.actions import UseSkillAction
from hsr_sim.battle.predicates import Predicate
from hsr_sim.entities.unit import ACTION_GAUGE_FULL


def make(enemies=("test_enemy_sequence",), allies=("test_ally_a",), **kwargs):
    kwargs.setdefault("crit_mode", CritMode.NEVER)
    config = BattleConfig(log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def used_skills(engine, state, uid, n):
    """이 유닛이 자기 턴을 n번 가졌을 때 쓰는 스킬 순서.

    쿨다운은 소유자의 턴 종료 시에 줄어들므로 그것까지 흉내낸다.
    """
    out = []
    unit = state.unit(uid)
    for _ in range(n):
        out.append(engine.choose_action(state, uid).skill_id)
        ai.tick_cooldowns(unit)
    return out


# --- 고정 스킬 순환 ---------------------------------------------------------


def test_sequence_ai_cycles_through_its_skill_list():
    engine, state = make()
    assert used_skills(engine, state, "E1", 7) == [
        "basic", "sweep", "basic", "basic", "sweep", "basic", "basic",
    ]


def test_sequence_ai_is_not_random():
    runs = []
    for seed in (1, 2, 3):
        engine, state = make(seed=seed)
        runs.append(used_skills(engine, state, "E1", 6))
    assert runs[0] == runs[1] == runs[2]


def test_sequence_position_survives_cloning():
    engine, state = make()
    engine.choose_action(state, "E1")
    clone = state.clone()
    assert clone.unit("E1").sequence_index == state.unit("E1").sequence_index
    engine.choose_action(state, "E1")
    assert clone.unit("E1").sequence_index != state.unit("E1").sequence_index


def test_sequence_skips_skills_unavailable_in_this_phase():
    engine, state = make(enemies=("test_boss",))
    boss = state.unit("E1")
    # 보스는 순환 AI 가 아니지만, 페이즈 게이팅 자체를 확인한다
    assert boss.phase == 1
    assert ai.decide(state, boss) == "basic"
    boss.phase = 2
    assert ai.decide(state, boss) == "nuke"


# --- 효용 기반 결정 ---------------------------------------------------------


def test_decision_ai_uses_counter_to_time_its_big_attack():
    """기본 공격 2회로 카운터를 쌓고 3번째에 강타."""
    engine, state = make(enemies=("test_enemy_smasher",))
    assert used_skills(engine, state, "E1", 6) == [
        "basic", "basic", "smash", "basic", "basic", "smash",
    ]


def test_counter_is_reset_after_the_big_attack():
    engine, state = make(enemies=("test_enemy_smasher",))
    enemy = state.unit("E1")
    used_skills(engine, state, "E1", 3)
    assert enemy.counters["charge"] == 0.0


def test_higher_score_decision_wins():
    """격노(0.9)는 HP 50% 미만에서만 참이고, 강타(1.0)보다 점수가 낮다."""
    engine, state = make(enemies=("test_enemy_smasher",))
    enemy = state.unit("E1")
    enemy.current_hp = enemy.max_hp * 0.3
    # 카운터가 0 이므로 강타 조건은 거짓 -> 격노(0.9) 가 기본(0.5) 를 이긴다
    assert ai.decide(state, enemy) == "enrage"


def test_cooldown_blocks_reuse():
    engine, state = make(enemies=("test_enemy_smasher",))
    enemy = state.unit("E1")
    enemy.current_hp = enemy.max_hp * 0.3
    assert ai.decide(state, enemy) == "enrage"
    # 격노는 쿨다운 99 이므로 다시 나오지 않는다
    assert ai.decide(state, enemy) != "enrage"


def test_cooldown_decreases_at_owner_turn_end():
    engine, state = make(enemies=("test_enemy_smasher",))
    enemy = state.unit("E1")
    enemy.skill_cooldowns["smash"] = 2
    ai.tick_cooldowns(enemy)
    assert enemy.skill_cooldowns["smash"] == 1
    ai.tick_cooldowns(enemy)
    assert enemy.skill_cooldowns["smash"] == 0
    assert ai.ready(enemy, "smash")


def test_predicate_registry_is_extensible():
    """새 조건 = 함수 하나 + 등록."""
    from hsr_sim.battle.predicates import PREDICATES

    PREDICATES.register("test_never", lambda state, unit, params: False)
    try:
        engine, state = make()
        assert Predicate("test_never").evaluate(state, state.unit("E1")) is False
        assert Predicate("test_never", negate=True).evaluate(state, state.unit("E1")) is True
    finally:
        PREDICATES._items.pop("test_never", None)


# --- 행동 게이지 배수 -------------------------------------------------------


def test_skill_delay_ratio_pushes_the_next_turn_back():
    """광역기(delay_ratio 1.5)를 쓰면 다음 턴이 1.5배 늦게 온다."""
    engine, state = make()
    enemy = state.unit("E1")
    state.active_uid = "E1"
    engine.perform(state, UseSkillAction(actor_uid="E1", target_uid="A1", skill_id="sweep"))
    assert enemy.pending_delay_ratio == pytest.approx(1.5)
    engine.end_turn(state)
    assert enemy.action_gauge == pytest.approx(ACTION_GAUGE_FULL * 1.5)
    assert enemy.pending_delay_ratio == pytest.approx(1.0)


def test_normal_skill_keeps_the_standard_gauge():
    engine, state = make()
    enemy = state.unit("E1")
    state.active_uid = "E1"
    engine.perform(state, UseSkillAction(actor_uid="E1", target_uid="A1", skill_id="basic"))
    engine.end_turn(state)
    assert enemy.action_gauge == pytest.approx(ACTION_GAUGE_FULL)


def test_initial_delay_ratio_makes_a_unit_act_sooner():
    """보스는 InitialDelayRatio 0.5 -> 처음 행동이 절반 시점에 온다."""
    engine, state = make(enemies=("test_boss",))
    boss = state.unit("E1")
    assert boss.action_gauge == pytest.approx(ACTION_GAUGE_FULL * 0.5)
    assert scheduler.action_value(boss) == pytest.approx(
        ACTION_GAUGE_FULL * 0.5 / boss.spd
    )


# --- 대상 에너지 (SPHitBase) ------------------------------------------------


def test_enemy_skills_grant_energy_per_skill_data():
    """SPHitBase 는 스킬마다 다르다. 일반 10 / 광역 15."""
    engine, state = make()
    ally = state.unit("A1")
    state.active_uid = "E1"
    engine.perform(state, UseSkillAction(actor_uid="E1", target_uid="A1", skill_id="basic"))
    assert ally.energy == pytest.approx(10.0)
    engine.perform(state, UseSkillAction(actor_uid="E1", target_uid="A1", skill_id="sweep"))
    assert ally.energy == pytest.approx(25.0)


# --- 통합 --------------------------------------------------------------------


def test_enemy_ai_behavior_produces_use_skill_actions():
    engine, state = make()
    action = engine.choose_action(state, "E1")
    assert isinstance(action, UseSkillAction)
    assert action.target_uid == "A1"


def test_full_battle_with_ai_enemies_is_deterministic():
    results = []
    for _ in range(2):
        engine, state = make(
            allies=("test_ally_a", "test_ally_b", "test_ally_c"),
            enemies=("test_enemy_sequence", "test_enemy_smasher"),
            seed=77,
        )
        engine.run(state)
        results.append(
            (state.outcome, state.turn_count, tuple(round(u.current_hp, 6) for u in state.all_units()))
        )
    assert results[0] == results[1]


def test_boss_resists_crowd_control_completely():
    engine, state = make(enemies=("test_boss",))
    boss = state.unit("E1")
    applied = status.try_apply_effect(
        engine, state, boss, "test_stun", source=state.unit("A1")
    )
    assert applied is False
    assert not boss.has_effect("test_stun")
