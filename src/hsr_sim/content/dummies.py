"""V0.1~V0.2 검증용 테스트 유닛.

주의: 여기 있는 유닛은 **실제 게임 캐릭터/적이 아니다.**
전투 엔진 자체를 검증하기 위한 가상의 개체이며, 이름도 우리가 지은 것이다.

실제 캐릭터/적 데이터는 별도 임포터로 들어올 예정이며,
그때는 반드시 공식 한국어 명칭을 확인해서 `LocalizedName.ko_verified=True` 로 표시한다.
(요구사항 6)

자원 수치(SP +1/-1, 에너지 20/30/5)는 게임의 표준값이다. 근거: docs/mechanics.md 3~4장
"""

from __future__ import annotations

from typing import Optional

from ..core.enums import DamageTag, Element, Path, ScalingStat, Side, SkillKind
from ..entities.definitions import LocalizedName, SkillDefinition, TargetRule, UnitDefinition
from ..registries import UNIT_DEFINITIONS
from ..stats.stat import Stat


def _name(ko: str, en: str) -> LocalizedName:
    return LocalizedName(ko=ko, en=en, ko_verified=True)


def basic_skill(multiplier: float, energy_to_target: float = 0.0) -> SkillDefinition:
    """일반 공격: 스킬 포인트 +1, 에너지 +20"""
    return SkillDefinition(
        skill_id="basic",
        name=_name("테스트 일반 공격", "Test Basic Attack"),
        tag=DamageTag.BASIC_ATK,
        kind=SkillKind.BASIC_ATK,
        multiplier=multiplier,
        target_rule=TargetRule(side="enemy", shape="single"),
        sp_gain=1,
        energy_gain=20.0,
        energy_grant_to_target=energy_to_target,
    )


def combat_skill(
    multiplier: float,
    shape: str = "single",
    adjacent_multiplier: Optional[float] = None,
    inflicts: tuple = (),
    self_effects: tuple = (),
) -> SkillDefinition:
    """전투 스킬: 스킬 포인트 -1, 에너지 +30"""
    return SkillDefinition(
        skill_id="skill",
        name=_name("테스트 전투 스킬", "Test Skill"),
        tag=DamageTag.SKILL,
        kind=SkillKind.SKILL,
        multiplier=multiplier,
        adjacent_multiplier=adjacent_multiplier,
        target_rule=TargetRule(side="enemy", shape=shape),
        sp_cost=1,
        energy_gain=30.0,
        inflicts=inflicts,
        self_effects=self_effects,
    )


def ultimate_skill(
    multiplier: float,
    max_energy: float,
    shape: str = "single",
    inflicts: tuple = (),
) -> SkillDefinition:
    """필살기: 에너지 전량 소모, 사용 후 +5"""
    return SkillDefinition(
        skill_id="ultimate",
        name=_name("테스트 필살기", "Test Ultimate"),
        tag=DamageTag.ULTIMATE,
        kind=SkillKind.ULTIMATE,
        multiplier=multiplier,
        target_rule=TargetRule(side="enemy", shape=shape),
        energy_cost=max_energy,
        energy_gain=5.0,
        inflicts=inflicts,
    )


TEST_ALLY_A = UnitDefinition(
    unit_id="test_ally_a",
    name=_name("테스트 아군 A", "Test Ally A"),
    default_side=Side.ALLY,
    element=Element.PHYSICAL,
    path=Path.DESTRUCTION,
    base_stats={
        Stat.MAX_HP: 1200.0,
        Stat.ATK: 1000.0,
        Stat.DEF: 500.0,
        Stat.SPD: 100.0,
        Stat.CRIT_RATE: 0.5,
        Stat.CRIT_DMG: 1.0,
        Stat.ENERGY_REGEN_RATE: 0.0,
    },
    skills={
        "basic": basic_skill(1.0),
        "skill": combat_skill(2.0),
        "ultimate": ultimate_skill(3.0, max_energy=120.0, shape="aoe"),
    },
    basic_attack_id="basic",
    skill_id="skill",
    ultimate_id="ultimate",
    max_energy=120.0,
    behavior_id="skill_then_basic",
)

