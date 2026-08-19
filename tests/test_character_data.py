"""임포트한 실제 캐릭터 데이터 테스트.

적과 달리 스킬 배율을 신뢰할 수 있다 (설명의 #N 이 ParamList[N-1] 에 대응).
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle
from hsr_sim.battle import aggro
from hsr_sim.content import characters, monsters
from hsr_sim.core.enums import Element, Path, SkillKind
from hsr_sim.stats.stat import Stat

MARCH_7TH = 1001
DAN_HENG = 1002
HIMEKO = 1003
ICE_EDGE = 1002011


@pytest.fixture(scope="module")
def data():
    return characters.load_data()


# --- 데이터 ----------------------------------------------------------------


def test_data_loads(data):
    assert data["schema_version"] == 1
    assert len(data["characters"]) >= 90
    assert len(data["skills"]) > 600


def test_every_character_has_a_korean_name(data):
    assert all(c["name"]["ko"] for c in data["characters"])


def test_trailblazer_placeholder_is_resolved(data):
    trailblazers = [c for c in data["characters"] if c["name"].get("is_placeholder")]
    assert trailblazers
    assert all(c["name"]["ko"] == "개척자" for c in trailblazers)


def test_names_have_no_non_breaking_spaces(data):
    assert not any(" " in (c["name"]["ko"] or "") for c in data["characters"])


def test_most_attack_skills_have_verified_multipliers(data):
    attacks = [s for s in data["skills"].values() if s["is_attack"] and s["kind"]]
    verified = [s for s in attacks if s["multiplier_verified"]]
    assert len(verified) / len(attacks) > 0.85


# --- 게임 데이터로 어그로 교차검증 ------------------------------------------


def test_base_aggro_matches_our_path_table(data):
    """`AvatarPromotionConfig.BaseAggro` 로 docs/mechanics.md 6.1 을 직접 검증한다."""
    for character in data["characters"]:
        path = character.get("path")
        if not path or not character["promotions"]:
            continue
        expected = aggro.PATH_BASE_AGGRO[Path(path)]
        for promotion in character["promotions"]:
            assert promotion["aggro"] == pytest.approx(expected), path


# --- 스탯 -----------------------------------------------------------------


def test_dan_heng_level_80_base_stats():
    """스탯 = 승급 단계의 Base + Add x (레벨 - 1)"""
    definition = characters.build_definition(DAN_HENG, level=80)
    stats = definition.base_stats
    assert stats[Stat.MAX_HP] == pytest.approx(882.0)
    assert stats[Stat.ATK] == pytest.approx(546.84)
    assert stats[Stat.DEF] == pytest.approx(396.9)
    assert stats[Stat.SPD] == pytest.approx(110.0)
    assert stats[Stat.CRIT_RATE] == pytest.approx(0.05)
    assert stats[Stat.CRIT_DMG] == pytest.approx(0.5)
    assert definition.max_energy == pytest.approx(100.0)


def test_march_7th_level_80_base_stats():
    stats = characters.build_definition(MARCH_7TH, level=80).base_stats
    assert stats[Stat.MAX_HP] == pytest.approx(1058.4)
    assert stats[Stat.ATK] == pytest.approx(511.56)
    assert stats[Stat.DEF] == pytest.approx(573.3)


def test_lower_level_gives_lower_stats():
    low = characters.build_definition(DAN_HENG, level=1).base_stats
    high = characters.build_definition(DAN_HENG, level=80).base_stats
    assert low[Stat.MAX_HP] < high[Stat.MAX_HP]
    assert low[Stat.ATK] < high[Stat.ATK]


def test_path_and_aggro_are_set():
    definition = characters.build_definition(DAN_HENG)
    assert definition.path is Path.HUNT
    assert definition.base_stats[Stat.AGGRO] == pytest.approx(75.0)
    assert characters.build_definition(MARCH_7TH).base_stats[Stat.AGGRO] == pytest.approx(150.0)


# --- 스킬 -----------------------------------------------------------------


def test_dan_heng_skill_multipliers():
    """설명의 자리표시자로 추출한 배율이 스킬 레벨에 따라 올라간다."""
    lv1 = characters.build_definition(DAN_HENG, skill_levels=1)
    lv10 = characters.build_definition(DAN_HENG, skill_levels=10)

    basic1 = lv1.skills[lv1.basic_attack_id]
    assert basic1.multiplier == pytest.approx(0.5)  # 50% ATK
    assert basic1.multiplier_verified is True
    assert lv10.skills[lv10.basic_attack_id].multiplier > basic1.multiplier

    skill10 = lv10.skills[lv10.skill_id]
    assert skill10.multiplier == pytest.approx(2.6)  # 260% ATK
    ult10 = lv10.skills[lv10.ultimate_id]
    assert ult10.multiplier == pytest.approx(4.0)  # 400% ATK


def test_skill_resource_costs_match_the_game():
    """일반 공격 +1 SP / 에너지 20, 전투 스킬 -1 SP / 에너지 30 (docs/mechanics.md 3~4장)"""
    definition = characters.build_definition(DAN_HENG)
    basic = definition.skills[definition.basic_attack_id]
    skill = definition.skills[definition.skill_id]
    ultimate = definition.skills[definition.ultimate_id]

    assert (basic.sp_gain, basic.sp_cost, basic.energy_gain) == (1, 0, 20.0)
    assert (skill.sp_cost, skill.energy_gain) == (1, 30.0)
    assert ultimate.kind is SkillKind.ULTIMATE
    assert ultimate.energy_cost == pytest.approx(definition.max_energy)


def test_blast_skill_has_an_adjacent_multiplier():
    """히메코의 전투 스킬은 확산이고 인접 대상 배율이 따로 있다."""
    definition = characters.build_definition(HIMEKO, skill_levels=10)
    skill = definition.skills[definition.skill_id]
    assert skill.target_rule.shape == "blast"
    assert skill.adjacent_multiplier is not None
    assert skill.adjacent_multiplier < skill.multiplier


def test_toughness_damage_is_imported():
    definition = characters.build_definition(DAN_HENG)
    basic = definition.skills[definition.basic_attack_id]
    assert basic.extra["toughness_damage"] == pytest.approx(30.0)


# --- 검색 / 전투 -----------------------------------------------------------


def test_search_by_korean_name():
    found = characters.search(name="단항", limit=3)
    assert found and any(c["id"] == DAN_HENG for c in found)


def test_real_party_fights_real_enemy():
    party = [characters.register(cid, level=80) for cid in (DAN_HENG, HIMEKO, MARCH_7TH)]
    enemy = monsters.register(ICE_EDGE, level=80)

    config = BattleConfig(seed=11, crit_mode=CritMode.NEVER, log_enabled=False)
    state = build_battle(party, [enemy, enemy], config=config)
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    outcome = engine.run(state)

    assert state.turn_count > 0
    assert outcome.value in ("victory", "defeat", "draw")
    # 캐릭터는 배율이 있으므로 실제로 피해를 준다
    assert state.unit("E1").current_hp < state.unit("E1").max_hp


def test_unknown_character_raises():
    with pytest.raises(KeyError):
        characters.build_definition(999999)


# --- 행적 -----------------------------------------------------------------

KAFKA = 1005


def test_traces_are_imported(data):
    kafka = next(c for c in data["characters"] if c["id"] == KAFKA)
    kinds = {t["type"] for t in kafka["traces"]}
    assert {"stat", "skill_level", "major"} <= kinds


def test_major_traces_have_korean_text_from_starrailres(data):
    """주요 행적 이름은 원본에서 문자열 키로만 참조되어 StarRailRes 로 보충한다."""
    majors = [t for c in data["characters"] for t in c["traces"] if t["type"] == "major"]
    assert majors
    assert all(t["name"]["ko"] for t in majors)


def test_trace_stat_totals_are_summed(data):
    """스탯 행적을 모두 찍었을 때의 합계."""
    kafka = next(c for c in data["characters"] if c["id"] == KAFKA)
    totals = kafka["trace_stat_totals"]
    assert totals["atk"]["percent"] == pytest.approx(0.56)
    assert totals["effect_hit_rate"]["flat"] == pytest.approx(0.36)
    assert totals["max_hp"]["percent"] == pytest.approx(0.20)


def test_with_traces_increases_stats():
    plain = characters.build_definition(KAFKA, level=80)
    traced = characters.build_definition(KAFKA, level=80, with_traces=True)
    assert traced.base_stats[Stat.ATK] == pytest.approx(plain.base_stats[Stat.ATK] * 1.56)
    assert traced.base_stats[Stat.EFFECT_HIT_RATE] == pytest.approx(0.36)


def test_elemental_damage_traces_go_to_extra():
    """속성 피해 증가 행적은 스탯이 아니라 속성별 보너스로 들어간다."""
    traced = characters.build_definition(MARCH_7TH, level=80, with_traces=True)
    bonus = traced.extra.get("elemental_dmg_bonus") or {}
    assert bonus.get("ice", 0.0) > 0.0


def test_elemental_damage_bonus_reaches_the_damage_pipeline():
    from hsr_sim.setup import spawn_unit

    traced = characters.build_definition(MARCH_7TH, level=80, with_traces=True)
    unit = spawn_unit(traced, "A1", level=80)
    assert unit.extra["elemental_dmg_bonus"]["ice"] > 0.0


def test_damage_affecting_traces_are_flagged(data):
    kafka = next(c for c in data["characters"] if c["id"] == KAFKA)
    flagged = [t for t in kafka["traces"] if t["affects_damage"]]
    assert flagged
    assert all(t["type"] == "major" for t in flagged)


def test_major_traces_helper():
    majors = characters.major_traces(KAFKA)
    assert len(majors) >= 3
    assert any(t["affects_damage"] for t in majors)
