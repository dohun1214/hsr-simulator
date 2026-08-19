"""자동 행동 선택기 (적 AI 및 아군 기본 정책).

`Behavior` 는 `(engine, state, unit) -> Action` 인 순수 함수처럼 취급한다.
새 AI 패턴은 함수 하나 작성 + 레지스트리 등록으로 추가된다.
"""

from __future__ import annotations

from typing import Optional

from ..entities.definitions import TargetRule
from ..registries import BEHAVIORS, UNIT_DEFINITIONS
from . import aggro
from .actions import Action, BasicAttackAction, SkipAction
from .targeting import candidate_targets


def _basic_attack_rule() -> TargetRule:
    return TargetRule(side="enemy", shape="single")


def _skill_rule(unit, skill_id: str) -> TargetRule:
    definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
    if definition is None:
        return _basic_attack_rule()
    skill = definition.skills.get(skill_id)
    return skill.target_rule if skill is not None else _basic_attack_rule()


def basic_attack_aggro(engine, state, unit) -> Action:
    """스킬의 대상 규칙에 따라 주 대상을 고르고 일반 공격.

    적이 아군을 고를 때의 **기본 동작**이다. 완전 무작위가 아니라
    운명의 길에서 오는 어그로에 비례한 확률로 고른다 (docs/mechanics.md 6장).
    난수는 BattleState 의 RNG 를 쓰므로 시드가 같으면 완전히 재현된다.
    """
    rule = _skill_rule(unit, "basic")
    targets = candidate_targets(state, unit, rule)
    target = aggro.select_target(state, targets, rule.selection)
    if target is None:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
    return BasicAttackAction(actor_uid=unit.uid, target_uid=target.uid)


def basic_attack_random(engine, state, unit) -> Action:
    """살아 있는 적 중 **균등 확률**로 1명에게 일반 공격.

    어그로를 무시하는 Bounce 계열 공격이나 테스트용.
    """
    targets = candidate_targets(state, unit, _basic_attack_rule())
    target = aggro.select_target(state, targets, "uniform")
    if target is None:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
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


BEHAVIORS.register("basic_attack_aggro", basic_attack_aggro)
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


def enemy_ai_behavior(engine, state, unit) -> Action:
    """적의 행동 패턴 정의(`EnemyAI`)에 따라 스킬과 대상을 고른다.

    게임의 AI 구조를 그대로 따른다 (docs/mechanics.md 7장).
    정의가 없으면 일반 공격으로 물러난다.
    """
    from . import ai as enemy_ai
    from .actions import UseSkillAction

    skill_id = enemy_ai.decide(state, unit)
    if skill_id is None:
        return basic_attack_aggro(engine, state, unit)

    rule = _skill_rule(unit, skill_id)
    decision = enemy_ai.decision_for(state, unit, skill_id)
    selection = (decision.target_selection if decision else None) or rule.selection

    targets = candidate_targets(state, unit, rule)
    target = aggro.select_target(state, targets, selection)
    if target is None:
        return SkipAction(actor_uid=unit.uid, reason="대상 없음")
    return UseSkillAction(actor_uid=unit.uid, target_uid=target.uid, skill_id=skill_id)


BEHAVIORS.register("enemy_ai", enemy_ai_behavior)