TEST_ALLY_B = UnitDefinition(
    unit_id="test_ally_b",
    name=_name("테스트 아군 B", "Test Ally B"),
    default_side=Side.ALLY,
    element=Element.FIRE,
    path=Path.HUNT,
    base_stats={
        Stat.MAX_HP: 1000.0,
        Stat.ATK: 900.0,
        Stat.DEF: 400.0,
        Stat.SPD: 134.0,
        Stat.CRIT_RATE: 0.5,
        Stat.CRIT_DMG: 1.0,
        Stat.ENERGY_REGEN_RATE: 0.0,
    },
    skills={
        "basic": basic_skill(1.1),
        "skill": combat_skill(1.5, shape="blast", adjacent_multiplier=0.75),
        "ultimate": ultimate_skill(4.0, max_energy=110.0),
    },
    basic_attack_id="basic",
    skill_id="skill",
    ultimate_id="ultimate",
    max_energy=110.0,
    behavior_id="basic_attack_lowest_hp",
)

#: 상태 효과 검증용 아군. 스킬로 방어력 감소, 필살기로 화상을 건다.
TEST_ALLY_C = UnitDefinition(
    unit_id="test_ally_c",
    name=_name("테스트 아군 C", "Test Ally C"),
    default_side=Side.ALLY,
    element=Element.WIND,
    path=Path.NIHILITY,
    base_stats={
        Stat.MAX_HP: 1100.0,
        Stat.ATK: 800.0,
        Stat.DEF: 450.0,
        Stat.SPD: 105.0,
        Stat.CRIT_RATE: 0.0,
        Stat.CRIT_DMG: 0.5,
        Stat.EFFECT_HIT_RATE: 0.0,
        Stat.ENERGY_REGEN_RATE: 0.0,
    },
    skills={
        "basic": basic_skill(1.0),
        "skill": combat_skill(1.0, inflicts=(("test_def_down", 1.0),)),
        "ultimate": ultimate_skill(
            1.0, max_energy=100.0, shape="aoe", inflicts=(("test_burn", 1.0),)
        ),
    },
    basic_attack_id="basic",
    skill_id="skill",
    ultimate_id="ultimate",
    max_energy=100.0,
    behavior_id="skill_then_basic",
)

TEST_ENEMY_A = UnitDefinition(
    unit_id="test_enemy_a",
    name=_name("테스트 적 A", "Test Enemy A"),
    default_side=Side.ENEMY,
    element=Element.PHYSICAL,
    base_stats={
        Stat.MAX_HP: 8000.0,
        Stat.ATK: 700.0,
        Stat.DEF: 1000.0,
        Stat.SPD: 90.0,
        Stat.CRIT_RATE: 0.0,
        Stat.CRIT_DMG: 0.5,
    },
    skills={"basic": basic_skill(1.0, energy_to_target=10.0)},
    weaknesses=(Element.PHYSICAL,),
    max_toughness=60.0,
    behavior_id="basic_attack_aggro",
)

TEST_ENEMY_B = UnitDefinition(
    unit_id="test_enemy_b",
    name=_name("테스트 적 B", "Test Enemy B"),
    default_side=Side.ENEMY,
    element=Element.ICE,
    base_stats={
        Stat.MAX_HP: 5000.0,
        Stat.ATK: 600.0,
        Stat.DEF: 800.0,
        Stat.SPD: 110.0,
        Stat.CRIT_RATE: 0.0,
        Stat.CRIT_DMG: 0.5,
    },
    skills={"basic": basic_skill(0.9, energy_to_target=10.0)},
    weaknesses=(Element.FIRE,),
    max_toughness=30.0,
    behavior_id="basic_attack_aggro",
)

TEST_ENEMY_C = UnitDefinition(
    unit_id="test_enemy_c",
    name=_name("테스트 적 C", "Test Enemy C"),
    default_side=Side.ENEMY,
    element=Element.WIND,
    base_stats={
        Stat.MAX_HP: 4000.0,
        Stat.ATK: 550.0,
        Stat.DEF: 800.0,
        Stat.SPD: 95.0,
        Stat.CRIT_RATE: 0.0,
        Stat.CRIT_DMG: 0.5,
    },
    skills={"basic": basic_skill(0.9, energy_to_target=10.0)},
    weaknesses=(Element.FIRE,),
    max_toughness=30.0,
    behavior_id="basic_attack_aggro",
)


for _definition in (
    TEST_ALLY_A,
    TEST_ALLY_B,
    TEST_ALLY_C,
    TEST_ENEMY_A,
    TEST_ENEMY_B,
    TEST_ENEMY_C,
):
    UNIT_DEFINITIONS.register(_definition.unit_id, _definition)
