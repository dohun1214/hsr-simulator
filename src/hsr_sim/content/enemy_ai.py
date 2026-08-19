"""검증용 적 AI 정의.

실제 게임 데이터(`Config/ConfigAI/Monster_*.json`)에서 관찰된 두 가지 형태를
그대로 재현한 예시다. 근거와 통계는 docs/mechanics.md 7장.

1. 고정 스킬 순환 — 613개 템플릿 중 158개가 쓰는 가장 흔한 형태
2. 효용 기반 결정 — 조건 1개 + 점수 1개가 사실상 표준
"""

from __future__ import annotations

from ..battle.ai import AIDecision, EnemyAI
from ..battle.predicates import Predicate
from ..registries import ENEMY_AI

#: 실제 게임의 `Monster_Common_SequenceThree_AI` 에 대응.
#: 순환 목록 자체는 유닛 정의의 `skill_sequence` 에 있다.
COMMON_SEQUENCE = EnemyAI(ai_id="common_sequence", mode="sequence")

#: 카운터로 강공격 주기를 관리하는 형태.
#: 게임 데이터에서 DefineDynamicValue / ByCompareDynamicValue 조합으로 흔히 보인다.
CHARGE_AND_SMASH = EnemyAI(
    ai_id="charge_and_smash",
    mode="decision",
    decisions=(
        AIDecision(
            name="Smash",
            skill_id="smash",
            score=1.0,
            predicate=Predicate("counter", {"key": "charge", "op": ">=", "value": 2}),
            cooldown=3,
            counter_ops=(("charge", "set", 0.0),),
        ),
        AIDecision(
            name="Enrage",
            skill_id="enrage",
            score=0.9,
            predicate=Predicate("hp_below", {"value": 0.5}),
            cooldown=99,
        ),
        AIDecision(
            name="Charge",
            skill_id="basic",
            score=0.5,
            predicate=Predicate("always"),
            counter_ops=(("charge", "add", 1.0),),
        ),
    ),
)

#: 페이즈에 따라 쓸 수 있는 스킬이 달라지는 형태.
PHASE_BOSS = EnemyAI(
    ai_id="phase_boss",
    mode="decision",
    decisions=(
        AIDecision(
            name="Phase2Nuke",
            skill_id="nuke",
            score=1.0,
            predicate=Predicate("phase_is", {"phases": (2,)}),
            cooldown=2,
        ),
        AIDecision(
            name="Basic",
            skill_id="basic",
            score=0.5,
            predicate=Predicate("always"),
        ),
    ),
)


for _ai in (COMMON_SEQUENCE, CHARGE_AND_SMASH, PHASE_BOSS):
    ENEMY_AI.register(_ai.ai_id, _ai)
