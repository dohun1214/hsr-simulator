"""임포트한 실제 적 데이터를 시뮬레이터 정의로 변환한다.

데이터 파일: `data/monsters.json.gz` (`tools/import_monsters.py` 로 생성)
필드의 의미와 무엇을 가져오지 못했는지는 docs/data_sources.md 참고.

레벨 스케일링은 **로드 시점에** 계산한다. 데이터에는 기본값과 배율 표만 들어 있어
같은 적을 여러 레벨로 만들 수 있다.

    스탯 = 기본값 x 개체 배율 x HardLevelGroup 배율 x EliteGroup 배율

**주의**: 적 스킬의 피해 배율은 게임 데이터에서 복원하지 못했다.
임포트된 스킬은 `multiplier=0.0, multiplier_verified=False` 로 들어온다.
`assume_first_param=True` 를 주면 `params[0]` 을 배율로 가정하지만,
이는 **검증되지 않은 추정**이며 기본값이 아니다.
"""

from __future__ import annotations

import gzip
import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from ..battle.ai import EnemyAI
from ..core.enums import DamageTag, Element, ScalingStat, Side, SkillKind
from ..entities.definitions import LocalizedName, SkillDefinition, TargetRule, UnitDefinition
from ..registries import ENEMY_AI, UNIT_DEFINITIONS
from ..stats.stat import Stat

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "data",
    "monsters.json.gz",
)

#: 임포트한 적은 전부 이 AI 를 쓴다.
#: 게임의 AI 파일(Config/ConfigAI)까지 변환하는 것은 아직 하지 않았으므로,
#: 가장 흔한 형태인 고정 스킬 순환으로 근사한다. docs/mechanics.md 7.2
IMPORTED_AI_ID = "imported_sequence"

_ELEMENTS = {e.value: e for e in Element}


class MonsterDataUnavailable(RuntimeError):
    """데이터 파일이 없을 때. 임포터를 먼저 돌려야 한다."""


@lru_cache(maxsize=4)
def load_data(path: Optional[str] = None) -> Dict[str, Any]:
    path = path or DEFAULT_DATA_PATH
    if not os.path.exists(path):
        raise MonsterDataUnavailable(
            f"적 데이터 파일이 없습니다: {path}\n"
            "먼저 `python tools/import_monsters.py --fetch` 를 실행하세요."
        )
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fp:
        return json.load(fp)


@lru_cache(maxsize=4)
def _index(path: Optional[str] = None) -> Dict[int, Dict[str, Any]]:
    return {m["id"]: m for m in load_data(path)["monsters"]}


def _scaling(
    data: Dict[str, Any],
    monster: Dict[str, Any],
    level: int,
    hard_level_group: Optional[int] = None,
) -> Dict[str, float]:
    """레벨/등급 배율.

    **중요**: `HardLevelGroup` 은 몬스터가 아니라 **스테이지가 지정한다.**
    `MonsterConfig` 상의 값은 전부 1 이지만 `StageConfig` 는 1/2/3 을 쓰며,
    같은 레벨에서도 곡선이 크게 다르다 (Lv80 기준 HP 배수 148 / 428 / 170).
    엔드게임 스테이지의 상당수가 2 또는 3 을 쓴다.

    따라서 특정 스테이지의 적을 재현하려면 `hard_level_group` 을 직접 지정해야 한다.
    지정하지 않으면 몬스터 데이터의 값(=1)을 쓴다. docs/data_sources.md 참고.
    """
    group = hard_level_group if hard_level_group is not None else monster["hard_level_group"]
    hard_table = data["level_scaling"]["hard_level"].get(str(group), {})
    hard = hard_table.get(str(level))
    if hard is None and hard_table:
        # 해당 레벨이 없으면 가장 가까운 낮은 레벨을 쓴다
        levels = sorted(int(k) for k in hard_table)
        closest = max((lv for lv in levels if lv <= level), default=levels[0])
        hard = hard_table[str(closest)]
    hard = hard or {}
    elite = data["level_scaling"]["elite"].get(str(monster["elite_group"]), {})
    return {
        key: hard.get(key, 1.0) * elite.get(key, 1.0)
        for key in ("hp", "atk", "def", "spd", "stance")
    } | {
        "status_res": hard.get("status_res", 0.0),
        "status_prob": hard.get("status_prob", 0.0),
    }


def _skill_definition(raw: Dict[str, Any], assume_first_param: bool) -> SkillDefinition:
    element = _ELEMENTS.get(raw.get("element") or "")
    shape = raw.get("shape") or "single"
    selection = raw.get("selection") or "aggro"
    params = raw.get("params") or []

    multiplier = 0.0
    verified = False
    if assume_first_param and params:
        multiplier = params[0]

    name = raw.get("name") or {}
    return SkillDefinition(
        skill_id=str(raw["id"]),
        name=LocalizedName(
            ko=name.get("ko") or "", en=name.get("en") or "", ko_verified=bool(name.get("ko"))
        ),
        tag=DamageTag.SKILL,
        kind=SkillKind.SKILL,
        element=element,
        multiplier=multiplier,
        multiplier_verified=verified,
        scaling=ScalingStat.ATK,
        target_rule=TargetRule(side="enemy", shape=shape, selection=selection),
        energy_grant_to_target=raw.get("energy_to_target") or 0.0,
        delay_ratio=raw.get("delay_ratio") or 1.0,
        phases=tuple(raw.get("phases") or ()),
    )


