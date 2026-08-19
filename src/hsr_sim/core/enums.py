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
