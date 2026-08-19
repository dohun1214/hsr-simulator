"""자동 행동 선택기 (적 AI 및 아군 기본 정책).

`Behavior` 는 `(engine, state, unit) -> Action` 인 순수 함수처럼 취급한다.
새 AI 패턴은 함수 하나 작성 + 레지스트리 등록으로 추가된다.
"""

from __future__ import annotations

from typing import Optional

from ..entities.definitions import TargetRule
from ..registries import BEHAVIORS
from .actions import Action, BasicAttackAction, SkipAction
from .targeting import candidate_targets


def _basic_attack_rule() -> TargetRule:
    return TargetRule(side="enemy", shape="single")


def basic_attack_random(engine, state, unit) -> Action:
    """살아 있는 적 중 무작위 1명에게 일반 공격.

    난수는 BattleState 의 RNG 를 사용하므로 시드가 같으면 완전히 재현된다.
    """
    targets = candidate_targets(state, unit, _basic_attack_rule())
    if not targets:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
    target = targets[state.rng.randrange(len(targets))]
    return BasicAttackAction(actor_uid=unit.uid, target_uid=target.uid)


def basic_attack_first(engine, state, unit) -> Action:
    """슬롯 순서가 가장 앞인 적을 공격 (결정론적, 테스트용)."""
    targets = candidate_targets(state, unit, _basic_attack_rule())
    if not targets:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
    target = min(targets, key=lambda u: (u.slot, u.uid))
    return BasicAttackAction(actor_uid=unit.uid, target_uid=target.uid)


def basic_attack_lowest_hp(engine, state, unit) -> Action:
    """남은 HP 비율이 가장 낮은 적을 공격."""
    targets = candidate_targets(state, unit, _basic_attack_rule())
    if not targets:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
    target = min(targets, key=lambda u: (u.hp_ratio, u.slot, u.uid))
    return BasicAttackAction(actor_uid=unit.uid, target_uid=target.uid)


BEHAVIORS.register("basic_attack_random", basic_attack_random)
BEHAVIORS.register("basic_attack_first", basic_attack_first)
BEHAVIORS.register("basic_attack_lowest_hp", basic_attack_lowest_hp)


def skill_then_basic(engine, state, unit) -> Action:
    """스킬 포인트가 있으면 전투 스킬, 없으면 일반 공격.

    실제 플레이의 스킬 포인트 운영과는 다르지만, 자원 순환을 결정론적으로
    검증하기에 충분하다. 탐색 단계에서는 이 자리가 평가 기반 정책으로 바뀐다.
    """
    actions = engine.legal_actions(state, unit.uid)
    skills = [a for a in actions if type(a).__name__ == "SkillAction"]
    if skills:
        return skills[0]
    basics = [a for a in actions if type(a).__name__ == "BasicAttackAction"]
    if basics:
        return basics[0]
    return actions[0] if actions else SkipAction(actor_uid=unit.uid, reason="대상 없음")


def basic_only(engine, state, unit) -> Action:
    """항상 일반 공격 (스킬 포인트 절약 정책, 테스트용)."""
    actions = engine.legal_actions(state, unit.uid)
    basics = [a for a in actions if type(a).__name__ == "BasicAttackAction"]
    if basics:
        return basics[0]
    return actions[0] if actions else SkipAction(actor_uid=unit.uid, reason="대상 없음")


BEHAVIORS.register("skill_then_basic", skill_then_basic)
BEHAVIORS.register("basic_only", basic_only)
