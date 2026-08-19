"""인성치와 약점 격파.

근거와 무엇이 확인되지 않았는지는 docs/mechanics.md 8장.

확실한 것
  - 인성치는 **약점 속성 공격일 때만** 깎인다 (스킬에 예외 플래그가 있다)
  - 스킬별 인성치 감소량과 적의 최대 인성치는 게임 데이터에 있다
  - 격파 기본 피해는 공격자 레벨별 테이블(`AvatarBreakDamage`)이 원본에 있다
  - 격파되면 범용 피해 감소 0.9 가 1.0 이 된다

확실하지 않은 것 (전부 설정으로 분리했고 기본값은 보수적이다)
  - 격파 피해의 속성 배수, 최대 인성치 배수  -> 기본 미설정이면 격파 피해 0
  - 격파 시 행동 지연 비율
  - 인성치 회복 시점
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..core.enums import DamageTag, Element
from ..core.events import Event
from ..entities.unit import Unit
from ..stats.stat import Stat

#: 공격자 레벨별 격파 기본 피해. 게임 데이터 `ExcelOutput/AvatarBreakDamage.json` 원본.
#: 전체 표는 data/break_base_damage.json 에 있고 여기에는 대표값만 둔다.
#: docs/mechanics.md 8.2
BREAK_BASE_DAMAGE_LV80 = 3767.5535


@dataclass
class BreakEffectSpec:
    """속성별 격파 효과. 수치 근거가 없어 전부 데이터로 둔다."""

    effect_id: Optional[str] = None
    #: 격파 피해에 곱해지는 속성 배수. **근거 없음** — None 이면 격파 피해를 계산하지 않는다.
    damage_multiplier: Optional[float] = None


@dataclass
class BreakConfig:
    """격파 관련 설정.

    수치 근거가 없는 항목은 전부 여기에 모아 두었다.
    기본값은 "모른다"에 가깝게 잡았다 — 격파 피해는 설정하지 않으면 0 이다.
    docs/mechanics.md 8.3
    """

    #: 격파 시 대상의 행동 게이지를 얼마나 뒤로 미는가. **[미확인]**
    action_delay: float = 0.25
    #: 최대 인성치 배수 함수용 계수. **[미확인]** — None 이면 1.0 을 쓴다.
    toughness_multiplier: Optional[float] = None
    #: 속성별 설정
    elements: Dict[Element, BreakEffectSpec] = field(default_factory=dict)
    #: 격파된 대상이 자기 턴을 마치면 인성치를 회복하는가. **[미확인]**
    recover_on_turn_end: bool = True


#: 기본 설정. 격파 피해 배수는 비워 두었다 (근거 없음).
DEFAULT_BREAK_CONFIG = BreakConfig()


# --- 이벤트 -----------------------------------------------------------------


@dataclass
class ToughnessReduced(Event):
    uid: str = ""
    amount: float = 0.0
    remaining: float = 0.0


@dataclass
class WeaknessBroken(Event):
    uid: str = ""
    element: Optional[Element] = None
    break_damage: float = 0.0


@dataclass
class ToughnessRecovered(Event):
    uid: str = ""


# --- 판정 -------------------------------------------------------------------


def has_toughness(unit: Unit) -> bool:
    return unit.max_toughness > 0.0


def can_reduce(unit: Unit, element: Element, ignores_weakness: bool = False) -> bool:
    """이 속성 공격이 인성치를 깎을 수 있는가. 근거: docs/mechanics.md 8.1"""
    if not has_toughness(unit) or unit.toughness_broken:
        return False
    return ignores_weakness or element in unit.weaknesses


def break_base_damage(level: int, table: Optional[Dict[int, float]] = None) -> float:
    """공격자 레벨에 대응하는 격파 기본 피해. 게임 데이터 원본 값."""
    if table:
        if level in table:
            return table[level]
        levels = sorted(table)
        closest = max((lv for lv in levels if lv <= level), default=levels[0])
        return table[closest]
    return BREAK_BASE_DAMAGE_LV80 if level >= 80 else 0.0


def compute_break_damage(
    engine, state, attacker: Unit, target: Unit, element: Element, config: BreakConfig
) -> float:
    """격파 피해.

    속성 배수가 설정되어 있지 않으면 **0 을 반환한다.**
    근거 없는 값을 추정해서 넣지 않기 위한 것이다. docs/mechanics.md 8.3
    """
    spec = config.elements.get(element)
    if spec is None or spec.damage_multiplier is None:
        return 0.0

    table = getattr(engine.config, "break_base_damage_table", None)
    base = break_base_damage(attacker.level, table)
    break_effect = 1.0 + attacker.stat(Stat.BREAK_EFFECT)
    toughness_mult = 1.0
    if config.toughness_multiplier is not None:
        toughness_mult = config.toughness_multiplier
    return base * spec.damage_multiplier * break_effect * toughness_mult


def reduce(
    engine,
    state,
    attacker: Unit,
    target: Unit,
    amount: float,
    element: Element,
    ignores_weakness: bool = False,
    config: Optional[BreakConfig] = None,
) -> bool:
    """인성치를 깎고, 0 이 되면 격파 처리한다. 격파되었으면 True."""
    config = config or getattr(engine.config, "break_config", None) or DEFAULT_BREAK_CONFIG
    if amount <= 0.0 or not can_reduce(target, element, ignores_weakness):
        return False

    before = target.current_toughness
    target.current_toughness = max(0.0, before - amount)
    engine.bus.emit(
        engine, state,
        ToughnessReduced(uid=target.uid, amount=before - target.current_toughness,
                         remaining=target.current_toughness),
    )
    state.log.add(
        state.elapsed_av, state.cycle, "toughness",
        f"{target.uid} 인성치 {before:.0f} -> {target.current_toughness:.0f}",
        uid=target.uid,
    )
    if target.current_toughness > 0.0:
        return False
    return _break(engine, state, attacker, target, element, config)


def _break(engine, state, attacker: Unit, target: Unit, element: Element,
           config: BreakConfig) -> bool:
    from . import scheduler, status
    from .damage import DamageContext

    target.toughness_broken = True
    state.log.add(
        state.elapsed_av, state.cycle, "break",
        f"{target.uid} 약점 격파 ({element.value})", uid=target.uid,
    )

    # 행동 지연 — 비율 근거는 미확인 (docs/mechanics.md 8.4)
    if config.action_delay:
        scheduler.modify_gauge(target, delay=config.action_delay)

    # 격파 피해 — 속성 배수가 설정되지 않았으면 0 이다
    amount = compute_break_damage(engine, state, attacker, target, element, config)
    if amount > 0.0:
        ctx = DamageContext(
            attacker=attacker, defender=target, element=element,
            multiplier=0.0, tags=(DamageTag.BREAK,), skill_id="weakness_break",
            base_damage_override=amount,
        )
        from ..core.enums import CritMode
        engine.deal_damage(state, ctx, crit_mode=CritMode.NEVER)

    # 속성별 격파 효과
    spec = config.elements.get(element)
    if spec is not None and spec.effect_id:
        status.try_apply_effect(engine, state, target, spec.effect_id, source=attacker)

    engine.bus.emit(
        engine, state,
        WeaknessBroken(uid=target.uid, element=element, break_damage=amount),
    )
    return True


def on_turn_end(engine, state, unit: Unit, config: Optional[BreakConfig] = None) -> None:
    """격파된 대상이 자기 턴을 마치면 인성치를 회복한다. **[미확인]**"""
    config = config or getattr(engine.config, "break_config", None) or DEFAULT_BREAK_CONFIG
    if not config.recover_on_turn_end or not unit.toughness_broken:
        return
    unit.toughness_broken = False
    unit.current_toughness = unit.max_toughness
    state.log.add(
        state.elapsed_av, state.cycle, "toughness",
        f"{unit.uid} 인성치 회복", uid=unit.uid,
    )
    engine.bus.emit(engine, state, ToughnessRecovered(uid=unit.uid))
