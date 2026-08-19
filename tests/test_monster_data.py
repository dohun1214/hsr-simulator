"""임포트한 실제 적 데이터 테스트.

데이터 파일은 `tools/import_monsters.py` 로 생성해 저장소에 포함되어 있다.
필드의 의미와 한계는 docs/data_sources.md 참고.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.content import monsters
from hsr_sim.core.enums import Element, Side
from hsr_sim.stats.stat import Stat

#: 얼음 서슬 — 가장 단순한 잡몹 (스킬 1개, 배율 없음)
ICE_EDGE = 1002011
#: 쿠쿠리아, 허망의 어머니 — 보스
COCOLIA = 1005010


@pytest.fixture(scope="module")
def data():
    return monsters.load_data()


# --- 데이터 자체 -----------------------------------------------------------


def test_data_file_loads(data):
    assert data["schema_version"] == 1
    assert len(data["monsters"]) > 2000
    assert len(data["skills"]) > 3000


def test_every_monster_has_an_official_korean_name(data):
    """요구사항 6: 영어를 임의 번역하지 않고 공식 한국어 명칭을 쓴다."""
    missing = [m["id"] for m in data["monsters"] if not m["name"]["ko_verified"]]
    assert missing == []


def test_skill_multipliers_are_marked_unresolved(data):
    """게임 데이터에서 적 스킬 배율은 복원하지 못했다.

    조용히 추정값을 넣지 않고 명시적으로 미해결 표시를 유지한다.
    """
    assert all(s["multiplier"] is None for s in data["skills"].values())
    assert "가져오지 못했다" in data["notes"]["multiplier"]


def test_level_scaling_tables_exist(data):
    hard = data["level_scaling"]["hard_level"]
    assert "1" in hard and "80" in hard["1"]
    row = hard["1"]["80"]
    assert row["hp"] == pytest.approx(148.01102)
    assert row["atk"] == pytest.approx(30.684488)
    assert row["status_res"] == pytest.approx(0.1)


# --- 정의 변환 -------------------------------------------------------------


def test_build_definition_applies_level_scaling(data):
    """스탯 = 기본값 x 개체 배율 x HardLevel 배율 x Elite 배율"""
    raw = next(m for m in data["monsters"] if m["id"] == ICE_EDGE)
    definition = monsters.build_definition(ICE_EDGE, level=80)

    hard = data["level_scaling"]["hard_level"][str(raw["hard_level_group"])]["80"]
    elite = data["level_scaling"]["elite"][str(raw["elite_group"])]
    expected_hp = raw["base"]["hp"] * raw["ratio"]["hp"] * hard["hp"] * elite["hp"]
    assert definition.base_stats[Stat.MAX_HP] == pytest.approx(expected_hp)


def test_lower_level_gives_lower_stats():
    low = monsters.build_definition(ICE_EDGE, level=20)
    high = monsters.build_definition(ICE_EDGE, level=80)
    assert low.base_stats[Stat.MAX_HP] < high.base_stats[Stat.MAX_HP]
    assert low.base_stats[Stat.ATK] < high.base_stats[Stat.ATK]


def test_korean_name_is_used(data):
    definition = monsters.build_definition(ICE_EDGE)
    assert definition.name.ko == "얼음 서슬"
    assert definition.name.en == "Ice Edge"
    assert definition.name.ko_verified is True


def test_weaknesses_and_resistances_are_imported():
    definition = monsters.build_definition(ICE_EDGE)
    assert set(definition.weaknesses) == {Element.FIRE, Element.LIGHTNING}
    # 약점이 아닌 속성은 저항 20%
    assert definition.res_overrides[Element.ICE] == pytest.approx(0.2)


def test_boss_has_toughness_and_debuff_resistance():
    definition = monsters.build_definition(COCOLIA)
    assert definition.max_toughness > 0
    # 쿠쿠리아는 빙결과 속박에 완전 저항한다
    assert definition.debuff_res["STAT_CTRL_Frozen"] == pytest.approx(1.0)


def test_enemy_effect_resistance_includes_level_bonus(data):
    """효과 저항 = 템플릿 기본값 + 레벨 보너스 [유도됨]"""
    raw = next(m for m in data["monsters"] if m["id"] == ICE_EDGE)
    definition = monsters.build_definition(ICE_EDGE, level=80)
    expected = raw["base"]["status_res"] + 0.1
    assert definition.base_stats[Stat.EFFECT_RES] == pytest.approx(expected)


def test_skill_shape_comes_from_the_game_skill_tag():
    definition = monsters.build_definition(ICE_EDGE)
    skill = next(iter(definition.skills.values()))
    assert skill.target_rule.shape == "aoe"  # "AoE ATK"
    assert skill.name.ko == "얼음 바람"
    assert skill.energy_grant_to_target == pytest.approx(10.0)


def test_imported_skills_are_flagged_unverified():
    definition = monsters.build_definition(ICE_EDGE)
    for skill in definition.skills.values():
        assert skill.multiplier_verified is False
        assert skill.multiplier == 0.0


def test_assume_first_param_is_opt_in(data):
    plain = monsters.build_definition(ICE_EDGE)
    assumed = monsters.build_definition(
        ICE_EDGE, assume_first_param=True
    )
    assert next(iter(plain.skills.values())).multiplier == 0.0
    assert next(iter(assumed.skills.values())).multiplier > 0.0
    # 추정값이라도 검증됨으로 표시하지 않는다
    assert next(iter(assumed.skills.values())).multiplier_verified is False


# --- 검색 ------------------------------------------------------------------


def test_search_by_korean_name():
    found = monsters.search(name="쿠쿠리아", limit=3)
    assert found
    assert all("쿠쿠리아" in m["name"]["ko"] for m in found)


def test_search_by_rank():
    found = monsters.search(rank="BigBoss", limit=5)
    assert found and all(m["rank"] == "BigBoss" for m in found)


# --- 실제 전투 -------------------------------------------------------------


def test_real_enemy_can_fight():
    """임포트한 적을 실제 전투에 넣을 수 있는가."""
    monsters.register(ICE_EDGE, level=80)
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False, seed=3)
    state = build_battle(
        definitions("test_ally_a", "test_ally_b"),
        definitions(f"monster_{ICE_EDGE}"),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    outcome = engine.run(state)

    enemy = state.unit("E1")
    assert enemy.max_hp > 10000  # 레벨 80 스케일링이 적용됨
    assert outcome.value in ("victory", "defeat", "draw")
    assert state.turn_count > 0


def test_unknown_monster_id_raises():
    with pytest.raises(KeyError):
        monsters.build_definition(999999999)
