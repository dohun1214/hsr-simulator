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
from typing import Dict, Optional, Tuple

from ..core.enums import DamageTag, Element, Path, ScalingStat, Side
from ..stats.stat import Stat


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
    #: blast/aoe 에서 인접 대상에 적용될 배율 (V0.1 미사용)
    adjacent_ratio: float = 0.0


@dataclass(frozen=True)
class SkillDefinition:
    """스킬 1개의 정적 정의.

    ``multiplier`` 는 게임 내 표기 배율(예: 100% -> 1.0).
    """

    skill_id: str
    name: LocalizedName
    tag: DamageTag
    element: Optional[Element] = None
    multiplier: float = 1.0
    scaling: ScalingStat = ScalingStat.ATK
    flat_bonus: float = 0.0
    target_rule: TargetRule = field(default_factory=TargetRule)
    #: 향후 확장용: 스킬 포인트 소모/획득, 에너지 획득, 토ughness 감소량 등
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
    #: 기본 공격으로 사용할 스킬 id
    basic_attack_id: str = "basic"
    #: 적일 때: 약점 속성
    weaknesses: Tuple[Element, ...] = ()
    #: 속성 저항 명시 오버라이드 (미지정 속성은 기본 규칙 적용)
    res_overrides: Dict[Element, float] = field(default_factory=dict)
    #: 최대 인성치 (V0.1 에서는 저장만 하고 사용하지 않음)
    max_toughness: float = 0.0
    #: 이벤트에 반응하는 패시브/특성 구현 id 목록 (레지스트리 키)
    ability_ids: Tuple[str, ...] = ()
    #: 적 AI / 자동 행동 선택기 id (레지스트리 키)
    behavior_id: str = "basic_attack_random"
