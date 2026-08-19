"""행동(Action) 객체.

Action 은 **의도를 나타내는 순수 데이터**다. 실행 로직은 별도의 처리기에 있다.

이렇게 나눠야
  - 탐색 알고리즘이 행동을 자유롭게 생성/비교/직렬화할 수 있고
  - 새로운 종류의 행동(스킬, 필살기, 추가 공격...)이 처리기 등록만으로 추가된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Action:
    """모든 행동의 기반. frozen 이라 해시 가능하며 탐색 트리 키로 쓸 수 있다."""

    actor_uid: str

    @property
    def kind(self) -> str:
        return type(self).__name__

    def describe(self) -> str:
        return f"{self.actor_uid}: {self.kind}"


@dataclass(frozen=True)
class BasicAttackAction(Action):
    target_uid: str = ""
    skill_id: str = "basic"

    def describe(self) -> str:
        return f"{self.actor_uid} -> {self.target_uid} 일반 공격"


@dataclass(frozen=True)
class SkipAction(Action):
    """행동할 수 없을 때의 안전한 무행동 (예: 유효한 대상이 없음)."""

    reason: str = ""

    def describe(self) -> str:
        return f"{self.actor_uid} 행동 없음 ({self.reason})"
