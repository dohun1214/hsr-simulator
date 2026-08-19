"""지속 피해(DoT) 테스트. 근거: docs/mechanics.md 5.6

기준 수치 (모든 테스트 공통):
  시전자 A1 = 테스트 아군 C, ATK 800, 레벨 80
  화상  = ATK 50% / 중첩, 화염
  중독  = ATK 25%, 양자
  대상 E1 = 테스트 적 A, DEF 1000, 물리 약점(=화염/양자는 비약점 RES 20%), 미격파
  -> 화상 1중첩 틱 = 400 x 0.5(DEF) x 0.8(RES) x 0.9(미격파) = 144.0
  -> 중독      틱 = 200 x 0.5 x 0.8 x 0.9 = 72.0
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import status
from hsr_sim.core.events import DotTick
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier

BURN_TICK = 144.0
POISON_TICK = 72.0


def make(**kwargs):
    kwargs.setdefault("crit_mode", CritMode.NEVER)
    config = BattleConfig(log_enabled=False, **kwargs)
    state = build_battle(
        definitions("test_ally_c"), definitions("test_enemy_a"), config=config
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def advance_to(engine, state, uid, limit=30):
    for _ in range(limit):
        actor = engine.advance_to_next_turn(state)
        if actor == uid:
            return
        engine.end_turn(state)
    raise AssertionError(f"{uid} 의 턴이 오지 않았습니다")


def test_dot_ticks_at_the_start_of_the_targets_turn():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))

    # 다른 유닛의 턴에는 발동하지 않는다
    advance_to(engine, state, "A1")
    assert enemy.current_hp == enemy.max_hp
    engine.end_turn(state)

    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK)


def test_dot_damage_hand_calculation():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))
    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(144.0)


def test_dot_scales_with_stacks():
    engine, state = make()
    enemy = state.unit("E1")
    for _ in range(3):
        status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))
    assert enemy.effect("test_burn").stacks == 3
    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK * 3)


def test_dot_never_crits_even_when_crit_mode_is_always():
    engine, state = make(crit_mode=CritMode.ALWAYS)
    enemy = state.unit("E1")
    source = state.unit("A1")
    source.modifiers.append(StatModifier(Stat.CRIT_RATE, ModifierKind.FLAT, 1.0))
    source.modifiers.append(StatModifier(Stat.CRIT_DMG, ModifierKind.FLAT, 2.0))
    status.apply_effect(engine, state, enemy, "test_burn", source=source)
    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK)


def test_dots_tick_in_chronological_order():
    engine, state = make()
    enemy = state.unit("E1")
    order = []
    engine.bus.subscribe(DotTick, lambda e, s, ev: order.append(ev.effect_id))

    status.apply_effect(engine, state, enemy, "test_poison", source=state.unit("A1"))
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))
    advance_to(engine, state, "E1")
    assert order == ["test_poison", "test_burn"]
    assert enemy.max_hp - enemy.current_hp == pytest.approx(POISON_TICK + BURN_TICK)


def test_dot_expires_after_its_duration():
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"), duration=2)

    ticks = 0
    for _ in range(6):
        actor = engine.advance_to_next_turn(state)
        if actor == "E1":
            ticks += 1
        engine.end_turn(state)
    # 2턴 지속 -> 정확히 2번 발동
    assert ticks >= 2
    assert not enemy.has_effect("test_burn")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK * 2)


def test_dot_can_defeat_the_target_and_it_does_not_act():
    engine, state = make()
    enemy = state.unit("E1")
    enemy.current_hp = 100.0
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))

    advance_to(engine, state, "E1")
    assert enemy.alive is False
    assert state.is_over


def test_snapshot_mode_freezes_the_casters_attack():
    engine, state = make(dot_snapshot=True)
    enemy = state.unit("E1")
    source = state.unit("A1")
    status.apply_effect(engine, state, enemy, "test_burn", source=source)

    source.modifiers.append(StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 1.0))
    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK)


def test_live_mode_recalculates_from_current_stats():
    engine, state = make(dot_snapshot=False)
    enemy = state.unit("E1")
    source = state.unit("A1")
    status.apply_effect(engine, state, enemy, "test_burn", source=source)

    source.modifiers.append(StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 1.0))
    advance_to(engine, state, "E1")
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK * 2)


def test_snapshot_survives_the_casters_death():
    engine, state = make(dot_snapshot=True)
    enemy = state.unit("E1")
    source = state.unit("A1")
    status.apply_effect(engine, state, enemy, "test_burn", source=source)
    source.alive = False
    source.current_hp = 0.0

    engine.advance_to_next_turn(state)  # E1 만 남았으므로 다음은 E1
    assert enemy.max_hp - enemy.current_hp == pytest.approx(BURN_TICK)


def test_defence_reduction_increases_dot_damage():
    """DoT 는 발동 시점의 방어 측 값을 쓴다."""
    engine, state = make()
    enemy = state.unit("E1")
    status.apply_effect(engine, state, enemy, "test_burn", source=state.unit("A1"))
    status.apply_effect(engine, state, enemy, "test_def_down")
    advance_to(engine, state, "E1")
    expected = 400.0 * (1.0 - 700.0 / 1700.0) * 0.8 * 0.9
    assert enemy.max_hp - enemy.current_hp == pytest.approx(expected)
