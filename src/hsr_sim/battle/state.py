"""BattleState: 전투의 모든 가변 상태.

원칙

- **순수 데이터만 들어간다.** 함수/클로저/이벤트 구독은 들어가지 않는다.
- 따라서 `clone()` 이 싸고, 결정론적이며, 미래 상태 탐색에 그대로 쓸 수 있다.
- 동작(패시브, 적 AI, 행동 처리)은 전부 레지스트리에 있고 엔진이 참조한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.enums import BattleOutcome, CritMode, Side
from ..core.rng import RngState
from ..entities.unit import Unit
from .log import BattleLog


#: 전투 시작 시 스킬 포인트. 근거: docs/mechanics.md 3.1
STARTING_SKILL_POINTS = 3
MAX_SKILL_POINTS = 5


@dataclass
class BattleConfig:
    """전투 실행 옵션. 상태가 아니라 엔진 설정이다."""

    crit_mode: CritMode = CritMode.ROLL
    seed: int = 0
    log_enabled: bool = True
    #: 무한 루프 방지 (탐색 중 안전장치)
    max_turns: int = 500
    starting_skill_points: int = STARTING_SKILL_POINTS
    max_skill_points: int = MAX_SKILL_POINTS


@dataclass
class BattleState:
    units: Dict[str, Unit] = field(default_factory=dict)
    #: 등록 순서. 동점 처리와 재현성의 기준 (docs/mechanics.md 1.7)
    order: List[str] = field(default_factory=list)

    #: 아군 파티 공유 스킬 포인트. 근거: docs/mechanics.md 3.1
    skill_points: int = 3
    max_skill_points: int = 5

    elapsed_av: float = 0.0
    cycle: int = 1
    turn_count: int = 0
    active_uid: Optional[str] = None

    rng: RngState = field(default_factory=RngState)
    outcome: BattleOutcome = BattleOutcome.ONGOING
    log: BattleLog = field(default_factory=BattleLog)
    started: bool = False

    #: 미래 메커니즘용 전역 확장 슬롯 (스킬 포인트, 웨이브 정보 등)
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- 조회 ------------------------------------------------------------

    def unit(self, uid: str) -> Unit:
        return self.units[uid]

    def all_units(self) -> List[Unit]:
        return [self.units[uid] for uid in self.order]

    def living(self, side: Optional[Side] = None) -> List[Unit]:
        return [
            unit
            for unit in self.all_units()
            if unit.alive and (side is None or unit.side is side)
        ]

    @property
    def active_unit(self) -> Optional[Unit]:
        return self.units.get(self.active_uid) if self.active_uid else None

    @property
    def is_over(self) -> bool:
        return self.outcome is not BattleOutcome.ONGOING

    # --- 복제 ------------------------------------------------------------

    def clone(self) -> "BattleState":
        """미래 상태 탐색용 복제.

        정의(UnitDefinition)와 레지스트리는 공유하고, 가변 상태만 복사한다.
        """
        return BattleState(
            units={uid: unit.clone() for uid, unit in self.units.items()},
            order=list(self.order),
            skill_points=self.skill_points,
            max_skill_points=self.max_skill_points,
            elapsed_av=self.elapsed_av,
            cycle=self.cycle,
            turn_count=self.turn_count,
            active_uid=self.active_uid,
            rng=self.rng.clone(),
            outcome=self.outcome,
            log=self.log.clone(),
            started=self.started,
            extra=dict(self.extra),
        )
