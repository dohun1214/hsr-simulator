"""어그로(도발치)와 적의 대상 선택 테스트. 근거: docs/mechanics.md 6장

테스트 파티의 운명의 길과 기본 어그로:
  A1 = 테스트 아군 A, 파멸  -> 125
  A2 = 테스트 아군 B, 수렵  ->  75
  A3 = 테스트 아군 C, 허무  -> 100
  합계 300 -> 확률 125/300, 75/300, 100/300
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import aggro, status
from hsr_sim.battle.actions import BasicAttackAction
from hsr_sim.core.enums import Path, Side
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


def make(allies=("test_ally_a", "test_ally_b", "test_ally_c"), enemies=("test_enemy_a",), **kwargs):
    kwargs.setdefault("crit_mode", CritMode.NEVER)
    config = BattleConfig(log_enabled=False, **kwargs)
    state = build_battle(definitions(*allies), definitions(*enemies), config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


# --- 기본값 ---------------------------------------------------------------


def test_base_aggro_per_path():
    """운명의 길별 기본 어그로. 3개 자료 교차검증 값."""
    assert aggro.base_aggro_for(Path.PRESERVATION) == 150.0
    assert aggro.base_aggro_for(Path.DESTRUCTION) == 125.0
    assert aggro.base_aggro_for(Path.HARMONY) == 100.0
    assert aggro.base_aggro_for(Path.NIHILITY) == 100.0
    assert aggro.base_aggro_for(Path.ABUNDANCE) == 100.0
    assert aggro.base_aggro_for(Path.REMEMBRANCE) == 100.0
    assert aggro.base_aggro_for(Path.HUNT) == 75.0
    assert aggro.base_aggro_for(Path.ERUDITION) == 75.0


def test_fandom_scale_is_25x_of_internal_scale():
    """Fandom 은 3/4/5/6, 다른 자료는 75/100/125/150 으로 적는다. 정확히 25배."""
    for path, small in [
        (Path.HUNT, 3), (Path.ERUDITION, 3),
        (Path.HARMONY, 4), (Path.NIHILITY, 4), (Path.ABUNDANCE, 4),
        (Path.DESTRUCTION, 5), (Path.PRESERVATION, 6),
    ]:
        assert aggro.base_aggro_for(path) == small * 25


def test_units_get_aggro_from_their_path():
    _, state = make()
    assert state.unit("A1").stat(Stat.AGGRO) == 125.0
    assert state.unit("A2").stat(Stat.AGGRO) == 75.0
    assert state.unit("A3").stat(Stat.AGGRO) == 100.0


def test_definition_override_beats_path():
    from hsr_sim.entities.definitions import LocalizedName, UnitDefinition
    from hsr_sim.setup import spawn_unit

    definition = UnitDefinition(
        unit_id="x",
        name=LocalizedName(ko="x", en="x"),
        path=Path.HUNT,
        base_aggro=999.0,
    )
    assert spawn_unit(definition, "A9").stat(Stat.AGGRO) == 999.0


# --- 확률 공식 -------------------------------------------------------------


def test_target_probability_is_aggro_share():
    """확률 = 자신의 어그로 / 살아 있는 아군 어그로 총합"""
    _, state = make()
    weights = aggro.target_weights(state.living(Side.ALLY))
    assert weights["A1"] == pytest.approx(125.0 / 300.0)
    assert weights["A2"] == pytest.approx(75.0 / 300.0)
    assert weights["A3"] == pytest.approx(100.0 / 300.0)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_dead_allies_are_excluded_from_the_pool():
    _, state = make()
    state.unit("A2").alive = False
    weights = aggro.target_weights(state.living(Side.ALLY))
    assert set(weights) == {"A1", "A3"}
    assert weights["A1"] == pytest.approx(125.0 / 225.0)


def test_aggro_modifiers_are_additive_inside_the_multiplier():
    """어그로 = 기본 x (1 + 수정자 합). 자료의 겁화 예시 150 x (1+3+2) = 900 과 동일 구조."""
    _, state = make()
    unit = state.unit("A1")
    unit.modifiers.append(StatModifier(Stat.AGGRO, ModifierKind.PERCENT_OF_BASE, 3.0))
    unit.modifiers.append(StatModifier(Stat.AGGRO, ModifierKind.PERCENT_OF_BASE, 2.0))
    assert aggro.aggro_of(unit) == pytest.approx(125.0 * 6.0)


def test_negative_aggro_is_clamped_to_zero():
    _, state = make()
    unit = state.unit("A1")
    unit.modifiers.append(StatModifier(Stat.AGGRO, ModifierKind.PERCENT_OF_BASE, -5.0))
    assert aggro.aggro_of(unit) == 0.0


# --- 도발 / 어그로 감소 -----------------------------------------------------


def test_taunt_effect_dominates_target_selection():
    engine, state = make()
    status.apply_effect(engine, state, state.unit("A2"), "test_taunt")
    # 75 x 6 = 450, 총합 125 + 450 + 100 = 675
    weights = aggro.target_weights(state.living(Side.ALLY))
    assert weights["A2"] == pytest.approx(450.0 / 675.0)
    assert weights["A2"] > weights["A1"] > weights["A3"] * 0.9


def test_aggro_reduction_effect():
    engine, state = make()
    status.apply_effect(engine, state, state.unit("A1"), "test_aggro_down")
    assert aggro.aggro_of(state.unit("A1")) == pytest.approx(62.5)


# --- 실제 선택 -------------------------------------------------------------


def sample_targets(engine, state, rolls=3000, selection="aggro"):
    counts = {"A1": 0, "A2": 0, "A3": 0}
    allies = state.living(Side.ALLY)
    for _ in range(rolls):
        target = aggro.select_target(state, allies, selection)
        counts[target.uid] += 1
    return {uid: n / rolls for uid, n in counts.items()}


def test_selection_follows_the_aggro_distribution():
    engine, state = make(seed=4242)
    observed = sample_targets(engine, state)
    assert observed["A1"] == pytest.approx(125 / 300, abs=0.03)
    assert observed["A2"] == pytest.approx(75 / 300, abs=0.03)
    assert observed["A3"] == pytest.approx(100 / 300, abs=0.03)


def test_uniform_selection_ignores_aggro():
    """Bounce 계열처럼 어그로를 무시하는 공격."""
    engine, state = make(seed=99)
    observed = sample_targets(engine, state, selection="uniform")
    for uid in ("A1", "A2", "A3"):
        assert observed[uid] == pytest.approx(1 / 3, abs=0.03)


def test_taunted_ally_is_actually_targeted_far_more():
    engine, state = make(seed=7)
    status.apply_effect(engine, state, state.unit("A2"), "test_taunt")
    observed = sample_targets(engine, state)
    assert observed["A2"] == pytest.approx(450 / 675, abs=0.03)


def test_selection_is_deterministic_for_a_seed():
    runs = []
    for _ in range(2):
        engine, state = make(seed=31)
        allies = state.living(Side.ALLY)
        runs.append([aggro.select_target(state, allies).uid for _ in range(30)])
    assert runs[0] == runs[1]
    assert len(set(runs[0])) > 1  # 실제로 갈린다


def test_enemy_behavior_uses_aggro_by_default():
    engine, state = make(seed=2026)
    hits = {"A1": 0, "A2": 0, "A3": 0}
    for _ in range(600):
        action = engine.choose_action(state, "E1")
        assert isinstance(action, BasicAttackAction)
        hits[action.target_uid] += 1
    total = sum(hits.values())
    assert hits["A1"] / total == pytest.approx(125 / 300, abs=0.05)
    assert hits["A2"] / total == pytest.approx(75 / 300, abs=0.05)


def test_lowest_hp_selection_is_deterministic():
    engine, state = make()
    state.unit("A3").current_hp = 1.0
    allies = state.living(Side.ALLY)
    assert aggro.select_target(state, allies, "lowest_hp").uid == "A3"


def test_no_living_candidates_returns_none():
    engine, state = make()
    for uid in ("A1", "A2", "A3"):
        state.unit(uid).alive = False
    assert aggro.select_target(state, state.all_units()[:3]) is None
