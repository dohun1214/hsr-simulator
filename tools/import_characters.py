#!/usr/bin/env python3
"""붕괴: 스타레일 게임 데이터에서 캐릭터를 가져온다.

원본: https://github.com/DimbreathBot/TurnBasedGameData

적 임포터(`import_monsters.py`)와 달리 **스킬 배율을 신뢰할 수 있게 추출할 수 있다.**
캐릭터 스킬 설명에는 `#1[i]%` 같은 자리표시자가 들어 있고, 그 번호가 `ParamList` 의
인덱스에 그대로 대응하기 때문이다. 즉 설명 자체가 배율의 근거가 된다.

    "Deals Wind DMG equal to #1[i]% of Dan Heng's ATK to one enemy."
    ParamList = [0.5]   ->  배율 50% ATK

사용법
------
    python tools/import_characters.py --fetch
    python tools/import_characters.py --source /path/to/TurnBasedGameData
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO = "https://github.com/DimbreathBot/TurnBasedGameData.git"

NEEDED_FILES = [
    "ExcelOutput/AvatarConfig.json",
    "ExcelOutput/AvatarPromotionConfig.json",
    "ExcelOutput/AvatarSkillConfig.json",
    "TextMap/TextMapEN.json",
    "TextMap/TextMapKR_0.json",
    "TextMap/TextMapKR_1.json",
]

ELEMENTS = {
    "Physical": "physical", "Fire": "fire", "Ice": "ice", "Thunder": "lightning",
    "Wind": "wind", "Quantum": "quantum", "Imaginary": "imaginary",
}

#: 게임 내부 직업명 -> 운명의 길
#: `AvatarPromotionConfig.BaseAggro` 로 어그로 값이 직접 확인된다 (docs/mechanics.md 6.1)
PATHS = {
    "Knight": "preservation",   # 보존   150
    "Warrior": "destruction",   # 파멸   125
    "Rogue": "hunt",            # 수렵    75
    "Mage": "erudition",        # 지식    75
    "Shaman": "harmony",        # 동조   100
    "Warlock": "nihility",      # 허무   100
    "Priest": "abundance",      # 풍요   100
    "Memory": "remembrance",    # 기억   100
    "Elation": "elation",       # 환락   100
}

#: AttackType -> 스킬 슬롯
SKILL_KINDS = {"Normal": "basic", "BPSkill": "skill", "Ultra": "ultimate"}

#: SkillEffect -> 대상 형태
SHAPES = {
    "SingleAttack": "single", "AoEAttack": "aoe", "Blast": "blast",
    "Bounce": "single", "Impair": "single",
}
ATTACK_EFFECTS = set(SHAPES)

_OWNER = r"(?:[^#]{0,45}?\s)?"
#: "DMG equal to #N[i]% of X's ATK" / "#N[i]% of X's ATK as ... DMG"
MULTIPLIER_PATTERNS = [
    re.compile(r"DMG equal to #(\d+)\[[^\]]*\]%\s*of\s+" + _OWNER + r"(ATK|DEF|Max HP)", re.I),
    re.compile(r"#(\d+)\[[^\]]*\]%\s*of\s+" + _OWNER + r"(ATK|DEF|Max HP)\s+as\s+\w+\s+DMG", re.I),
]
#: 확산의 인접 대상 배율 ("... to enemies adjacent to it")
ADJACENT_PATTERN = re.compile(
    r"#(\d+)\[[^\]]*\]%\s*of\s+" + _OWNER + r"(?:ATK|DEF|Max HP)[^.]{0,80}?adjacent", re.I
)
SCALING = {"atk": "atk", "def": "def", "max hp": "max_hp"}


def value(node: Any, default: float = 0.0) -> float:
    if isinstance(node, dict):
        return float(node.get("Value", default))
    return default if node is None else float(node)


#: 개척자는 이름이 플레이어 닉네임 자리표시자로 되어 있다.
NICKNAME = {"ko": "개척자", "en": "Trailblazer"}


def _normalize(text: str) -> str:
    """게임 텍스트 정리: U+00A0(줄바꿈 없는 공백)을 일반 공백으로."""
    return text.replace("\u00a0", " ").replace("\u2007", " ").strip()


class TextMap:
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
        return _normalize(text) if text is not None else None


def strip_tags(text: Optional[str]) -> str:
    return re.sub(r"<[^>]+>", "", text or "").replace("\\n", " ")


def fetch(cache: str) -> str:
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


def find_multiplier(desc_en: str) -> Tuple[Optional[int], Optional[str], Optional[int]]:
    """설명에서 (배율 파라미터 인덱스, 기준 스탯, 인접 대상 파라미터 인덱스)를 찾는다.

    설명의 `#N` 이 `ParamList[N-1]` 이라는 점을 이용한다. 찾지 못하면 (None, None, None).
    """
    for pattern in MULTIPLIER_PATTERNS:
        match = pattern.search(desc_en)
        if match:
            index = int(match.group(1)) - 1
            scaling = SCALING.get(match.group(2).lower(), "atk")
            adjacent = ADJACENT_PATTERN.search(desc_en)
            adjacent_index = int(adjacent.group(1)) - 1 if adjacent else None
            if adjacent_index == index:
                adjacent_index = None
            return index, scaling, adjacent_index
    return None, None, None


def convert_skills(rows: List[dict], en: TextMap, ko: TextMap) -> Dict[str, dict]:
    """스킬 id 별로 레벨별 파라미터를 모은다."""
    grouped: Dict[int, List[dict]] = {}
    for row in rows:
        grouped.setdefault(row["SkillID"], []).append(row)

    skills: Dict[str, dict] = {}
    for skill_id, levels in grouped.items():
        levels.sort(key=lambda r: r.get("Level") or 0)
        head = levels[0]
        kind = SKILL_KINDS.get(head.get("AttackType"))
        effect = head.get("SkillEffect")
        desc_en = strip_tags(en.get(head.get("SkillDesc")))
        index, scaling, adjacent_index = find_multiplier(desc_en)

        skills[str(skill_id)] = {
            "id": skill_id,
            "trigger": head.get("SkillTriggerKey"),
            "kind": kind,
            "effect": effect,
            "shape": SHAPES.get(effect, "single"),
            "name": {"ko": ko.get(head.get("SkillName")), "en": en.get(head.get("SkillName"))},
            "type_desc": {
                "ko": ko.get(head.get("SkillTypeDesc")), "en": en.get(head.get("SkillTypeDesc"))
            },
            "element": ELEMENTS.get(head.get("StanceDamageType")),
            "max_level": head.get("MaxLevel"),
            "levels": {
                str(row.get("Level")): [value(p) for p in row.get("ParamList") or []]
                for row in levels
            },
            "param_index": index,
            "adjacent_param_index": adjacent_index,
            "scaling": scaling,
            "multiplier_verified": index is not None,
            "is_attack": effect in ATTACK_EFFECTS,
            "energy_gain": value(head.get("SPBase")) or None,
            "sp_cost": max(0, int(value(head.get("BPNeed"), -1))),
            "sp_gain": max(0, int(value(head.get("BPAdd"), 0))),
            "toughness_damage": (
                value((head.get("ShowStanceList") or [None])[0]) if head.get("ShowStanceList") else None
            ),
            "delay_ratio": value(head.get("DelayRatio"), 1.0),
            "desc": {"ko": ko.get(head.get("SkillDesc")), "en": en.get(head.get("SkillDesc"))},
        }
    return skills


def convert_character(raw: dict, promotions: List[dict], en: TextMap, ko: TextMap) -> dict:
    promotions = sorted(promotions, key=lambda r: r.get("MaxLevel") or 0)
    rarity = raw.get("Rarity") or ""
    name_ko = ko.get(raw.get("AvatarName"))
    name_en = en.get(raw.get("AvatarName"))
    # 개척자는 이름이 플레이어 닉네임 자리표시자다
    placeholder = name_en == "{NICKNAME}"
    if placeholder:
        name_ko, name_en = NICKNAME["ko"], NICKNAME["en"]
    return {
        "id": raw["AvatarID"],
        "name": {"ko": name_ko, "en": name_en, "is_placeholder": placeholder},
        "full_name": {"ko": ko.get(raw.get("AvatarFullName")), "en": en.get(raw.get("AvatarFullName"))},
        "rarity": int(rarity[-1]) if rarity and rarity[-1].isdigit() else None,
        "path": PATHS.get(raw.get("AvatarBaseType")),
        "path_internal": raw.get("AvatarBaseType"),
        "element": ELEMENTS.get(raw.get("DamageType")),
        "max_energy": value(raw.get("SPNeed")),
        "max_promotion": raw.get("MaxPromotion"),
        "promotions": [
            {
                "max_level": row.get("MaxLevel"),
                "hp": {"base": value(row.get("HPBase")), "add": value(row.get("HPAdd"))},
                "atk": {"base": value(row.get("AttackBase")), "add": value(row.get("AttackAdd"))},
                "def": {"base": value(row.get("DefenceBase")), "add": value(row.get("DefenceAdd"))},
                "spd": value(row.get("SpeedBase")),
                "crit_rate": value(row.get("CriticalChance")),
                "crit_dmg": value(row.get("CriticalDamage")),
                "aggro": value(row.get("BaseAggro")),
            }
            for row in promotions
        ],
        "skill_ids": list(raw.get("SkillList") or []),
    }


def run_import(source: str) -> dict:
    en = TextMap([os.path.join(source, "TextMap/TextMapEN.json")])
    ko = TextMap(
        [
            os.path.join(source, "TextMap/TextMapKR_0.json"),
            os.path.join(source, "TextMap/TextMapKR_1.json"),
        ]
    )
    avatars = load(source, "ExcelOutput/AvatarConfig.json")
    promotion_rows: Dict[int, List[dict]] = {}
    for row in load(source, "ExcelOutput/AvatarPromotionConfig.json"):
        promotion_rows.setdefault(row["AvatarID"], []).append(row)

    skills = convert_skills(load(source, "ExcelOutput/AvatarSkillConfig.json"), en, ko)
    characters = [
        convert_character(raw, promotion_rows.get(raw["AvatarID"], []), en, ko) for raw in avatars
    ]

    commit = subprocess.run(
        ["git", "-C", source, "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    return {
        "schema_version": 1,
        "source": {"repo": REPO, "commit": commit or None},
        "notes": {
            "multiplier": (
                "캐릭터 스킬 배율은 설명의 #N 자리표시자가 ParamList[N-1] 에 대응한다는 점으로 "
                "추출했다. 추출에 실패한 스킬은 multiplier_verified=False 다."
            ),
            "stat_formula": "스탯 = 승급 단계의 Base + Add x (레벨 - 1)",
        },
        "characters": characters,
        "skills": skills,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="캐릭터 데이터 임포터")
    parser.add_argument("--source")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--cache", default=os.path.expanduser("~/.cache/hsr-gamedata"))
    parser.add_argument("--out", default="data/characters.json.gz")
    args = parser.parse_args()

    source = fetch(args.cache) if args.fetch else args.source
    if not source:
        parser.error("--source 또는 --fetch 중 하나가 필요합니다")

    result = run_import(source)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    opener = gzip.open if args.out.endswith(".gz") else open
    with opener(args.out, "wt", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False, separators=(",", ":"))

    characters, skills = result["characters"], result["skills"]
    attacks = [s for s in skills.values() if s["is_attack"] and s["kind"]]
    verified = [s for s in attacks if s["multiplier_verified"]]
    ko_ok = sum(1 for c in characters if c["name"]["ko"])
    size = os.path.getsize(args.out) / 1024 / 1024
    print(f"캐릭터 {len(characters)}명, 스킬 {len(skills)}개 -> {args.out} ({size:.1f} MB)")
    print(f"한국어 공식 명칭: {ko_ok}/{len(characters)}")
    print(f"공격 스킬 배율 추출: {len(verified)}/{len(attacks)} ({len(verified)/max(1,len(attacks)):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
