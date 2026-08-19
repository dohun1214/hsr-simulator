"""스탯 정의와 스탯 계산.

스탯 값은 유닛에 "기본값 + 수정자 목록" 형태로 저장되고,
최종 값은 필요할 때 계산한다.
(버프/디버프가 붙고 떨어질 때 원본을 훼손하지 않기 위해)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Stat(Enum):
    """전투 스탯.

    새 스탯이 게임에 추가되면 여기에 항목만 추가한다.
    """

    MAX_HP = "max_hp"
    ATK = "atk"
    DEF = "def"
    SPD = "spd"
    CRIT_RATE = "crit_rate"
    CRIT_DMG = "crit_dmg"
    BREAK_EFFECT = "break_effect"
    EFFECT_HIT_RATE = "effect_hit_rate"
    EFFECT_RES = "effect_res"
    ENERGY_REGEN_RATE = "energy_regen_rate"
    OUTGOING_HEALING = "outgoing_healing"


STAT_NAMES_KO = {
    Stat.MAX_HP: "HP",
    Stat.ATK: "공격력",
    Stat.DEF: "방어력",
    Stat.SPD: "속도",
    Stat.CRIT_RATE: "치명타 확률",
    Stat.CRIT_DMG: "치명타 피해",
    Stat.BREAK_EFFECT: "약점 격파 특효",
    Stat.EFFECT_HIT_RATE: "효과 명중",
    Stat.EFFECT_RES: "효과 저항",
    Stat.ENERGY_REGEN_RATE: "에너지 회복 효율",
    Stat.OUTGOING_HEALING: "치유량",
}

#: 이 스탯들은 "기본값의 %" 개념이 없고 가산만 존재한다 (치확 +10% 등).
#: 계산식은 동일하지만(퍼센트 기여가 0), 데이터 작성 시 혼동을 막기 위해 명시해 둔다.
ADDITIVE_ONLY_STATS = frozenset(
    {
        Stat.CRIT_RATE,
        Stat.CRIT_DMG,
        Stat.BREAK_EFFECT,
        Stat.EFFECT_HIT_RATE,
        Stat.EFFECT_RES,
        Stat.ENERGY_REGEN_RATE,
        Stat.OUTGOING_HEALING,
    }
)


class ModifierKind(Enum):
    """수정자 적용 방식."""

    #: 기본값에 대한 비율. 여러 개는 서로 가산된다. (HSR 의 일반적인 %버프)
    PERCENT_OF_BASE = "percent_of_base"
    #: 고정 수치 가산.
    FLAT = "flat"


@dataclass
class StatModifier:
    """하나의 스탯 수정자.

    source_id / stack_key 는 향후 버프 갱신·중첩 규칙에서 사용한다.
    V0.1 에서는 단순히 목록에 쌓기만 한다.
    """

    stat: Stat
    kind: ModifierKind
    value: float
    source_id: str = ""
    stack_key: str = ""

    def clone(self) -> "StatModifier":
        return StatModifier(self.stat, self.kind, self.value, self.source_id, self.stack_key)


def compute_stat(
    stat: Stat,
    base: float,
    modifiers: Optional[List[StatModifier]] = None,
) -> float:
    """최종 스탯 = 기본값 x (1 + 퍼센트 합) + 고정값 합.

    HSR 의 스탯 계산 구조를 따른다.
    """
    percent = 0.0
    flat = 0.0
    if modifiers:
        for mod in modifiers:
            if mod.stat is not stat:
                continue
            if mod.kind is ModifierKind.PERCENT_OF_BASE:
                percent += mod.value
            else:
                flat += mod.value
    return base * (1.0 + percent) + flat


StatMap = Dict[Stat, float]


def stat_components(
    stat: Stat,
    base: float,
    modifiers: Optional[List[StatModifier]] = None,
):
    """(기본값, 퍼센트 합, 고정값 합) 을 분리해서 반환.

    데미지 공식의 DEF 계산은

        DEF = Base DEF x (1 + DEF% - (DEF 감소 + DEF 무시)) + Flat DEF

    처럼 **감소/무시가 기본값 쪽에만 곱해지고 고정값에는 곱해지지 않으므로**
    (docs/mechanics.md 2.5) 최종 스탯 하나만으로는 정확히 계산할 수 없다.
    """
    percent = 0.0
    flat = 0.0
    if modifiers:
        for mod in modifiers:
            if mod.stat is not stat:
                continue
            if mod.kind is ModifierKind.PERCENT_OF_BASE:
                percent += mod.value
            else:
                flat += mod.value
    return base, percent, flat
