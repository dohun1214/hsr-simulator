"""임포트한 실제 캐릭터 데이터를 시뮬레이터 정의로 변환한다.

데이터 파일: `data/characters.json.gz` (`tools/import_characters.py` 로 생성)

적과 달리 **스킬 배율을 신뢰할 수 있다.** 게임 스킬 설명의 `#N[i]%` 자리표시자가
`ParamList[N-1]` 에 대응하므로 설명 자체가 배율의 근거다.
추출에 실패한 스킬은 `multiplier_verified=False` 로 남는다.

스탯 계산 (docs/data_sources.md 6장):

    스탯 = 승급 단계의 Base + Add x (레벨 - 1)

여기에는 **캐릭터 본체 스탯만** 들어 있다. 광추/유물/행적은 아직 임포트하지 않았다.
따라서 실제 게임의 최종 스탯과 비교할 때는 그 점을 감안해야 한다.
"""

from __future__ import annotations

import gzip
import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union

from ..core.enums import DamageTag, Element, Path, ScalingStat, Side, SkillKind
from ..entities.definitions import LocalizedName, SkillDefinition, TargetRule, UnitDefinition
from ..registries import UNIT_DEFINITIONS
from ..stats.stat import Stat

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "characters.json.gz",
)

#: 스킬 레벨 기본값.
#: 데이터의 MaxLevel(일반 10 / 스킬·필살기 15)은 성혼까지 포함한 절대 상한이다.
#: 성혼 0 기준의 일반적인 만렙을 기본으로 쓴다. **[유도됨]** — 필요하면 인자로 덮어쓸 것.
DEFAULT_SKILL_LEVELS = {"basic": 6, "skill": 10, "ultimate": 10}

_ELEMENTS = {e.value: e for e in Element}
_PATHS = {p.value: p for p in Path}
_SCALING = {"atk": ScalingStat.ATK, "def": ScalingStat.DEF, "max_hp": ScalingStat.MAX_HP}
_KINDS = {
    "basic": (SkillKind.BASIC_ATK, DamageTag.BASIC_ATK),
    "skill": (SkillKind.SKILL, DamageTag.SKILL),
    "ultimate": (SkillKind.ULTIMATE, DamageTag.ULTIMATE),
}


class CharacterDataUnavailable(RuntimeError):
    """데이터 파일이 없을 때. 임포터를 먼저 돌려야 한다."""


