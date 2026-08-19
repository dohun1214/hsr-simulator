"""BattleState 생성 헬퍼.

정의(UnitDefinition) + 배치 정보 -> 실제 전투 상태.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from .core.enums import Side
from .core.rng import RngState
from .entities.definitions import UnitDefinition
from .entities.unit import ACTION_GAUGE_FULL, Unit
from .registries import UNIT_DEFINITIONS
from .stats.stat import Stat
from .battle.state import BattleConfig, BattleState


def spawn_unit(
    definition: UnitDefinition,
    uid: str,
    side: Optional[Side] = None,
    slot: int = 0,
    level: int = 80,
) -> Unit:
    side = side or definition.default_side
    unit = Unit(
        uid=uid,
        definition_id=definition.unit_id,
        side=side,
        slot=slot,
        level=level,
        base_stats=dict(definition.base_stats),
        weaknesses=frozenset(definition.weaknesses),
        res_overrides=dict(definition.res_overrides),
        debuff_res=dict(definition.debuff_res),
        max_toughness=definition.max_toughness,
        current_toughness=definition.max_toughness,
        action_gauge=ACTION_GAUGE_FULL,
        max_energy=definition.max_energy,
        energy=0.0,
    )
    unit.current_hp = unit.max_hp
    return unit


def build_battle(
    allies: Sequence[UnitDefinition],
    enemies: Sequence[UnitDefinition],
    config: Optional[BattleConfig] = None,
    ally_level: int = 80,
    enemy_level: int = 80,
) -> BattleState:
    """파티/적 정의 목록으로 전투 상태를 만든다.

    등록 순서는 `아군 슬롯 순 -> 적 슬롯 순` 이며, 이것이 동점 처리 기준이 된다
    (docs/mechanics.md 1.7 의 미확인 규칙에 대한 우리의 결정론적 기본값).
    """
    config = config or BattleConfig()
    state = BattleState(
        rng=RngState(seed=config.seed),
        skill_points=min(config.starting_skill_points, config.max_skill_points),
        max_skill_points=config.max_skill_points,
    )
    state.log.enabled = config.log_enabled

    for slot, definition in enumerate(allies):
        unit = spawn_unit(definition, f"A{slot + 1}", Side.ALLY, slot, ally_level)
        state.units[unit.uid] = unit
        state.order.append(unit.uid)

    for slot, definition in enumerate(enemies):
        unit = spawn_unit(definition, f"E{slot + 1}", Side.ENEMY, slot, enemy_level)
        state.units[unit.uid] = unit
        state.order.append(unit.uid)

    return state


def definitions(*unit_ids: str) -> List[UnitDefinition]:
    return [UNIT_DEFINITIONS.get(uid) for uid in unit_ids]
