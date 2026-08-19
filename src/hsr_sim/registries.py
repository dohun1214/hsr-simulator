"""전역 레지스트리 모음.

BattleState 는 문자열 id 만 들고 있고, 실제 구현은 전부 여기 등록된다.

새 메커니즘 추가 절차 (요구사항 11):

    1. 구현 작성 (Ability / Behavior / ActionHandler / DamageStep)
    2. 여기 레지스트리에 등록
    3. 데이터(UnitDefinition)에 id 추가
    4. 테스트 추가

엔진 코어 수정은 필요 없다.
"""

from __future__ import annotations

from typing import Any, Callable

from .core.registry import Registry

#: unit_id -> UnitDefinition
UNIT_DEFINITIONS: Registry[Any] = Registry("유닛 정의")

#: ability_id -> Ability (이벤트 구독으로 동작하는 패시브/특성/버프 로직)
ABILITIES: Registry[Any] = Registry("특성")

#: effect_id -> StatusEffectDefinition
STATUS_EFFECTS: Registry[Any] = Registry("상태 효과")

#: behavior_id -> Behavior (적 AI, 자동 행동 선택기)
BEHAVIORS: Registry[Any] = Registry("행동 선택기")

#: Action 클래스 이름 -> 실행 함수 (engine, state, action) -> None
ACTION_HANDLERS: Registry[Callable[..., Any]] = Registry("행동 처리기")
