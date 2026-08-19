"""상태 효과 (버프/디버프) 테스트. 근거: docs/mechanics.md 5장"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import status
from hsr_sim.battle.actions import BasicAttackAction, SkillAction, SkipAction
from hsr_sim.core.enums import EffectCategory
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def make(allies=("test_ally_c",), enemies=("test_enemy_a",), **kwargs):
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def turns_until(engine, state, uid, limit=30):
    """해당 유닛의 턴이 올 때까지 진행하고 그 턴을 시작한 상태로 둔다."""
    for _ in range(limit):
        actor = engine.advance_to_next_turn(state)
        if actor == uid:
            return
        engine.end_turn(state)
    raise AssertionError(f"{uid} 의 턴이 오지 않았습니다")


# --- 부여 / 스탯 반영 -------------------------------------------------------


def test_buff_applies_stat_modifier():
    engine, state = make()
    unit = state.unit("A1")
    assert unit.stat(Stat.ATK) == pytest.approx(800.0)

    status.apply_effect(engine, state, unit, "test_atk_up", source=unit)
    assert unit.stat(Stat.ATK) == pytest.approx(960.0)  # +20%


def test_stacking_multiplies_modifier_value():
    engine, state = make()
    unit = state.unit("A1")
    for _ in range(3):
        status.apply_effect(engine, state, unit, "test_atk_up", source=unit)
    assert unit.effect("test_atk_up").stacks == 3
    assert unit.stat(Stat.ATK) == pytest.approx(800.0 * 1.6)  # +60%


def test_stacks_are_capped():
    engine, state = make()
    unit = state.unit("A1")
    for _ in range(10):
        status.apply_effect(engine, state, unit, "test_atk_up", source=unit)
    assert unit.effect("test_atk_up").stacks == 3


def test_refresh_policy_only_refreshes_duration():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_def_down", duration=1)
    assert enemy.effect("test_def_down").remaining_turns == 1
    status.apply_effect(engine, state, enemy, "test_def_down")
    assert enemy.effect("test_def_down").stacks == 1
    assert enemy.effect("test_def_down").remaining_turns == 2


def test_removing_effect_removes_its_modifiers():
    engine, state = make()
    unit = state.unit("A1")
    status.apply_effect(engine, state, unit, "test_atk_up", source=unit)
    assert unit.stat(Stat.ATK) > 800.0
    status.remove_effect(engine, state, unit, "test_atk_up")
    assert unit.stat(Stat.ATK) == pytest.approx(800.0)
    assert unit.modifiers == []


def test_effect_modifiers_do_not_clobber_other_modifiers():
    engine, state = make()
    unit = state.unit("A1")
    unit.modifiers.append(StatModifier(Stat.ATK, ModifierKind.FLAT, 100.0, "relic"))
    status.apply_effect(engine, state, unit, "test_atk_up", source=unit)
    status.remove_effect(engine, state, unit, "test_atk_up")
    assert unit.stat(Stat.ATK) == pytest.approx(900.0)


# --- 지속시간 --------------------------------------------------------------


def test_duration_decreases_at_owner_turn_end():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_def_down", duration=2)

    turns_until(engine, state, "E1")
    assert enemy.effect("test_def_down").remaining_turns == 2  # 턴 시작에는 그대로
    engine.end_turn(state)
    assert enemy.effect("test_def_down").remaining_turns == 1

    turns_until(engine, state, "E1")
    engine.end_turn(state)
    assert not enemy.has_effect("test_def_down")  # 만료


def test_turn_start_timing_effect_decreases_at_turn_start():
    engine, state = make()
    unit = state.unit("A1")
    status.apply_effect(engine, state, unit, "test_turn_start_buff", duration=2, source=unit)
    turns_until(engine, state, "A1")
    assert unit.effect("test_turn_start_buff").remaining_turns == 1


def test_infinite_duration_never_expires():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_unremovable_mark", duration=-1)
    for _ in range(6):
        uid = engine.advance_to_next_turn(state)
        engine.end_turn(state)
    assert enemy.has_effect("test_unremovable_mark")


# --- 적용 확률 --------------------------------------------------------------


def test_application_chance_formula():
    """확률 = 기본 x (1 + 효과 명중) x (1 - 효과 저항) x (1 - 디버프 저항)"""
    engine, state = make()
    source = state.unit("A1")
    target = state.unit("E1")
    source.modifiers.append(StatModifier(Stat.EFFECT_HIT_RATE, ModifierKind.FLAT, 0.5))
    target.base_stats[Stat.EFFECT_RES] = 0.0  # 적의 기본 효과 저항을 지우고 시작
    target.modifiers.append(StatModifier(Stat.EFFECT_RES, ModifierKind.FLAT, 0.1))
    target.debuff_res["test_def_down"] = 0.2

    chance = status.application_chance(source, target, "test_def_down", 0.8)
    assert chance == pytest.approx(0.8 * 1.5 * 0.9 * 0.8)


def test_enemies_have_base_effect_resistance():
    """게임 데이터 StatusResistanceBase 는 0.1~0.3 이며 0 이 아니다.
    근거: docs/mechanics.md 7.6
    """
    _, state = make()
    assert state.unit("E1").stat(Stat.EFFECT_RES) == pytest.approx(0.2)
    # 기본 확률 100% 도 적의 저항 때문에 80% 가 된다
    assert status.application_chance(
        state.unit("A1"), state.unit("E1"), "test_def_down", 1.0
    ) == pytest.approx(0.8)


def test_debuff_resistance_is_looked_up_by_tag():
    """게임 데이터의 DebuffResist 는 효과 id 가 아니라 태그 단위다."""
    _, state = make(enemies=("test_boss",))
    boss = state.unit("E1")
    assert boss.debuff_res == {"STAT_CTRL": 1.0}
    # 행동 불능 효과는 STAT_CTRL 태그를 가지므로 완전 저항
    assert status.debuff_resistance(boss, "test_stun") == 1.0
    # 화상은 다른 태그이므로 영향 없음
    assert status.debuff_resistance(boss, "test_burn") == 0.0


def test_application_chance_is_capped_at_one():
    engine, state = make()
    source = state.unit("A1")
    source.modifiers.append(StatModifier(Stat.EFFECT_HIT_RATE, ModifierKind.FLAT, 2.0))
    assert status.application_chance(source, state.unit("E1"), "test_def_down", 1.0) == 1.0


def test_full_debuff_res_always_resists():
    engine, state = make()
    target = state.unit("E1")
    target.debuff_res["test_def_down"] = 1.0
    applied = status.try_apply_effect(
        engine, state, target, "test_def_down", source=state.unit("A1")
    )
    assert applied is False
    assert not target.has_effect("test_def_down")


def test_buffs_skip_the_resistance_roll():
    engine, state = make()
    unit = state.unit("A1")
    unit.modifiers.append(StatModifier(Stat.EFFECT_RES, ModifierKind.FLAT, 1.0))
    assert status.try_apply_effect(engine, state, unit, "test_atk_up", base_chance=0.0) is True


def test_partial_chance_is_deterministic_for_a_seed():
    results = []
    for _ in range(2):
        engine, state = make(seed=11)
        outcomes = [
            status.try_apply_effect(
                engine, state, state.unit("E1"), "test_def_down",
                source=state.unit("A1"), base_chance=0.5,
            )
            for _ in range(20)
        ]
        results.append(outcomes)
    assert results[0] == results[1]
    assert any(results[0]) and not all(results[0])


# --- 해제 -----------------------------------------------------------------


def test_cleanse_removes_removable_debuffs_oldest_first():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_def_down")
    status.apply_effect(engine, state, enemy, "test_slow")
    removed = status.cleanse(engine, state, enemy, EffectCategory.DEBUFF, count=1)
    assert removed == 1
    assert not enemy.has_effect("test_def_down")
    assert enemy.has_effect("test_slow")


def test_cleanse_skips_unremovable_effects():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_unremovable_mark")
    assert status.cleanse(engine, state, enemy, EffectCategory.DEBUFF, count=5) == 0
    assert enemy.has_effect("test_unremovable_mark")


# --- 행동 불능 -------------------------------------------------------------


def test_crowd_control_blocks_the_main_action():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_stun")
    actions = engine.legal_actions(state, "E1")
    assert len(actions) == 1 and isinstance(actions[0], SkipAction)


def test_slow_reduces_speed_and_delays_turns():
    engine, state = make()
    enemy = state.unit("E1")
    base_spd = enemy.spd
    status.apply_effect(engine, state, enemy, "test_slow")
    assert enemy.spd == pytest.approx(base_spd * 0.8)


# --- 스킬 연동 -------------------------------------------------------------


def test_skill_applies_its_debuff_after_damage():
    """방어력 감소는 그 타격 자체에는 적용되지 않고 다음 타격부터 적용된다."""
    engine, state = make()
    enemy = state.unit("E1")
    enemy.base_stats[Stat.EFFECT_RES] = 0.0  # 확률 판정을 확정적으로 만든다
    state.active_uid = "A1"
    engine.perform(state, SkillAction(actor_uid="A1", target_uid="E1"))
    first_hit = enemy.max_hp - enemy.current_hp
    assert enemy.has_effect("test_def_down")

    # A1(테스트 아군 C)은 바람 속성이고 E1 의 약점은 물리이므로 RES 20% -> 0.8
    # 첫 타격: 800 x 0.5(DEF 1000) x 0.8 x 0.9 = 288
    assert first_hit == pytest.approx(288.0)

    before = enemy.current_hp
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    second_hit = before - enemy.current_hp
    # 방어력 30% 감소 -> DEF 700 -> 1 - 700/1700
    assert second_hit == pytest.approx(800.0 * (1.0 - 700.0 / 1700.0) * 0.8 * 0.9)
    assert second_hit > first_hit


# --- 복제 -----------------------------------------------------------------


def test_clone_keeps_effects_independent():
    engine, state = make()
    status.apply_effect(engine, state, state.unit("E1"), "test_def_down")
    clone = state.clone()
    clone.unit("E1").effect("test_def_down").stacks = 5
    status.remove_effect(engine, clone, clone.unit("E1"), "test_def_down")

    assert state.unit("E1").has_effect("test_def_down")
    assert state.unit("E1").effect("test_def_down").stacks == 1