@lru_cache(maxsize=4)
def load_data(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or DEFAULT_DATA_PATH
    if not os.path.exists(path):
        raise CharacterDataUnavailable(
            f"캐릭터 데이터 파일이 없습니다: {path}\n"
            "먼저 `python tools/import_characters.py --fetch` 를 실행하세요."
        )
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fp:
        return json.load(fp)


@lru_cache(maxsize=4)
def _index(path: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
    return {c["id"]: c for c in load_data(path)["characters"]}


def _promotion(character: Dict[str, Any], level: int) -> Dict[str, Any]:
    """해당 레벨을 담당하는 승급 단계."""
    rows = character["promotions"]
    for row in rows:
        if level <= (row["max_level"] or 0):
            return row
    return rows[-1]


def _resolve_level(skill: Dict[str, Any], skill_levels: Union[int, Dict[str, int], None]) -> int:
    if isinstance(skill_levels, int):
        wanted = skill_levels
    else:
        table = {**DEFAULT_SKILL_LEVELS, **(skill_levels or {})}
        wanted = table.get(skill["kind"], 1)
    available = sorted(int(k) for k in skill["levels"])
    if not available:
        return 1
    return max((lv for lv in available if lv <= wanted), default=available[0])


def _skill_definition(
    raw: Dict[str, Any], character: Dict[str, Any], skill_levels: Union[int, Dict[str, int], None]
) -> Optional[SkillDefinition]:
    kind_pair = _KINDS.get(raw["kind"] or "")
    if kind_pair is None:
        return None  # 필드 기술(Maze), 보조 등 전투 밖 스킬
    kind, tag = kind_pair

    level = _resolve_level(raw, skill_levels)
    params = raw["levels"].get(str(level), [])
    index = raw["param_index"]
    multiplier = params[index] if index is not None and index < len(params) else 0.0
    adjacent_index = raw["adjacent_param_index"]
    adjacent = (
        params[adjacent_index]
        if adjacent_index is not None and adjacent_index < len(params)
        else None
    )

    element = _ELEMENTS.get(raw.get("element") or "") or _ELEMENTS.get(character.get("element") or "")
    name = raw.get("name") or {}
    return SkillDefinition(
        skill_id=str(raw["id"]),
        name=LocalizedName(
            ko=name.get("ko") or "", en=name.get("en") or "", ko_verified=bool(name.get("ko"))
        ),
        tag=tag,
        kind=kind,
        element=element,
        multiplier=multiplier,
        multiplier_verified=bool(raw["multiplier_verified"]),
        adjacent_multiplier=adjacent,
        scaling=_SCALING.get(raw.get("scaling") or "atk", ScalingStat.ATK),
        target_rule=TargetRule(side="enemy", shape=raw.get("shape") or "single"),
        sp_cost=int(raw.get("sp_cost") or 0),
        sp_gain=int(raw.get("sp_gain") or 0),
        energy_gain=float(raw.get("energy_gain") or 0.0),
        energy_cost=float(character["max_energy"]) if kind is SkillKind.ULTIMATE else 0.0,
        delay_ratio=float(raw.get("delay_ratio") or 1.0),
        extra={"toughness_damage": float(raw.get("toughness_damage") or 0.0)},
    )


#: 행적 스탯 이름 -> 우리 Stat
_TRACE_STATS = {
    "atk": Stat.ATK, "def": Stat.DEF, "max_hp": Stat.MAX_HP, "spd": Stat.SPD,
    "crit_rate": Stat.CRIT_RATE, "crit_dmg": Stat.CRIT_DMG,
    "effect_res": Stat.EFFECT_RES, "effect_hit_rate": Stat.EFFECT_HIT_RATE,
    "break_effect": Stat.BREAK_EFFECT, "energy_regen_rate": Stat.ENERGY_REGEN_RATE,
    "outgoing_healing": Stat.OUTGOING_HEALING,
}


def major_traces(character_id: int, path: Optional[str] = None) -> List[Dict[str, Any]]:
    """특성(주요 행적) 목록. `affects_damage` 가 True 면 피해 계산에 개입할 수 있다."""
    character = _index(path).get(character_id)
    if character is None:
        raise KeyError(f"등록되지 않은 캐릭터 id: {character_id}")
    return [t for t in character.get("traces") or [] if t["type"] == "major"]


def build_definition(
    character_id: int,
    level: int = 80,
    skill_levels: Union[int, Dict[str, int], None] = None,
    path: Optional[str] = None,
    with_traces: bool = False,
) -> UnitDefinition:
    """실제 캐릭터 하나를 `UnitDefinition` 으로 만든다.

    ``with_traces=True`` 면 **스탯 행적을 모두 찍은 상태**의 보너스를 더한다.
    광추/유물/성혼은 여전히 포함되지 않는다.
    """
    data = load_data(path)
    character = _index(path).get(character_id)
    if character is None:
        raise KeyError(f"등록되지 않은 캐릭터 id: {character_id}")

    promotion = _promotion(character, level)
    step = level - 1

    skills: Dict[str, SkillDefinition] = {}
    slots: Dict[str, str] = {}
    for skill_id in character["skill_ids"]:
        raw = data["skills"].get(str(skill_id))
        if raw is None:
            continue
        definition = _skill_definition(raw, character, skill_levels)
        if definition is None:
            continue
        skills[definition.skill_id] = definition
        slots.setdefault(raw["kind"], definition.skill_id)

    base_stats = {
        Stat.MAX_HP: promotion["hp"]["base"] + promotion["hp"]["add"] * step,
        Stat.ATK: promotion["atk"]["base"] + promotion["atk"]["add"] * step,
        Stat.DEF: promotion["def"]["base"] + promotion["def"]["add"] * step,
        Stat.SPD: promotion["spd"],
        Stat.CRIT_RATE: promotion["crit_rate"],
        Stat.CRIT_DMG: promotion["crit_dmg"],
        Stat.AGGRO: promotion["aggro"],
    }
    extra: Dict[str, Any] = {}
    if with_traces:
        totals = character.get("trace_stat_totals") or {}
        for key, amounts in totals.items():
            stat = _TRACE_STATS.get(key)
            if stat is not None:
                current = base_stats.get(stat, 0.0)
                base_stats[stat] = current * (1.0 + amounts["percent"]) + amounts["flat"]
            elif key.startswith("dmg_"):
                bonus = extra.setdefault("elemental_dmg_bonus", {})
                element = key[len("dmg_"):]
                bonus[element] = bonus.get(element, 0.0) + amounts["flat"] + amounts["percent"]

    name = character["name"]
    return UnitDefinition(
        unit_id=f"character_{character_id}",
        extra=extra,
        name=LocalizedName(
            ko=name.get("ko") or "", en=name.get("en") or "", ko_verified=bool(name.get("ko"))
        ),
        default_side=Side.ALLY,
        element=_ELEMENTS.get(character.get("element") or "") or Element.PHYSICAL,
        path=_PATHS.get(character.get("path") or ""),
        base_stats=base_stats,
        skills=skills,
        basic_attack_id=slots.get("basic", ""),
        skill_id=slots.get("skill"),
        ultimate_id=slots.get("ultimate"),
        max_energy=float(character["max_energy"]),
        behavior_id="skill_then_basic",
    )


def register(
    character_id: int,
    level: int = 80,
    skill_levels: Union[int, Dict[str, int], None] = None,
    path: Optional[str] = None,
    with_traces: bool = False,
) -> UnitDefinition:
    unit_id = f"character_{character_id}"
    existing = UNIT_DEFINITIONS.try_get(unit_id)
    if existing is not None:
        return existing
    definition = build_definition(character_id, level, skill_levels, path, with_traces)
    UNIT_DEFINITIONS.register(unit_id, definition)
    return definition


def search(name: Optional[str] = None, path_: Optional[str] = None,
           data_path: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """한국어/영어 이름 조각이나 운명의 길로 캐릭터를 찾는다."""
    result = []
    for character in load_data(data_path)["characters"]:
        if path_ and character.get("path") != path_:
            continue
        if name:
            haystack = f"{character['name'].get('ko') or ''} {character['name'].get('en') or ''}"
            if name.lower() not in haystack.lower():
                continue
        result.append(character)
        if len(result) >= limit:
            break
    return result
