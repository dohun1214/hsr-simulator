"""약점 격파로 붙는 7가지 상태 효과.

이름은 게임 데이터 `ExcelOutput/StatusConfig.json` 의 공식 한국어 명칭이다
(StatusID 30020020~30020026). 임의 번역이 아니다.

    물리 -> 열상   화염 -> 연소   얼음 -> 빙결   번개 -> 감전
    바람 -> 풍화   양자 -> 얽힘   허수 -> 속박

수치(피해 배율, 지속 턴, 중첩, 행동 지연)의 근거와 미확인 항목은
docs/mechanics.md 8.6 에 정리했다.

저항 태그는 게임 데이터의 modifier 정의(`MCommon_Element_*`)에 실제로 붙어 있는
`BehaviorFlagList` 를 그대로 옮긴 것이다. 적의 `DebuffResist` 가 이 태그 단위로
걸려 있기 때문에 여기서 지어내면 저항 계산이 통째로 어긋난다.
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


# 열상 — 대상 최대 HP 기준. 정예/보스는 배율이 낮고, 상한이 있다.
BLEED = StatusEffectDefinition(
    effect_id="break_bleed",
    name=_name("열상", "Bleed"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=2,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.PHYSICAL,
        multiplier=0.16,
        elite_multiplier=0.07,
        scaling=ScalingStat.TARGET_MAX_HP,
        per_stack=False,
        cap_break_multiplier=2.0,
        use_break_effect=True,
    ),
    resist_tags=("STAT_DOT", "STAT_DOT_Bleed"),
)

# 연소 — 격파 기본 피해의 1배
BURN = StatusEffectDefinition(
    effect_id="break_burn",
    name=_name("연소", "Burn"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=2,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.FIRE,
        multiplier=1.0,
        scaling=ScalingStat.BREAK_BASE,
        per_stack=False,
        use_break_effect=True,
    ),
    resist_tags=("STAT_DOT", "STAT_DOT_Burn"),
)

# 빙결 — 행동 불가 + 턴 시작 시 얼음 피해. 풀릴 때 다음 턴이 50% 앞당겨진다.
FROZEN = StatusEffectDefinition(
    effect_id="break_frozen",
    name=_name("빙결", "Frozen"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.CROWD_CONTROL,
    base_duration=1,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.ICE,
        multiplier=1.0,
        scaling=ScalingStat.BREAK_BASE,
        per_stack=False,
        use_break_effect=True,
    ),
    resist_tags=("STAT_CTRL", "STAT_CTRL_Frozen", "STAT_CTRL_Frozen_Effect"),
    extra={"expire_action_advance": 0.5},
)

# 감전 — 격파 기본 피해의 2배
SHOCK = StatusEffectDefinition(
    effect_id="break_shock",
    name=_name("감전", "Shock"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=2,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.LIGHTNING,
        multiplier=2.0,
        scaling=ScalingStat.BREAK_BASE,
        per_stack=False,
        use_break_effect=True,
    ),
    resist_tags=("STAT_DOT", "STAT_DOT_Electric"),
)

# 풍화 — 중첩 비례. 일반 1중첩 / 정예·보스 3중첩으로 시작, 최대 5중첩.
WIND_SHEAR = StatusEffectDefinition(
    effect_id="break_wind_shear",
    name=_name("풍화", "Wind Shear"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.DOT,
    base_duration=2,
    max_stacks=5,
    refresh=RefreshPolicy.STACK_AND_REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.WIND,
        multiplier=1.0,
        scaling=ScalingStat.BREAK_BASE,
        per_stack=True,
        use_break_effect=True,
    ),
    resist_tags=("STAT_DOT", "STAT_DOT_Poison"),
)

# 얽힘 — 피격할 때마다 1중첩(최대 5). 자료상 지속 피해로 분류되지는 않지만
# 대상의 턴 시작에 피해를 준다는 점은 같아서 같은 경로로 처리한다.
ENTANGLEMENT = StatusEffectDefinition(
    effect_id="break_entanglement",
    name=_name("얽힘", "Entanglement"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.OTHER,
    base_duration=1,
    max_stacks=5,
    refresh=RefreshPolicy.STACK_AND_REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    dot=DotSpec(
        element=Element.QUANTUM,
        multiplier=0.6,
        scaling=ScalingStat.BREAK_BASE,
        per_stack=True,
        use_toughness_multiplier=True,
        use_break_effect=True,
    ),
    resist_tags=("STAT_CTRL", "STAT_Entangle"),
)

# 속박 — 피해 없음. 행동 지연(격파 처리에서)과 속도 10% 감소.
IMPRISONMENT = StatusEffectDefinition(
    effect_id="break_imprisonment",
    name=_name("속박", "Imprisonment"),
    category=EffectCategory.DEBUFF,
    debuff_kind=DebuffKind.SLOW,
    base_duration=1,
    max_stacks=1,
    refresh=RefreshPolicy.REFRESH,
    duration_timing=DurationTiming.OWNER_TURN_END,
    stat_modifiers=(
        StatModifier(Stat.SPD, ModifierKind.PERCENT_OF_BASE, -0.1, "break_imprisonment"),
    ),
    resist_tags=("STAT_CTRL", "STAT_Confine", "STAT_SpeedDown"),
)


BREAK_EFFECTS = (
    BLEED,
    BURN,
    FROZEN,
    SHOCK,
    WIND_SHEAR,
    ENTANGLEMENT,
    IMPRISONMENT,
)

for _definition in BREAK_EFFECTS:
    STATUS_EFFECTS.register(_definition.effect_id, _definition)
