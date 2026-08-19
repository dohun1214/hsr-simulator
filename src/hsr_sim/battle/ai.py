"""적의 행동 패턴 (AI).

실제 게임 데이터(`Config/ConfigAI/Monster_*.json`)의 구조를 그대로 모델링한다.
근거와 통계는 docs/mechanics.md 7장, 데이터 출처는 docs/data_sources.md.

게임의 AI 는 두 형태로 요약된다.

1. **고정 스킬 순환** — 613개 템플릿 중 158개가 쓰는 가장 흔한 형태.
   `AISkillSequence` 의 스킬을 순서대로 반복한다.
2. **효용 기반 결정(DefaultDSE)** — 각 결정이 조건을 평가해 점수를 내고,
   점수가 가장 높은 결정을 실행한다. 결정당 조건은 사실상 1개다.

두 형태를 하나의 `EnemyAI` 로 표현한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from ..registries import ENEMY_AI, UNIT_DEFINITIONS
from .predicates import Predicate

#: 게임 데이터에서 가장 흔한 점수. docs/mechanics.md 7.1
DEFAULT_DECISION_SCORE = 0.5


@dataclass(frozen=True)
class AIDecision:
    """결정 하나 = 조건 + 점수 + 실행할 스킬."""

    name: str
    skill_id: str
    score: float = DEFAULT_DECISION_SCORE
    predicate: Optional[Predicate] = None
    #: 재사용까지 필요한 자신의 턴 수. 1 이하면 매 턴 사용 가능.
    cooldown: int = 1
    initial_cooldown: int = 1
    #: 사용 가능한 페이즈. 비어 있으면 제한 없음.
    phases: Tuple[int, ...] = ()
    #: 대상 선택 방식 오버라이드 (None 이면 스킬의 TargetRule 을 따른다)
    target_selection: Optional[str] = None
    #: 실행 후 카운터 조작: (key, op, value). op 는 "set" 또는 "add".
    counter_ops: Tuple[Tuple[str, str, float], ...] = ()


@dataclass(frozen=True)
class EnemyAI:
    """하나의 적 AI 정의.

    ``mode``
      - ``"sequence"``: `skill_sequence` 를 순서대로 반복 (가장 흔한 형태)
      - ``"decision"``: `decisions` 중 점수가 가장 높은 것을 실행
    """

    ai_id: str
    mode: str = "sequence"
    decisions: Tuple[AIDecision, ...] = ()


def ready(unit, skill_id: str) -> bool:
    return unit.skill_cooldowns.get(skill_id, 0) <= 0


def start_cooldowns(unit, ai: Optional[EnemyAI]) -> None:
    """전투 시작 시 초기 쿨다운을 건다.

    게임 데이터의 `InitialCD` 는 "첫 사용까지 필요한 턴 수" 로 해석한다.
    1 이면 첫 턴부터 사용 가능. **[유도됨]** docs/mechanics.md 7.7
    """
    if ai is None:
        return
    for decision in ai.decisions:
        unit.skill_cooldowns[decision.skill_id] = max(0, decision.initial_cooldown - 1)


def tick_cooldowns(unit) -> None:
    """소유자의 턴이 끝날 때 쿨다운을 1 줄인다. **[유도됨]**"""
    for key in list(unit.skill_cooldowns):
        if unit.skill_cooldowns[key] > 0:
            unit.skill_cooldowns[key] -= 1


def _apply_counter_ops(unit, decision: AIDecision) -> None:
    for key, op, value in decision.counter_ops:
        if op == "set":
            unit.counters[key] = value
        else:
            unit.counters[key] = unit.counters.get(key, 0.0) + value


def _skill_available(state, unit, skill_id: str) -> bool:
    definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
    if definition is None:
        return False
    skill = definition.skills.get(skill_id)
    if skill is None:
        return False
    if skill.phases and unit.phase not in skill.phases:
        return False
    return True


def choose_sequenced_skill(state, unit) -> Optional[str]:
    """고정 순환에서 다음 스킬을 고른다.

    현재 페이즈에서 쓸 수 없는 스킬은 건너뛴다.
    시작 위치와 되감기 규칙은 데이터에 없어 0번부터 순환한다. **[미확인]**
    """
    definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
    if definition is None or not definition.skill_sequence:
        return None
    sequence = definition.skill_sequence
    for offset in range(len(sequence)):
        index = (unit.sequence_index + offset) % len(sequence)
        skill_id = sequence[index]
        if _skill_available(state, unit, skill_id):
            unit.sequence_index = (index + 1) % len(sequence)
            return skill_id
    return None


def choose_decision(state, unit, ai: EnemyAI) -> Optional[AIDecision]:
    """점수가 가장 높은 결정을 고른다.

    동점일 때는 목록에서 먼저 오는 것을 쓴다 (게임 데이터의 점수는 0.5 가
    압도적으로 많아 동점이 흔하다). 동점 규칙은 **[미확인]**.
    """
    best: Optional[AIDecision] = None
    best_score = float("-inf")
    for decision in ai.decisions:
        if decision.phases and unit.phase not in decision.phases:
            continue
        if not ready(unit, decision.skill_id):
            continue
        if not _skill_available(state, unit, decision.skill_id):
            continue
        if decision.predicate is not None and not decision.predicate.evaluate(state, unit):
            continue
        if decision.score > best_score:
            best, best_score = decision, decision.score
    return best


def decide(state, unit) -> Optional[str]:
    """이 유닛이 이번 턴에 쓸 스킬 id. 부수효과(쿨다운/카운터)도 여기서 처리한다."""
    definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
    ai = ENEMY_AI.try_get(definition.ai_id) if definition and definition.ai_id else None

    if ai is None or ai.mode == "sequence":
        return choose_sequenced_skill(state, unit)

    decision = choose_decision(state, unit, ai)
    if decision is None:
        return choose_sequenced_skill(state, unit)
    unit.skill_cooldowns[decision.skill_id] = max(0, decision.cooldown - 1)
    _apply_counter_ops(unit, decision)
    return decision.skill_id


def decision_for(state, unit, skill_id: str) -> Optional[AIDecision]:
    definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
    ai = ENEMY_AI.try_get(definition.ai_id) if definition and definition.ai_id else None
    if ai is None:
        return None
    for decision in ai.decisions:
        if decision.skill_id == skill_id:
            return decision
    return None
