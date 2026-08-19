"""인성치와 약점 격파 테스트. 근거: docs/mechanics.md 8장

**주의**: 격파 피해의 속성 배수와 인성치 배수는 근거를 찾지 못했다.
설정하지 않으면 격파 피해가 0 이며, 그 동작 자체를 테스트로 고정한다.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import scheduler, toughness
from hsr_sim.battle.actions import BasicAttackAction
from hsr_sim.battle.toughness import BreakConfig, BreakEffectSpec, WeaknessBroken
from hsr_sim.core.enums import Element
from hsr_sim.entities.unit import ACTION_GAUGE_FULL


def make(allies=("test_ally_a",), enemies=("test_enemy_a",), **kwargs):
    kwargs.setdefault("crit_mode", CritMode.NEVER)
    config = BattleConfig(log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


# --- 인성치 감소 조건 -------------------------------------------------------


def test_enemies_start_with_full_toughness():
    _, state = make()
    enemy = state.unit("E1")
    assert enemy.max_toughness == 60.0
    assert enemy.current_toughness == 60.0
    assert enemy.toughness_broken is False


def test_toughness_only_drops_on_weakness_element():
    """테스트 적 A 의 약점은 물리다."""
    engine, state = make()
    enemy = state.unit("E1")
    attacker = state.unit("A1")

    # 물리(약점) -> 깎인다
    assert toughness.reduce(engine, state, attacker, enemy, 30.0, Element.PHYSICAL) is False
    assert enemy.current_toughness == 30.0

    # 화염(약점 아님) -> 안 깎인다
    toughness.reduce(engine, state, attacker, enemy, 30.0, Element.FIRE)
    assert enemy.current_toughness == 30.0


def test_ignores_weakness_flag_bypasses_the_check():
    """아케론 필살기처럼 '약점 속성 무시' 효과가 있다 (docs/mechanics.md 8.1)."""
    engine, state = make()
    enemy = state.unit("E1")
    toughness.reduce(
        engine, state, state.unit("A1"), enemy, 30.0, Element.FIRE, ignores_weakness=True
    )
    assert enemy.current_toughness == 30.0


def test_units_without_toughness_are_never_reduced():
    engine, state = make()
    ally = state.unit("A1")
    assert ally.max_toughness == 0.0
    assert toughness.can_reduce(ally, Element.PHYSICAL) is False


# --- 격파 ------------------------------------------------------------------


def test_break_when_toughness_reaches_zero():
    engine, state = make()
    enemy = state.unit("E1")
    broke = toughness.reduce(engine, state, state.unit("A1"), enemy, 60.0, Element.PHYSICAL)
    assert broke is True
    assert enemy.toughness_broken is True
    assert enemy.current_toughness == 0.0


def test_broken_enemy_takes_full_damage():
    """격파 전 0.9 배수가 격파 후 1.0 이 된다 (docs/mechanics.md 2.8)."""
    engine, state = make()
    enemy = state.unit("E1")
    state.active_uid = "A1"

    before = enemy.current_hp
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    unbroken_hit = before - enemy.current_hp

    enemy.toughness_broken = True
    before = enemy.current_hp
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    broken_hit = before - enemy.current_hp

    assert broken_hit / unbroken_hit == pytest.approx(1 / 0.9)


def test_break_delays_the_targets_action():
    engine, state = make()
    enemy = state.unit("E1")
    gauge_before = enemy.action_gauge
    toughness.reduce(engine, state, state.unit("A1"), enemy, 60.0, Element.PHYSICAL)
    # 기본 지연 25% (근거 미확인, 설정값)
    assert enemy.action_gauge == pytest.approx(gauge_before + ACTION_GAUGE_FULL * 0.25)


def test_already_broken_enemy_does_not_lose_more_toughness():
    engine, state = make()
    enemy = state.unit("E1")
    toughness.reduce(engine, state, state.unit("A1"), enemy, 60.0, Element.PHYSICAL)
    assert toughness.can_reduce(enemy, Element.PHYSICAL) is False


def test_break_event_is_emitted():
    engine, state = make()
    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, state.unit("A1"), state.unit("E1"), 60.0, Element.PHYSICAL)
    assert len(seen) == 1 and seen[0].element is Element.PHYSICAL


# --- 격파 피해 (근거 없는 부분) ---------------------------------------------


def test_break_damage_is_zero_without_configured_multipliers():
    """속성 배수의 근거를 찾지 못했다. 추정값을 몰래 쓰지 않는다."""
    engine, state = make()
    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, state.unit("A1"), state.unit("E1"), 60.0, Element.PHYSICAL)
    assert seen[0].break_damage == 0.0


def test_break_damage_uses_the_game_level_table_when_configured():
    """속성 배수를 설정하면 게임 원본 레벨 표로 계산한다."""
    config = BreakConfig(elements={Element.PHYSICAL: BreakEffectSpec(damage_multiplier=2.0)})
    engine, state = make(break_config=config)
    engine.config.break_base_damage_table = {80: 3767.5535}

    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, state.unit("A1"), state.unit("E1"), 60.0, Element.PHYSICAL)
    assert seen[0].break_damage == pytest.approx(3767.5535 * 2.0)


def test_break_base_damage_table_matches_game_data():
    from hsr_sim.content import characters

    table = characters.load_data()["break_base_damage"]
    assert table["80"] == pytest.approx(3767.5535)
    assert table["1"] == pytest.approx(54.0)


# --- 인성치 회복 ------------------------------------------------------------


def test_toughness_recovers_at_the_end_of_the_broken_units_turn():
    engine, state = make()
    enemy = state.unit("E1")
    toughness.reduce(engine, state, state.unit("A1"), enemy, 60.0, Element.PHYSICAL)
    assert enemy.toughness_broken is True

    while engine.advance_to_next_turn(state) != "E1":
        engine.end_turn(state)
    engine.end_turn(state)

    assert enemy.toughness_broken is False
    assert enemy.current_toughness == enemy.max_toughness


# --- 실제 데이터 연동 -------------------------------------------------------


def test_real_character_skill_reduces_real_enemy_toughness():
    from hsr_sim.content import characters, monsters

    # 히메코(화염) -> 얼음 서슬(화염 약점)
    party = [characters.register(1003, level=80)]
    enemy = monsters.register(1002011, level=80)
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False)
    state = build_battle(party, [enemy], config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    target = state.unit("E1")
    assert target.max_toughness == 60.0
    before = target.current_toughness
    state.active_uid = "A1"
    # 실제 캐릭터의 스킬 id 는 숫자다
    engine.perform(
        state,
        BasicAttackAction(actor_uid="A1", target_uid="E1", skill_id=party[0].basic_attack_id),
    )
    # 일반 공격의 인성치 감소량은 게임 데이터에서 30
    assert before - target.current_toughness == pytest.approx(30.0)
