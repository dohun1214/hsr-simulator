"""HSR Battle Simulator.

패키지를 임포트하면 기본 콘텐츠(테스트 유닛)와 행동 처리기가 등록된다.
"""

__version__ = "0.1.0"

from .battle import engine as _engine  # noqa: F401  (행동 처리기/행동 선택기 등록)
from .content import effects as _effects  # noqa: F401  (테스트 상태 효과 등록)
from .content import dummies as _dummies  # noqa: F401  (테스트 유닛 등록)

from .battle.engine import BattleEngine  # noqa: E402
from .battle.state import BattleConfig, BattleState  # noqa: E402
from .core.enums import BattleOutcome, CritMode, Element, Side  # noqa: E402
from .setup import build_battle, definitions, spawn_unit  # noqa: E402

__all__ = [
    "BattleEngine",
    "BattleConfig",
    "BattleState",
    "BattleOutcome",
    "CritMode",
    "Element",
    "Side",
    "build_battle",
    "definitions",
    "spawn_unit",
]
