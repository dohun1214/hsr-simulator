#!/usr/bin/env python3
"""붕괴: 스타레일 게임 데이터에서 적(몬스터) 데이터를 가져온다.

원본: https://github.com/DimbreathBot/TurnBasedGameData
필드 조사 결과와 무엇을 가져올 수 있고 없는지는 docs/data_sources.md 참고.

사용법
------
    # 필요한 파일만 받아서 임포트 (네트워크 필요)
    python tools/import_monsters.py --fetch

    # 이미 받아 둔 저장소에서 임포트
    python tools/import_monsters.py --source /path/to/TurnBasedGameData

    # HSRMaps 와 대조 검증
    python tools/import_monsters.py --source ... --validate /path/to/HSRMaps

출력
----
`data/monsters.json.gz` — 레벨을 고정하지 않고 **기본값 + 배율 표**를 저장한다.
런타임 로더가 원하는 레벨로 계산한다.

**가져오지 못하는 것**: 적 스킬의 피해 배율.
게임 데이터에서 배율은 능력(Ability) 설정의 동적 표현식으로 들어 있고,
그 표현식이 참조하는 이름이 해시로만 남아 있어 복원하지 못했다.
`params` 는 원본 그대로 보존하고 `multiplier` 는 null 로 둔다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional

REPO = "https://github.com/DimbreathBot/TurnBasedGameData.git"

#: 임포트에 필요한 파일만 받는다 (전체 저장소는 매우 크다)
NEEDED_FILES = [
    "ExcelOutput/MonsterConfig.json",
    "ExcelOutput/MonsterTemplateConfig.json",
    "ExcelOutput/MonsterSkillConfig.json",
    "ExcelOutput/HardLevelGroup.json",
    "ExcelOutput/EliteGroup.json",
    "TextMap/TextMapEN.json",
    "TextMap/TextMapKR_0.json",
    "TextMap/TextMapKR_1.json",
]

#: 게임 데이터의 속성명 -> 우리 열거형 값
ELEMENTS = {
    "Physical": "physical",
    "Fire": "fire",
    "Ice": "ice",
    "Thunder": "lightning",
    "Wind": "wind",
    "Quantum": "quantum",
    "Imaginary": "imaginary",
}

#: SkillTag(영문) -> (대상 형태, 대상 선택 방식)
#: 근거: docs/mechanics.md 6.4, 7.4
SKILL_TAG_SHAPE = {
    "Single Target": ("single", "aggro"),
    "AoE ATK": ("aoe", "aggro"),
    "Blast": ("blast", "aggro"),
    "Bounce": ("single", "uniform"),   # 어그로를 무시한다
    "Lock On": ("single", "lock_on"),  # 특정 대상 지정 (미구현)
    "Sweep": ("aoe", "aggro"),
}


def value(node: Any, default: float = 0.0) -> float:
    """게임 데이터의 {"Value": x} 래퍼를 벗긴다."""
    if isinstance(node, dict):
        return float(node.get("Value", default))
    if node is None:
        return default
    return float(node)


class TextMap:
    """해시 -> 현지화 문자열."""

    def __init__(self, files: Iterable[str]) -> None:
        self.table: Dict[str, str] = {}
        for path in files:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fp:
                    self.table.update(json.load(fp))

    def get(self, node: Any) -> Optional[str]:
        if not isinstance(node, dict):
            return None
        text = self.table.get(str(node.get("Hash")))
        if text is None:
            return None
        # 게임 텍스트는 줄바꿈 없는 공백(U+00A0)을 쓴다
        return text.replace(" ", " ").strip()


def fetch(cache: str) -> str:
    """필요한 파일만 sparse checkout 한다."""
    if not os.path.isdir(os.path.join(cache, ".git")):
        os.makedirs(cache, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", REPO, cache],
            check=True,
        )
    subprocess.run(["git", "-C", cache, "sparse-checkout", "init", "--no-cone"], check=True)
    subprocess.run(
        ["git", "-C", cache, "sparse-checkout", "set", "--no-cone", *[f"/{f}" for f in NEEDED_FILES]],
        check=True,
    )
    subprocess.run(["git", "-C", cache, "checkout", "HEAD"], check=True)
    return cache


def load(source: str, name: str) -> Any:
    path = os.path.join(source, name)
    if not os.path.exists(path):
        raise SystemExit(f"필요한 파일이 없습니다: {path}\n--fetch 로 받으시거나 --source 를 확인하세요.")
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def build_level_scaling(hard_rows: List[dict], elite_rows: List[dict]) -> Dict[str, Any]:
    """레벨/등급 배율 표.

    적 스탯 = 기본값 x HardLevelGroup 배율 x EliteGroup 배율 x 개체 배율
    **[유도됨]** — 필드명과 값 분포로부터의 해석이다. docs/data_sources.md 참고.
    """
    hard: Dict[str, Dict[str, Dict[str, float]]] = {}
    for row in hard_rows:
        group = str(row["HardLevelGroup"])
        level = str(row["Level"])
        entry = {
            "atk": value(row.get("AttackRatio"), 1.0),
            "def": value(row.get("DefenceRatio"), 1.0),
            "hp": value(row.get("HPRatio"), 1.0),
            "spd": value(row.get("SpeedRatio"), 1.0),
            "stance": value(row.get("StanceRatio"), 1.0),
        }
        # 고레벨에서만 존재한다 (60렙 0.04 -> 80렙 0.1)
        if "StatusResistance" in row:
            entry["status_res"] = value(row["StatusResistance"])
        if "StatusProbability" in row:
            entry["status_prob"] = value(row["StatusProbability"])
        hard.setdefault(group, {})[level] = entry

    elite = {
        str(row["EliteGroup"]): {
            "atk": value(row.get("AttackRatio"), 1.0),
            "def": value(row.get("DefenceRatio"), 1.0),
            "hp": value(row.get("HPRatio"), 1.0),
            "spd": value(row.get("SpeedRatio"), 1.0),
            "stance": value(row.get("StanceRatio"), 1.0),
        }
        for row in elite_rows
    }
    return {"hard_level": hard, "elite": elite}


def convert_skill(raw: dict, en: TextMap, ko: TextMap) -> dict:
    tag_en = en.get(raw.get("SkillTag"))
    shape, selection = SKILL_TAG_SHAPE.get(tag_en, (None, None))
    return {
        "id": raw["SkillID"],
        "trigger": raw.get("SkillTriggerKey"),
        "name": {"ko": ko.get(raw.get("SkillName")), "en": en.get(raw.get("SkillName"))},
        "tag": {"ko": ko.get(raw.get("SkillTag")), "en": tag_en},
        "element": ELEMENTS.get(raw.get("DamageType")),
        "shape": shape,
        "selection": selection,
        # 배율은 복원하지 못했다. 원본 파라미터만 보존한다.
        "multiplier": None,
        "params": [value(p) for p in raw.get("ParamList") or []],
        "energy_to_target": value(raw.get("SPHitBase"), 0.0) or None,
        "delay_ratio": value(raw.get("DelayRatio"), 1.0),
        "phases": list(raw.get("PhaseList") or []),
        "is_threat": bool(raw.get("IsThreat")),
        "desc": {"ko": ko.get(raw.get("SkillDesc")), "en": en.get(raw.get("SkillDesc"))},
    }


def convert_monster(raw: dict, template: dict, skills: Dict[int, dict], en: TextMap, ko: TextMap) -> dict:
    """스킬은 여러 적이 공유하므로 id 만 참조하고 본문은 최상위에 한 번만 둔다."""
    ko_name = ko.get(raw.get("MonsterName")) or ko.get(template.get("MonsterName"))
    en_name = en.get(raw.get("MonsterName")) or en.get(template.get("MonsterName"))
    stance_type = template.get("StanceType")

    return {
        "id": raw["MonsterID"],
        "template_id": raw["MonsterTemplateID"],
        "name": {"ko": ko_name, "en": en_name, "ko_verified": ko_name is not None},
        "rank": template.get("Rank"),
        "hard_level_group": raw.get("HardLevelGroup"),
        "elite_group": raw.get("EliteGroup"),
        "base": {
            "hp": value(template.get("HPBase")),
            "atk": value(template.get("AttackBase")),
            "def": value(template.get("DefenceBase")),
            "spd": value(template.get("SpeedBase")),
            "stance": value(template.get("StanceBase")),
            "crit_dmg": value(template.get("CriticalDamageBase")),
            "status_res": value(template.get("StatusResistanceBase")),
        },
        "ratio": {
            "hp": value(raw.get("HPModifyRatio"), 1.0),
            "atk": value(raw.get("AttackModifyRatio"), 1.0),
            "def": value(raw.get("DefenceModifyRatio"), 1.0),
            "spd": value(raw.get("SpeedModifyRatio"), 1.0),
            "stance": value(raw.get("StanceModifyRatio"), 1.0),
        },
        "stance_count": template.get("StanceCount"),
        "element": ELEMENTS.get(stance_type) if stance_type else None,
        "initial_delay_ratio": value(template.get("InitialDelayRatio"), 1.0),
        "weaknesses": [ELEMENTS[w] for w in raw.get("StanceWeakList") or [] if w in ELEMENTS],
        "resistances": {
            ELEMENTS[r["DamageType"]]: value(r.get("Value"))
            for r in raw.get("DamageTypeResistance") or []
            if r.get("DamageType") in ELEMENTS
        },
        "debuff_res": {
            r["Key"]: value(r.get("Value")) for r in raw.get("DebuffResist") or [] if r.get("Key")
        },
        "summons": list(raw.get("SummonIDList") or []),
        "ai": {
            "path": raw.get("OverrideAIPath") or template.get("AIPath") or None,
            "sequence": [
                sid
                for entry in (raw.get("OverrideAISkillSequence") or template.get("AISkillSequence") or [])
                for sid in (entry.values() if isinstance(entry, dict) else [entry])
            ],
        },
        "skill_ids": [s for s in raw.get("SkillList") or [] if s in skills],
    }


def run_import(source: str) -> dict:
    en = TextMap([os.path.join(source, "TextMap/TextMapEN.json")])
    ko = TextMap(
        [
            os.path.join(source, "TextMap/TextMapKR_0.json"),
            os.path.join(source, "TextMap/TextMapKR_1.json"),
        ]
    )
    monsters = load(source, "ExcelOutput/MonsterConfig.json")
    templates = {t["MonsterTemplateID"]: t for t in load(source, "ExcelOutput/MonsterTemplateConfig.json")}
    raw_skills = load(source, "ExcelOutput/MonsterSkillConfig.json")
    skills = {s["SkillID"]: convert_skill(s, en, ko) for s in raw_skills}

    out = []
    missing_template = 0
    for raw in monsters:
        template = templates.get(raw.get("MonsterTemplateID"))
        if template is None:
            missing_template += 1
            continue
        out.append(convert_monster(raw, template, skills, en, ko))

    commit = subprocess.run(
        ["git", "-C", source, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    return {
        "schema_version": 1,
        "source": {"repo": REPO, "commit": commit or None},
        "notes": {
            "multiplier": (
                "적 스킬의 피해 배율은 가져오지 못했다. 게임 데이터에서 배율은 능력 설정의 "
                "동적 표현식이고 참조 이름이 해시로만 남아 있다. params 는 원본 그대로 보존."
            ),
            "stat_formula": "스탯 = 기본값 x HardLevelGroup 배율 x EliteGroup 배율 x 개체 배율 [유도됨]",
        },
        "level_scaling": build_level_scaling(
            load(source, "ExcelOutput/HardLevelGroup.json"),
            load(source, "ExcelOutput/EliteGroup.json"),
        ),
        "skills": skills,
        "monsters": out,
        "skipped_missing_template": missing_template,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="적 데이터 임포터")
    parser.add_argument("--source", help="TurnBasedGameData 저장소 경로")
    parser.add_argument("--fetch", action="store_true", help="필요한 파일을 직접 받는다 (네트워크 필요)")
    parser.add_argument("--cache", default=os.path.expanduser("~/.cache/hsr-gamedata"))
    parser.add_argument("--out", default="data/monsters.json.gz")
    args = parser.parse_args()

    source = args.source
    if args.fetch:
        source = fetch(args.cache)
    if not source:
        parser.error("--source 또는 --fetch 중 하나가 필요합니다")

    result = run_import(source)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # 8MB 를 넘어가므로 gzip 으로 저장한다 (로더가 그대로 읽는다)
    if args.out.endswith(".gz"):
        import gzip

        with gzip.open(args.out, "wt", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))
    else:
        with open(args.out, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))

    monsters = result["monsters"]
    ko_ok = sum(1 for m in monsters if m["name"]["ko_verified"])
    skills = len(result["skills"])
    size = os.path.getsize(args.out) / 1024 / 1024
    print(f"적 {len(monsters)}종, 고유 스킬 {skills}개 -> {args.out} ({size:.1f} MB)")
    print(f"한국어 공식 명칭 확보: {ko_ok}/{len(monsters)} ({ko_ok / max(1, len(monsters)):.1%})")
    print(f"템플릿 없어 건너뜀: {result['skipped_missing_template']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
