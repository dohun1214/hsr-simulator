"""V0.3 검증용 상태 효과.

실제 게임의 효과가 아니라 엔진 검증용 가상 효과다.
실제 효과(풍화, 열상, 감전, 동상, 비의 등)는 데이터 임포터와 함께 들어온다.

중첩 상한 / 재적용 정책 / 지속시간 감소 시점은 게임에 일반 규칙이 없어
전부 데이터로 지정한다 (docs/mechanics.md 5.3, 5.5).
"""

from __future__ import annotations

from ..core.enums import (
    DebuffKind,
    DurationTiming,
    EffectCategory,
    Element,
    RefreshPolicy,
    ScalingStat,
)
from ..entities.definitions import DotSpec, LocalizedName, StatusEffectDefinition
from ..registries import STATUS_EFFECTS
from ..stats.stat import ModifierKind, Stat, StatModifier


def _name(ko: str, en: str) -> LocalizedName:
    return LocalizedName(ko=ko, en=en, ko_verified=True)


TEST_ATK_UP = StatusEffectDefinition(
    effect_id="test_atk_up",
    name=_name("테스트 공격력 증가", "Test ATK Up"),
    category=EffectCategory.BUFF,
    base_duration=2,
    max_stacks=3,
    refresh=RefreshPolicy.STACK_AND_REFRESH,
    stat_modifiers=(
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.2, "test_atk_up"),
    ),
)

TEST_DEF_DOWN = StatusEffectDefinition(
    effect_id="test_def_down",
    name=_name("테스트 방어력 감소", "Test DEF Down"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.OTHER,
    base_duration=2,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    stat_modifiers=(
        StatModifier(Stat.DEF, ModifierKind.PERCENT_OF_BASE, -0.3, "test_def_down"),
    ),
)

TEST_SLOW = StatusEffectDefinition(
    effect_id="test_slow",
    name=_name("테스트 감속", "Test Slow"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.SLOW,
    base_duration=2,
    stat_modifiers=(
        StatModifier(Stat.SPD, ModifierKind.PERCENT_OF_BASE, -0.2, "test_slow"),
    ),
)

TEST_STUN = StatusEffectDefinition(
    effect_id="test_stun",
    name=_name("테스트 행동 불능", "Test Stun"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.CROWD_CONTROL,
    base_duration=1,
)

TEST_BURN = StatusEffectDefinition(
    effect_id="test_burn",
    name=_name("테스트 화상", "Test Burn"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=3,
    max_stacks=3,
    refresh=RefreshPolicy.STACK_AND_REFRESH,
    dot=DotSpec(element=Element.FIRE, multiplier=0.5, scaling=ScalingStat.ATK, per_stack=True),
)

TEST_POISON = StatusEffectDefinition(
    effect_id="test_poison",
    name=_name("테스트 중독", "Test Poison"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=3,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    dot=DotSpec(element=Element.QUANTUM, multiplier=0.25, scaling=ScalingStat.ATK),
)

TEST_UNREMOVABLE_MARK = StatusEffectDefinition(
    effect_id="test_unremovable_mark",
    name=_name("테스트 해제 불가 표식", "Test Unremovable Mark"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.OTHER,
    base_duration=-1,  # 무한 지속
    removable=False,
)

TEST_TURN_START_BUFF = StatusEffectDefinition(
    effect_id="test_turn_start_buff",
    name=_name("테스트 턴 시작 감소 버프", "Test Turn-Start Buff"),
    category=EffectCategory.BUFF,
    base_duration=2,
    duration_timing=DurationTiming.OWNER_TURN_START,
    stat_modifiers=(
        StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.1, "test_turn_start_buff"),
    ),
)


for _definition in (
    TEST_ATK_UP,
    TEST_DEF_DOWN,
    TEST_SLOW,
    TEST_STUN,
    TEST_BURN,
    TEST_POISON,
    TEST_UNREMOVABLE_MARK,
    TEST_TURN_START_BUFF,
):
    STATUS_EFFECTS.register(_definition.effect_id, _definition)