def build_definition(
    monster_id: int,
    level: int = 80,
    path: Optional[str] = None,
    assume_first_param: bool = False,
    hard_level_group: Optional[int] = None,
) -> UnitDefinition:
    """실제 적 하나를 `UnitDefinition` 으로 만든다 (레지스트리 등록은 하지 않는다).

    ``hard_level_group`` 은 스테이지가 정하는 스케일링 곡선이다 (`_scaling` 설명 참고).
    """
    data = load_data(path)
    monster = _index(path).get(monster_id)
    if monster is None:
        raise KeyError(f"등록되지 않은 적 id: {monster_id}")

    scale = _scaling(data, monster, level, hard_level_group)
    base, ratio = monster["base"], monster["ratio"]

    def stat(key: str) -> float:
        return base[key] * ratio[key] * scale[key]

    skills_raw = data["skills"]
    skills = {}
    for sid in monster["skill_ids"]:
        raw = skills_raw.get(str(sid))
        if raw is None:
            continue
        skills[str(sid)] = _skill_definition(raw, assume_first_param)

    sequence = tuple(str(s) for s in monster["ai"]["sequence"] if str(s) in skills)
    if not sequence:
        sequence = tuple(skills)

    name = monster["name"]
    return UnitDefinition(
        unit_id=f"monster_{monster_id}",
        name=LocalizedName(
            ko=name.get("ko") or "", en=name.get("en") or "", ko_verified=bool(name.get("ko"))
        ),
        default_side=Side.ENEMY,
        element=_ELEMENTS.get(monster.get("element") or "") or Element.PHYSICAL,
        base_stats={
            Stat.MAX_HP: stat("hp"),
            Stat.ATK: stat("atk"),
            Stat.DEF: stat("def"),
            Stat.SPD: stat("spd"),
            Stat.CRIT_RATE: 0.0,
            Stat.CRIT_DMG: base["crit_dmg"],
            # 레벨에서 오는 보너스가 더해진다 [유도됨]
            Stat.EFFECT_RES: base["status_res"] + scale["status_res"],
            Stat.EFFECT_HIT_RATE: scale["status_prob"],
        },
        skills=skills,
        basic_attack_id=sequence[0] if sequence else "",
        weaknesses=tuple(
            _ELEMENTS[w] for w in monster["weaknesses"] if w in _ELEMENTS
        ),
        res_overrides={
            _ELEMENTS[k]: v for k, v in monster["resistances"].items() if k in _ELEMENTS
        },
        max_toughness=stat("stance"),
        status_resistance=None,  # 위에서 이미 base_stats 에 넣었다
        initial_delay_ratio=monster.get("initial_delay_ratio") or 1.0,
        debuff_res=dict(monster.get("debuff_res") or {}),
        ai_id=IMPORTED_AI_ID,
        skill_sequence=sequence,
        behavior_id="enemy_ai",
        # 몬스터 등급. 열상 배율과 풍화 초기 중첩이 정예/보스 여부로 갈린다.
        extra={"rank": monster.get("rank") or ""},
    )


def register(
    monster_id: int,
    level: int = 80,
    path: Optional[str] = None,
    assume_first_param: bool = False,
    hard_level_group: Optional[int] = None,
) -> UnitDefinition:
    """정의를 만들고 레지스트리에 등록한다. 이미 있으면 그대로 돌려준다."""
    unit_id = f"monster_{monster_id}"
    existing = UNIT_DEFINITIONS.try_get(unit_id)
    if existing is not None:
        return existing
    definition = build_definition(monster_id, level, path, assume_first_param, hard_level_group)
    UNIT_DEFINITIONS.register(unit_id, definition)
    return definition


def search(
    name: Optional[str] = None,
    rank: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """한국어/영어 이름 조각이나 등급으로 적을 찾는다."""
    result = []
    for monster in load_data(path)["monsters"]:
        if rank and monster.get("rank") != rank:
            continue
        if name:
            haystack = f"{monster['name'].get('ko') or ''} {monster['name'].get('en') or ''}"
            if name.lower() not in haystack.lower():
                continue
        result.append(monster)
        if len(result) >= limit:
            break
    return result


if IMPORTED_AI_ID not in ENEMY_AI:
    ENEMY_AI.register(IMPORTED_AI_ID, EnemyAI(ai_id=IMPORTED_AI_ID, mode="sequence"))
