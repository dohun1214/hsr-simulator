"""특성/패시브 (Ability).

Ability 는 **이벤트 구독만으로** 동작한다. 엔진 코어를 수정하지 않는다.

    class MyAbility:
        def bind(self, bus, owner_uid): ...

향후 캐릭터 고유 패시브, 행적, 광추 효과, 유물 세트 효과, 보스 기믹이
모두 이 인터페이스로 들어온다. 거대한 if/else 가 생기지 않는 이유가 이것이다.
"""

from __future__ import annotations

from typing import Protocol

from ..core.events import EventBus


class Ability(Protocol):
    """이벤트 버스에 자신을 등록하는 객체."""

    def bind(self, bus: EventBus, owner_uid: str) -> None:  # pragma: no cover - 프로토콜
        ...
