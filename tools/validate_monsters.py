#!/usr/bin/env python3
"""임포트한 적 데이터를 HSRMaps 와 대조해 검증한다.

요구사항 8: 하나의 데이터 소스를 절대적 진실로 취급하지 않는다.

HSRMaps(FortOfFans)는 Dimbreath 를 가공한 별도 프로젝트이므로,
두 결과가 일치하면 우리 임포터의 필드 매핑이 맞다는 근거가 된다.

    python tools/validate_monsters.py --hsrmaps /path/to/HSRMaps
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
from collections import Counter

ELEMENTS = {
    "Physical": "physical", "Fire": "fire", "Ice": "ice", "Thunder": "lightning",
    "Wind": "wind", "Quantum": "quantum", "Imaginary": "imaginary",
}


def load_ours(path: str) -> dict:
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as fp:
        return json.load(fp)


def close(a, b, tol=1e-4) -> bool:
    if a is None or b is None:
        return a == b
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=1e-6)


def main() -> int:
    parser = argparse.ArgumentParser(description="적 데이터 교차검증")
    parser.add_argument("--ours", default="data/monsters.json.gz")
    parser.add_argument("--hsrmaps", required=True, help="HSRMaps 저장소 경로")
    parser.add_argument("--show", type=int, default=5, help="불일치 예시 출력 개수")
    args = parser.parse_args()

    ours = load_ours(args.ours)
    with open(os.path.join(args.hsrmaps, "en/monster.json"), encoding="utf-8") as fp:
        theirs = json.load(fp)

    skills = ours["skills"]
    mismatches: Counter = Counter()
    info: Counter = Counter()
    examples: dict = {}
    compared = 0
    only_ours = 0

    for monster in ours["monsters"]:
        other = theirs.get(str(monster["id"]))
        if other is None:
            only_ours += 1
            continue
        compared += 1
        stats = other.get("stats", {})

        # HSRMaps 는 개체 배율(*ModifyRatio)을 기본값에 **미리 곱해서** 저장한다.
        # 우리는 기본값과 배율을 분리해 두므로 곱한 값으로 비교해야 한다.
        checks = [
            ("baseHealth", monster["base"]["hp"] * monster["ratio"]["hp"], stats.get("baseHealth")),
            ("baseAttack", monster["base"]["atk"] * monster["ratio"]["atk"], stats.get("baseAttack")),
            ("baseDefense", monster["base"]["def"] * monster["ratio"]["def"], stats.get("baseDefense")),
            ("baseStance", monster["base"]["stance"] * monster["ratio"]["stance"], stats.get("baseStance")),
            ("hardLevelGroup", monster["hard_level_group"], stats.get("hardLevelGroup")),
            ("speed", monster["base"]["spd"] * monster["ratio"]["spd"], stats.get("speed")),
            ("eliteGroup", monster["elite_group"], stats.get("eliteGroup")),
            ("rank", monster["rank"], other.get("rank")),
        ]
        for name, mine, yours in checks:
            if yours is None:
                continue
            # SpeedBase 가 0 인 개체는 스스로 행동하지 않는 부위/소환물이다.
            # HSRMaps 는 이 경우 100 으로 채워 넣으므로 비교에서 제외한다.
            if name == "speed" and mine == 0:
                info["speed_zero"] += 1
                continue
            ok = close(mine, yours) if isinstance(yours, (int, float)) else mine == yours
            if not ok:
                mismatches[name] += 1
                examples.setdefault(name, []).append((monster["id"], mine, yours))

        # 약점
        mine_weak = sorted(monster["weaknesses"])
        yours_weak = sorted(ELEMENTS.get(w, w.lower()) for w in other.get("weakness") or [])
        if mine_weak != yours_weak:
            mismatches["weakness"] += 1
            examples.setdefault("weakness", []).append((monster["id"], mine_weak, yours_weak))

        # 속성 저항
        yours_res = {
            ELEMENTS.get(r["element"], r["element"].lower()): r["value"]
            for r in other.get("resistance") or []
        }
        if any(not close(monster["resistances"].get(k), v) for k, v in yours_res.items()):
            mismatches["resistance"] += 1
            examples.setdefault("resistance", []).append(
                (monster["id"], monster["resistances"], yours_res)
            )

        # 스킬 (에너지/지연/속성)
        theirs_skills = {str(s["id"]): s for s in other.get("skills") or []}
        for sid in monster["skill_ids"]:
            mine_skill = skills[str(sid)] if str(sid) in skills else skills.get(sid)
            yours_skill = theirs_skills.get(str(sid))
            if mine_skill is None or yours_skill is None:
                continue
            if not close(mine_skill["energy_to_target"], yours_skill.get("spGain")):
                mismatches["skill.spGain"] += 1
                examples.setdefault("skill.spGain", []).append(
                    (sid, mine_skill["energy_to_target"], yours_skill.get("spGain"))
                )
            if not close(mine_skill["delay_ratio"], yours_skill.get("delay")):
                mismatches["skill.delay"] += 1
                examples.setdefault("skill.delay", []).append(
                    (sid, mine_skill["delay_ratio"], yours_skill.get("delay"))
                )
            if mine_skill["params"] != [float(p) for p in yours_skill.get("params") or []]:
                mismatches["skill.params"] += 1
                examples.setdefault("skill.params", []).append(
                    (sid, mine_skill["params"], yours_skill.get("params"))
                )

    print(f"대조한 적: {compared}종 (우리에만 있음: {only_ours}종)")
    if info["speed_zero"]:
        print(f"참고: 속도 0 인 개체 {info['speed_zero']}종은 비교에서 제외 (스스로 행동하지 않는 부위/소환물)")
    if not mismatches:
        print("불일치 없음 — 모든 항목이 HSRMaps 와 일치합니다.")
        return 0

    print("\n불일치 항목 (HSRMaps 가 다른 게임 버전에서 생성되었을 수 있음):")
    for name, count in mismatches.most_common():
        print(f"  {name}: {count}건")
        for example in examples[name][: args.show]:
            print(f"      id={example[0]}  ours={example[1]!r}  hsrmaps={example[2]!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
