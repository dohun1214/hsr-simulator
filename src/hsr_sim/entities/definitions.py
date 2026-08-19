"""정적 데이터 정의 (캐릭터/적/스킬 "설계도").

여기 있는 것은 **전투 중에 변하지 않는 데이터**다.
전투 중 변하는 값은 전부 `entities/unit.py` 의 Unit 에 있다.

이 분리는 다음을 위해 필요하다.

- 데이터와 전투 로직의 분리 (요구사항 3)
- BattleState 복제 비용 최소화: 정의는 공유하고 상태만 복제
- 향후 Dimbreath / StarRailRes 등에서 자동 임포트한 데이터를 그대로 꽂기 위함
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from ..core.enums import (
    DamageTag,
    DebuffKind,
    DurationTiming,
    EffectCategory,
    Element,
    Path,
    RefreshPolicy,
    ScalingStat,
    Side,
    SkillKind,
)
from ..stats.stat import Stat, StatModifier


@dataclass(frozen=True)
class LocalizedName:
    """한국어/영어 이름을 항상 함께 관리한다.

    요구사항 6: 영어 이름을 임의로 번역해서 쓰지 않는다.
    공식 한국어 명칭을 확인하지 못한 경우 ``ko_verified=False`` 로 두어
    데이터 검증 시 걸러낼 수 있게 한다.
    """

    ko: str
    en: str
    ko_verified: bool = False

    def __str__(self) -> str:
        return self.ko or self.en


@dataclass(frozen=True)
class TargetRule:
    """스킬이 누구를 때리는지에 대한 규칙.

    V0.1 은 단일 대상만 쓰지만, 확산/전체는 필드 추가만으로 표현되도록
    지금부터 규칙 객체로 분리해 둔다.
    """

    side: str = "enemy"  # "enemy" | "ally" | "self"
    shape: str = "single"  # "single" | "blast" | "aoe"
    #: 자동 선택 시 주 대상을 고르는 방식.
    #:   "aggro"   - 어그로 가중 확률 (적이 아군을 고르는 기본 방식)
    #:   "uniform" - 균등 확률 (Bounce 계열처럼 어그로를 무시하는 공격)
    #:   "lowest_hp" / "highest_hp" - 결정론적 선택
    #: 근거: docs/mechanics.md 6.2, 6.4
    selection: str = "aggro"
    #: blast/aoe 에서 인접 대상에 적용될 배율 (V0.1 미사용)
    adjacent_ratio: float = 0.0


@dataclass(frozen=True)
class SkillDefinition:
    """스킬 1개의 정적 정의.

    ``multiplier`` 는 게임 내 표기 배율(예: 100% -> 1.0).

    자원 관련 필드의 근거는 docs/mechanics.md 3~4장.
    기본값은 게임의 표준값(일반 공격 SP +1 / 에너지 20, 전투 스킬 SP -1 / 에너지 30,
    필살기 에너지 +5)이지만, 캐릭터마다 다른 경우가 있으므로 전부 데이터로 둔다.
    """

    skill_id: str
    name: LocalizedName
    tag: DamageTag
    kind: SkillKind = SkillKind.BASIC_ATK
    element: Optional[Element] = None
    multiplier: float = 1.0
    #: 배율이 신뢰할 수 있는 값인가.
    #: 임포트한 적 스킬은 게임 데이터에서 배율을 복원하지 못해 False 다.
    #: docs/data_sources.md 참고.
    multiplier_verified: bool = True
    #: 확산(blast)에서 인접 대상에 적용할 배율. None 이면 주 대상과 동일.
    adjacent_multiplier: Optional[float] = None
    scaling: ScalingStat = ScalingStat.ATK
    flat_bonus: float = 0.0
    target_rule: TargetRule = field(default_factory=TargetRule)

    #: 스킬 포인트 (양수 = 획득, 양수 소모는 sp_cost 로 표현)
    sp_gain: int = 0
    sp_cost: int = 0

    #: 사용 시 시전자가 얻는 에너지 (ERR 적용 전)
    energy_gain: float = 0.0
    #: 필살기 사용에 필요한 에너지. 0 이면 자원 요구 없음
    energy_cost: float = 0.0
    #: 이 공격에 맞은 대상이 얻는 에너지 (ERR 적용 전).
    #: 자료가 "적에 따라 다르다"고만 하므로 데이터로 둔다. docs/mechanics.md 4.4
    energy_grant_to_target: float = 0.0

    #: 이 스킬 사용 후의 행동 게이지 배수 (게임 데이터의 DelayRatio).
    #: 1.0 이 기본이고 1.5 면 다음 턴이 1.5배 늦게 온다. docs/mechanics.md 7.5
    delay_ratio: float = 1.0
    #: 사용 가능한 페이즈 (게임 데이터의 PhaseList). 비어 있으면 제한 없음.
    phases: Tuple[int, ...] = ()

    #: 이 스킬이 대상에게 거는 상태 효과: (effect_id, 기본 확률)
    inflicts: Tuple[Tuple[str, float], ...] = ()
    #: 이 스킬이 시전자 자신에게 거는 상태 효과
    self_effects: Tuple[str, ...] = ()

    #: 아직 이름이 없는 미래 메커니즘용 확장 슬롯
    extra: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DotSpec:
    """지속 피해 설정. 근거: docs/mechanics.md 5.6"""

    element: Element
    #: 중첩 1개당 배율
    multiplier: float = 0.0
    scaling: ScalingStat = ScalingStat.ATK
    #: 배율에 중첩 수를 곱할지 여부
    per_stack: bool = True


@dataclass(frozen=True)
class StatusEffectDefinition:
    """상태 효과 1개의 정적 정의.

    중첩 상한, 재적용 정책, 지속시간 감소 시점에 **일반 규칙이 없으므로**
    (docs/mechanics.md 5.3, 5.5) 전부 데이터로 둔다.
    """

    effect_id: str
    name: LocalizedName
    category: EffectCategory = EffectCategory.DEBUFF
    debuff_kind: Optional[DebuffKind] = None

    base_duration: int = 2
    max_stacks: int = 1
    refresh: RefreshPolicy = RefreshPolicy.REFRESH
    duration_timing: DurationTiming = DurationTiming.OWNER_TURN_END
    removable: bool = True

    #: 중첩 1개당 적용되는 스탯 수정자
    stat_modifiers: Tuple[StatModifier, ...] = ()
    #: 지속 피해 (없으면 None)
    dot: Optional[DotSpec] = None
    #: 저항 조회에 쓰이는 태그. 게임 데이터의 DebuffResist 키에 대응.
    #: 예: 빙결 -> ("STAT_CTRL", "STAT_CTRL_Frozen"). docs/mechanics.md 7.6
    resist_tags: Tuple[str, ...] = ()

    #: 미래 메커니즘용 확장 슬롯
    extra: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class UnitDefinition:
    """캐릭터/적 공통 정의.

    캐릭터와 적을 굳이 다른 클래스로 나누지 않는다.
    HSR 에서 둘 다 동일한 행동 순서/데미지 규칙을 따르기 때문이며,
    나뉘어 있으면 "적이 아군 스킬 메커니즘을 쓰는" 케이스에서 코드가 갈라진다.
    """

    unit_id: str
    name: LocalizedName
    default_side: Side = Side.ALLY
    element: Element = Element.PHYSICAL
    path: Optional[Path] = None
    base_stats: Dict[Stat, float] = field(default_factory=dict)
    skills: Dict[str, SkillDefinition] = field(default_factory=dict)
    #: 각 슬롯에 대응하는 스킬 id (없으면 None)
    basic_attack_id: str = "basic"
    skill_id: Optional[str] = None
    ultimate_id: Optional[str] = None
    #: 필살기 최대 에너지. 0 이면 에너지 시스템을 쓰지 않는 개체(대부분의 적)
    max_energy: float = 0.0
    #: 적일 때: 약점 속성
    weaknesses: Tuple[Element, ...] = ()
    #: 속성 저항 명시 오버라이드 (미지정 속성은 기본 규칙 적용)
    res_overrides: Dict[Element, float] = field(default_factory=dict)
    #: 최대 인성치 (V0.1 에서는 저장만 하고 사용하지 않음)
    max_toughness: float = 0.0
    #: 기본 어그로 직접 지정 (None 이면 운명의 길에서 결정). docs/mechanics.md 6.1
    base_aggro: Optional[float] = None
    #: 전투 시작 시 행동 게이지 배수 (게임 데이터의 InitialDelayRatio). docs/mechanics.md 7.5
    initial_delay_ratio: float = 1.0
    #: 기본 효과 저항 (게임 데이터의 StatusResistanceBase). 적은 보통 0.1~0.3.
    #: None 이면 적용하지 않는다. docs/mechanics.md 7.6
    status_resistance: Optional[float] = None
    #: 적 AI 정의 id (ENEMY_AI 레지스트리 키)
    ai_id: Optional[str] = None
    #: 고정 스킬 순환 목록 (게임 데이터의 AISkillSequence)
    skill_sequence: Tuple[str, ...] = ()
    #: 유닛 생성 시 `Unit.extra` 로 복사되는 값 (속성별 피해 증가 등)
    extra: Dict[str, Any] = field(default_factory=dict)
    #: 이벤트에 반응하는 패시브/특성 구현 id 목록 (레지스트리 키)
    ability_ids: Tuple[str, ...] = ()
    #: 적 AI / 자동 행동 선택기 id (레지스트리 키)
    behavior_id: str = "basic_attack_aggro"
    #: 상태 이상 **태그**별 저항 (tag -> 저항값).
    #: 게임 데이터의 DebuffResist 가 효과 id 가 아니라 태그 단위다.
    #: 예: {"STAT_CTRL": 1.0, "STAT_DOT_Burn": 0.3}. docs/mechanics.md 7.6
    debuff_res: Dict[str, float] = field(default_factory=dict)
