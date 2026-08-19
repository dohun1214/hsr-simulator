"""이름 -> 구현체 레지스트리.

확장성 요구사항의 핵심 축.

- BattleState 에는 "무엇을 가지고 있는가"(문자열 id)만 저장한다.
- 실제 동작(패시브, 트리거, 적 AI, 행동 처리기)은 레지스트리에만 존재한다.

이렇게 나누면
  1) 상태 복제가 매우 싸고 안전해지며 (순수 데이터만 복사)
  2) 새로운 메커니즘은 "구현 추가 + 레지스트리 등록"만으로 확장된다.
"""

from __future__ import annotations

from typing import Callable, Dict, Generic, Iterator, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: Dict[str, T] = {}

    def register(self, key: str, item: T) -> T:
        if key in self._items:
            raise KeyError(f"{self._kind} '{key}' 가 이미 등록되어 있습니다")
        self._items[key] = item
        return item

    def decorator(self, key: str) -> Callable[[T], T]:
        def wrap(item: T) -> T:
            self.register(key, item)
            return item

        return wrap

    def get(self, key: str) -> T:
        try:
            return self._items[key]
        except KeyError:
            raise KeyError(f"등록되지 않은 {self._kind}: '{key}'") from None

    def try_get(self, key: str):
        return self._items.get(key)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def keys(self):
        return self._items.keys()
