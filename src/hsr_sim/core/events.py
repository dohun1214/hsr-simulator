"""전투 이벤트와 이벤트 버스.

트리거 시스템의 기반.
"추가 공격", "턴 시작 시 회복", "피격 시 반격" 같은 것들이 전부
엔진 코드를 수정하지 않고 이벤트 구독으로 붙는다.

핸들러 시그니처: ``handler(engine, state, event) -> None``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class Event:
    """모든 전투 이벤트의 기반 클래스."""

    @property
    def name(self) -> str:
        return type(self).__name__


# --- 전투 흐름 -------------------------------------------------------------


@dataclass
class BattleStart(Event):
    pass


@dataclass
class BattleEnd(Event):
    outcome: Any = None


@dataclass
class CycleStart(Event):
    cycle: int = 1


@dataclass
class TurnStart(Event):
    uid: str = ""


@dataclass
class TurnEnd(Event):
    uid: str = ""


# --- 행동 -----------------------------------------------------------------


@dataclass
class BeforeAction(Event):
    uid: str = ""
    action: Any = None


@dataclass
class AfterAction(Event):
    uid: str = ""
    action: Any = None


# --- 데미지 / HP -----------------------------------------------------------


@dataclass
class BeforeDamage(Event):
    """데미지 계산 직전. 핸들러가 ``ctx`` 를 수정해 배수를 추가할 수 있다."""

    ctx: Any = None


@dataclass
class AfterDamage(Event):
    ctx: Any = None
    result: Any = None


@dataclass
class HpChanged(Event):
    uid: str = ""
    before: float = 0.0
    after: float = 0.0


@dataclass
class UnitDefeated(Event):
    uid: str = ""


# --- 버스 -----------------------------------------------------------------

Handler = Callable[[Any, Any, Event], None]


class EventBus:
    """타입별 구독 버스.

    - 우선순위(priority)가 낮을수록 먼저 실행 (결정론 보장)
    - 동일 우선순위는 등록 순서 유지
    - 버스는 **상태가 아니라 엔진에 속한다**. BattleState 복제 대상이 아니다.
    """

    def __init__(self) -> None:
        self._subs: Dict[type, List[Tuple[int, int, str, Handler]]] = {}
        self._seq = 0

    def subscribe(
        self,
        event_type: type,
        handler: Handler,
        priority: int = 100,
        source: str = "",
    ) -> None:
        self._seq += 1
        bucket = self._subs.setdefault(event_type, [])
        bucket.append((priority, self._seq, source, handler))
        bucket.sort(key=lambda item: (item[0], item[1]))

    def emit(self, engine: Any, state: Any, event: Event) -> Event:
        for event_type in type(event).__mro__:
            for _priority, _seq, _source, handler in list(self._subs.get(event_type, ())):
                handler(engine, state, event)
        return event

    def clear(self) -> None:
        self._subs.clear()
        self._seq = 0
