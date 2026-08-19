"""전투에서 쓰이는 열거형.

새로운 속성/타입이 게임에 추가되면 여기에 항목만 추가하면 되도록,
열거형 값에 로직을 붙이지 않는다.
"""

from __future__ import annotations

from enum import Enum


class Side(Enum):
    """진영."""

    ALLY = "ally"
    ENEMY = "enemy"

    @property
    def opposite(self) -> "Side":
        return Side.ENEMY if self is Side.ALLY else Side.ALLY


class Element(Enum):
    """속성. 한국어 공식 명칭 병기."""

    PHYSICAL = "physical"
    FIRE = "fire"
    ICE = "ice"
    LIGHTNING = "lightning"
    WIND = "wind"
    QUANTUM = "quantum"
    IMAGINARY = "imaginary"


ELEMENT_NAMES_KO = {
    Element.PHYSICAL: "물리",
    Element.FIRE: "화염",
    Element.ICE: "얼음",
    Element.LIGHTNING: "번개",
    Element.WIND: "바람",
    Element.QUANTUM: "양자",
    Element.IMAGINARY: "허수",
}


class Path(Enum):
    """운명의 길."""

    DESTRUCTION = "destruction"
    HUNT = "hunt"
    ERUDITION = "erudition"
    HARMONY = "harmony"
    NIHILITY = "nihility"
    PRESERVATION = "preservation"
    ABUNDANCE = "abundance"
    REMEMBRANCE = "remembrance"


PATH_NAMES_KO = {
    Path.DESTRUCTION: "파멸",
    Path.HUNT: "수렵",
    Path.ERUDITION: "지식",
    Path.HARMONY: "동조",
    Path.NIHILITY: "허무",
    Path.PRESERVATION: "보존",
    Path.ABUNDANCE: "풍요",
    Path.REMEMBRANCE: "기억",
}


class DamageTag(Enum):
    """데미지의 출처 분류.

    데미지 보너스/트리거 조건이 이 태그를 참조한다.
    새로운 종류의 데미지가 추가되면 태그만 추가한다.
    """

    BASIC_ATK = "basic_atk"
    SKILL = "skill"
    ULTIMATE = "ultimate"
    FOLLOW_UP = "follow_up"
    DOT = "dot"
    BREAK = "break"
    ADDITIONAL = "additional"


class SkillKind(Enum):
    """행동 슬롯 분류.

    자원 소모/획득 규칙이 이 값에 따라 달라진다 (docs/mechanics.md 3~4장).
    """

    BASIC_ATK = "basic_atk"
    SKILL = "skill"
    ULTIMATE = "ultimate"
    TALENT = "talent"
    TECHNIQUE = "technique"


class EffectCategory(Enum):
    """상태 효과 대분류. 근거: docs/mechanics.md 5.1"""

    BUFF = "buff"
    DEBUFF = "debuff"
    OTHER = "other"


class DebuffKind(Enum):
    """디버프 하위 분류. 근거: docs/mechanics.md 5.1"""

    CROWD_CONTROL = "crowd_control"
    DOT = "dot"
    SLOW = "slow"
    WEAKEN = "weaken"
    OTHER = "other"


class DurationTiming(Enum):
    """지속시간이 줄어드는 시점.

    게임 자료에 일반 규칙이 없어 효과마다 지정한다. 근거: docs/mechanics.md 5.5
    """

    OWNER_TURN_END = "owner_turn_end"
    OWNER_TURN_START = "owner_turn_start"


class RefreshPolicy(Enum):
    """이미 걸려 있는 효과를 다시 부여할 때의 동작."""

    #: 지속시간만 갱신
    REFRESH = "refresh"
    #: 중첩만 증가 (지속시간 유지)
    STACK = "stack"
    #: 중첩 증가 + 지속시간 갱신
    STACK_AND_REFRESH = "stack_and_refresh"
    #: 이미 있으면 무시
    IGNORE = "ignore"


class ScalingStat(Enum):
    """스킬 배율이 곱해지는 기준 스탯."""

    ATK = "atk"
    DEF = "def"
    MAX_HP = "max_hp"


class CritMode(Enum):
    """치명타 처리 방식.

    ROLL    : RNG로 판정 (실제 전투 재현)
    AVERAGE : 기대값 사용 (탐색/평가 시 분산 제거)
    NEVER   : 항상 비치명타 (테스트용)
    ALWAYS  : 항상 치명타 (테스트용)
    """

    ROLL = "roll"
    AVERAGE = "average"
    NEVER = "never"
    ALWAYS = "always"


class BattleOutcome(Enum):
    ONGOING = "ongoing"
    VICTORY = "victory"
    DEFEAT = "defeat"
    DRAW = "draw"
