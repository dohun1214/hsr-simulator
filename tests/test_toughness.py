"""인성치와 약점 격파 테스트. 근거: docs/mechanics.md 8장"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import scheduler, toughness
from hsr_sim.battle.actions import BasicAttackAction
from hsr_sim.battle.toughness import BreakConfig, BreakEffectSpec, WeaknessBroken
from hsr_sim.core.enums import Element
from hsr_sim.entities.unit import ACTION_GAUGE_FULL
from hsr_sim.stats.stat import Stat


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


# --- 격파 피해 -------------------------------------------------------------


def test_max_toughness_multiplier():
    """최대 인성치 배수 = 0.5 + 최대 인성치 / 120. docs/mechanics.md 8.3"""
    _, state = make()
    enemy = state.unit("E1")
    enemy.max_toughness = 60.0
    assert toughness.max_toughness_multiplier(enemy) == pytest.approx(1.0)
    enemy.max_toughness = 360.0
    assert toughness.max_toughness_multiplier(enemy) == pytest.approx(3.5)
    enemy.max_toughness = 30.0
    assert toughness.max_toughness_multiplier(enemy) == pytest.approx(0.75)


def test_break_damage_uses_element_multiplier_and_toughness():
    """물리 격파 = 2 x 격파기본피해 x 최대인성치배수. 최대 인성치 60 -> 배수 1.0"""
    engine, state = make()
    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, state.unit("A1"), state.unit("E1"), 60.0, Element.PHYSICAL)
    assert seen[0].break_damage == pytest.approx(3767.5535 * 2.0)


def test_break_damage_scales_with_break_effect():
    engine, state = make()
    attacker = state.unit("A1")
    attacker.base_stats[Stat.BREAK_EFFECT] = 1.5
    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, attacker, state.unit("E1"), 60.0, Element.PHYSICAL)
    assert seen[0].break_damage == pytest.approx(3767.5535 * 2.0 * 2.5)


def test_element_multipliers_match_the_cross_checked_table():
    assert toughness.ELEMENT_BREAK_MULTIPLIER == {
        Element.PHYSICAL: 2.0,
        Element.FIRE: 2.0,
        Element.ICE: 1.0,
        Element.LIGHTNING: 1.0,
        Element.WIND: 1.5,
        Element.QUANTUM: 0.5,
        Element.IMAGINARY: 0.5,
    }


def test_break_base_damage_table_matches_game_data():
    from hsr_sim.content import characters

    table = characters.load_data()["break_base_damage"]
    assert table["80"] == pytest.approx(3767.5535)
    assert table["1"] == pytest.approx(54.0)


def test_break_damage_can_still_be_switched_off():
    """미확인 항목을 끌 수 있는 구조는 유지한다."""
    config = BreakConfig(elements={Element.PHYSICAL: BreakEffectSpec("break_bleed", None)})
    engine, state = make(break_config=config)
    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    toughness.reduce(engine, state, state.unit("A1"), state.unit("E1"), 60.0, Element.PHYSICAL)
    assert seen[0].break_damage == 0.0


# --- 속성별 격파 디버프 (docs/mechanics.md 8.6) -----------------------------


def _break_with(engine, state, element):
    toughness.reduce(
        engine, state, state.unit("A1"), state.unit("E1"), 60.0, element,
        ignores_weakness=True,
    )
    return state.unit("E1")


@pytest.mark.parametrize(
    "element,effect_id",
    [
        (Element.PHYSICAL, "break_bleed"),
        (Element.FIRE, "break_burn"),
        (Element.ICE, "break_frozen"),
        (Element.LIGHTNING, "break_shock"),
        (Element.WIND, "break_wind_shear"),
        (Element.QUANTUM, "break_entanglement"),
        (Element.IMAGINARY, "break_imprisonment"),
    ],
)
def test_break_applies_the_matching_debuff(element, effect_id):
    engine, state = make()
    enemy = _break_with(engine, state, element)
    assert enemy.has_effect(effect_id)


def test_break_debuff_names_are_the_official_korean_ones():
    """게임 데이터 StatusConfig 30020020~30020026 의 명칭. 임의 번역이 아니다."""
    from hsr_sim.content import break_effects

    assert [d.name.ko for d in break_effects.BREAK_EFFECTS] == [
        "열상", "연소", "빙결", "감전", "풍화", "얽힘", "속박",
    ]


def test_wind_shear_starts_at_one_stack_and_three_for_elites():
    engine, state = make()
    enemy = _break_with(engine, state, Element.WIND)
    assert enemy.effect("break_wind_shear").stacks == 1

    engine, state = make()
    state.unit("E1").extra["rank"] = "Elite"
    enemy = _break_with(engine, state, Element.WIND)
    assert enemy.effect("break_wind_shear").stacks == 3


def test_imprisonment_reduces_speed_by_ten_percent():
    engine, state = make()
    enemy = state.unit("E1")
    before = enemy.stat(Stat.SPD)
    _break_with(engine, state, Element.IMAGINARY)
    assert enemy.stat(Stat.SPD) == pytest.approx(before * 0.9)


def test_entanglement_and_imprisonment_delay_more_than_a_plain_break():
    engine, state = make()
    _break_with(engine, state, Element.PHYSICAL)
    plain = state.unit("E1").action_gauge

    engine, state = make()
    _break_with(engine, state, Element.IMAGINARY)
    assert state.unit("E1").action_gauge > plain


def test_entanglement_gains_a_stack_when_hit():
    engine, state = make()
    enemy = _break_with(engine, state, Element.QUANTUM)
    assert enemy.effect("break_entanglement").stacks == 1

    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid="E1"))
    assert enemy.effect("break_entanglement").stacks == 2


def test_frozen_blocks_the_action_and_advances_the_next_turn_on_expiry():
    from hsr_sim.battle import status

    engine, state = make()
    enemy = _break_with(engine, state, Element.ICE)
    assert status.is_action_blocked(enemy) is True

    while engine.advance_to_next_turn(state) != "E1":
        engine.end_turn(state)
    engine.end_turn(state)

    assert enemy.has_effect("break_frozen") is False
    # 빙결이 풀리면서 다음 턴이 50% 앞당겨진다
    assert enemy.action_gauge == pytest.approx(ACTION_GAUGE_FULL * 0.5)


# --- 격파 지속 피해의 기본 피해 ---------------------------------------------


def _dot_base(engine, state, effect_id, target=None):
    from hsr_sim.battle import status
    from hsr_sim.registries import STATUS_EFFECTS

    definition = STATUS_EFFECTS.get(effect_id)
    return status.dot_base_per_stack(
        engine, state.unit("A1"), target or state.unit("E1"), definition.dot
    )


def test_burn_and_shock_scale_off_the_break_base_damage():
    engine, state = make()
    assert _dot_base(engine, state, "break_burn") == pytest.approx(3767.5535)
    assert _dot_base(engine, state, "break_shock") == pytest.approx(3767.5535 * 2)


def test_entanglement_uses_the_max_toughness_multiplier():
    engine, state = make()
    enemy = state.unit("E1")
    enemy.max_toughness = 360.0  # 배수 3.5
    assert _dot_base(engine, state, "break_entanglement") == pytest.approx(
        3767.5535 * 0.6 * 3.5
    )


def test_bleed_uses_target_max_hp_and_is_capped():
    engine, state = make()
    enemy = state.unit("E1")

    enemy.base_stats[Stat.MAX_HP] = 10_000.0
    assert _dot_base(engine, state, "break_bleed") == pytest.approx(1600.0)

    # 상한 = 2 x 격파기본피해 x 최대인성치배수(60 -> 1.0)
    enemy.base_stats[Stat.MAX_HP] = 1_000_000.0
    assert _dot_base(engine, state, "break_bleed") == pytest.approx(3767.5535 * 2)


def test_bleed_uses_a_lower_ratio_on_elites():
    engine, state = make()
    enemy = state.unit("E1")
    enemy.base_stats[Stat.MAX_HP] = 10_000.0
    enemy.extra["rank"] = "BigBoss"
    assert _dot_base(engine, state, "break_bleed") == pytest.approx(700.0)


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


def test_real_character_breaks_a_real_enemy_and_applies_burn():
    """히메코(화염) 일반 공격 2회 -> 얼음 서슬(화염 약점, 인성치 60) 격파 -> 연소."""
    from hsr_sim.content import characters, monsters

    party = [characters.register(1003, level=80)]
    enemy = monsters.register(1002011, level=80)
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False)
    state = build_battle(party, [enemy], config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)

    seen = []
    engine.bus.subscribe(WeaknessBroken, lambda e, s, ev: seen.append(ev))
    target = state.unit("E1")
    for _ in range(2):
        state.active_uid = "A1"
        engine.perform(
            state,
            BasicAttackAction(actor_uid="A1", target_uid="E1", skill_id=party[0].basic_attack_id),
        )

    assert target.toughness_broken is True
    assert seen and seen[0].element is Element.FIRE
    # 화염 배수 2.0, 최대 인성치 60 -> 배수 1.0
    assert seen[0].break_damage == pytest.approx(3767.5535 * 2.0)
    assert target.has_effect("break_burn")
