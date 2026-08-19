"""전투 로그.

두 가지 용도를 동시에 만족해야 한다.

1. 사람이 읽는 전투 기록 / 리플레이 검증
2. 탐색 중에는 **꺼둘 수 있어야 한다** (수만 개 상태를 복제할 때 로그는 순수 비용)

그래서 로그는 BattleState 안의 선택적 컴포넌트이며, ``enabled=False`` 면 아무것도 쌓지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class LogEntry:
    av: float
    cycle: int
    kind: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)

    def format(self) -> str:
        return f"[AV {self.av:7.2f} | C{self.cycle}] {self.message}"


@dataclass
class BattleLog:
    enabled: bool = True
    entries: List[LogEntry] = field(default_factory=list)

    def add(self, av: float, cycle: int, kind: str, message: str, **data: Any) -> None:
        if not self.enabled:
            return
        self.entries.append(LogEntry(av, cycle, kind, message, data))

    def clone(self) -> "BattleLog":
        if not self.enabled:
            return BattleLog(enabled=False)
        return BattleLog(enabled=True, entries=list(self.entries))

    def render(self) -> str:
        return "\n".join(entry.format() for entry in self.entries)
