"""인성치와 약점 격파.

근거와 무엇이 확인되지 않았는지는 docs/mechanics.md 8장.

확인된 것 (게임 데이터 + 커뮤니티 자료 교차검증)
  - 인성치는 **약점 속성 공격일 때만** 깎인다 (스킬에 예외 플래그가 있다)
  - 격파 기본 피해 = 공격자 레벨별 표(`AvatarBreakDamage`). 커뮤니티의 "Level Multiplier" 와
    Lv1 54 / Lv95 7494.371 까지 일치한다
  - 속성별 격파 배수: 물리 2 / 화염 2 / 얼음 1 / 번개 1 / 바람 1.5 / 양자 0.5 / 허수 0.5
  - 최대 인성치 배수 = 0.5 + 최대 인성치 / 120 (우리 단위 기준)
  - 격파 시 행동 25% 지연, 속성별 디버프를 **기본 확률 150%** 로 부여
  - 격파되면 범용 피해 감소 0.9 가 1.0 이 된다

확실하지 않은 것 (설정으로 분리했다)
  - 인성치 회복 시점
  - 얽힘/속박의 게임 데이터 DisableAction 플래그 (자료는 행동 지연만 말한다)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..core.enums import DamageTag, Element
from ..core.events import Event
from ..entities.unit import Unit
from ..stats.stat import Stat

#: 속성별 격파 피해 배수. 게임 내 표기가 없어 커뮤니티 자료(Fandom 위키 원문)에서 얻었고,
#: 게임 데이터의 격파 디버프 구조와 모순이 없음을 확인했다. docs/mechanics.md 8.3
ELEMENT_BREAK_MULTIPLIER: Dict[Element, float] = {
    Element.PHYSICAL: 2.0,
    Element.FIRE: 2.0,
    Element.ICE: 1.0,
    Element.LIGHTNING: 1.0,
    Element.WIND: 1.5,
    Element.QUANTUM: 0.5,
    Element.IMAGINARY: 0.5,
}

#: 최대 인성치 배수의 분모. 우리 인성치 단위(일반 공격 30)를 기준으로 한다.
#: 자료에 따라 "표기 인성치/40" 으로도 쓰는데, 표기 단위가 우리 단위의 1/3 이라
#: 결국 같은 식이다. docs/mechanics.md 8.3
MAX_TOUGHNESS_DIVISOR = 120.0

#: 격파 디버프의 기본 적용 확률. docs/mechanics.md 8.5
BREAK_DEBUFF_BASE_CHANCE = 1.5

#: 피격 시 중첩이 쌓이는 효과의 id (얽힘)
ENTANGLEMENT_EFFECT_ID = "break_entanglement"

#: 정예 이상으로 취급하는 몬스터 등급 (열상 배율, 풍화 초기 중첩이 달라진다)
ELITE_RANKS = frozenset({"Elite", "LittleBoss", "BigBoss"})

#: 공격자 레벨별 격파 기본 피해. 게임 데이터 `ExcelOutput/AvatarBreakDamage.json` 원본.
#: 전체 표는 data/break_base_damage.json 에 있고 여기에는 대표값만 둔다.
#: docs/mechanics.md 8.2
BREAK_BASE_DAMAGE_LV80 = 3767.5535


@dataclass
class BreakEffectSpec:
    """속성 1개의 격파 결과."""

    #: 격파 시 부여하는 상태 효과 id (STATUS_EFFECTS 레지스트리 키)
    effect_id: Optional[str] = None
    #: 격파 피해에 곱해지는 속성 배수. None 이면 격파 피해를 계산하지 않는다.
    damage_multiplier: Optional[float] = None
    #: 부여 시 중첩 수 (풍화: 일반 1)
    initial_stacks: int = 1
    #: 대상이 정예/보스일 때의 중첩 수 (풍화: 3). None 이면 initial_stacks 를 쓴다.
    elite_initial_stacks: Optional[int] = None
    #: 격파 25% 지연에 **추가로** 들어가는 행동 지연 (얽힘 0.20 / 속박 0.30)
    action_delay: float = 0.0
    #: 그 추가 지연에 (1 + 격파 특효) 를 곱하는가. 자료가 그렇게 적고 있다.
    action_delay_scales_with_break_effect: bool = True


@dataclass
class BreakConfig:
    """격파 관련 설정.

    수치의 근거는 docs/mechanics.md 8장. 아직 확인되지 않은 항목만 여기서
    끄고 켤 수 있게 두었다.
    """

    #: 격파 시 대상의 행동 게이지를 얼마나 뒤로 미는가. [확인됨] 25%
    action_delay: float = 0.25
    #: 최대 인성치 배수(0.5 + 최대인성치/120)를 격파 피해에 곱하는가. [확인됨]
    use_max_toughness_multiplier: bool = True
    #: 격파 디버프 부여 확률의 기본값
    debuff_base_chance: float = BREAK_DEBUFF_BASE_CHANCE
    #: 속성별 설정
    elements: Dict[Element, BreakEffectSpec] = field(default_factory=dict)
    #: 격파된 대상이 자기 턴을 마치면 인성치를 회복하는가. **[미확인]**
    recover_on_turn_end: bool = True


def _default_elements() -> Dict[Element, BreakEffectSpec]:
    """속성별 기본 설정. 효과 id 는 content/break_effects.py 에서 등록한다."""
    m = ELEMENT_BREAK_MULTIPLIER
    return {
        Element.PHYSICAL: BreakEffectSpec("break_bleed", m[Element.PHYSICAL]),
        Element.FIRE: BreakEffectSpec("break_burn", m[Element.FIRE]),
        Element.ICE: BreakEffectSpec("break_frozen", m[Element.ICE]),
        Element.LIGHTNING: BreakEffectSpec("break_shock", m[Element.LIGHTNING]),
        Element.WIND: BreakEffectSpec(
            "break_wind_shear", m[Element.WIND], initial_stacks=1, elite_initial_stacks=3
        ),
        Element.QUANTUM: BreakEffectSpec(
            "break_entanglement", m[Element.QUANTUM], action_delay=0.20
        ),
        Element.IMAGINARY: BreakEffectSpec(
            "break_imprisonment", m[Element.IMAGINARY], action_delay=0.30
        ),
    }


#: 기본 설정. 7속성 전부 채워져 있다.
DEFAULT_BREAK_CONFIG = BreakConfig(elements=_default_elements())


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


def is_elite(unit: Unit) -> bool:
    """정예/보스인가. 게임 데이터의 MonsterRank 를 그대로 쓴다.

    열상 배율(0.16 / 0.07)과 풍화 초기 중첩(1 / 3)이 이 판정으로 갈린다.
    게임 데이터의 격파 열상 정의도 `ByCompareMonsterRank` 로 같은 분기를 한다.
    """
    return str(unit.extra.get("rank") or "") in ELITE_RANKS


def max_toughness_multiplier(unit: Unit) -> float:
    """최대 인성치 배수 = 0.5 + 최대 인성치 / 120. docs/mechanics.md 8.3"""
    if unit.max_toughness <= 0.0:
        return 1.0
    return 0.5 + unit.max_toughness / MAX_TOUGHNESS_DIVISOR


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
    """격파 피해의 기본 피해.

        속성 배수 x 격파 기본 피해(공격자 레벨) x 최대 인성치 배수 x (1 + 격파 특효)

    이 값이 데미지 파이프라인의 Base DMG 로 들어가고, 이후 DEF/저항/취약/격파
    배수가 곱해진다. docs/mechanics.md 8.3
    """
    spec = config.elements.get(element)
    if spec is None or spec.damage_multiplier is None:
        return 0.0

    table = getattr(engine.config, "break_base_damage_table", None)
    base = break_base_damage(attacker.level, table)
    value = base * spec.damage_multiplier
    if config.use_max_toughness_multiplier:
        value *= max_toughness_multiplier(target)
    return value * (1.0 + attacker.stat(Stat.BREAK_EFFECT))


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

    # 행동 25% 지연. docs/mechanics.md 8.4
    if config.action_delay:
        scheduler.modify_gauge(target, delay=config.action_delay)

    amount = compute_break_damage(engine, state, attacker, target, element, config)
    if amount > 0.0:
        ctx = DamageContext(
            attacker=attacker, defender=target, element=element,
            multiplier=0.0, tags=(DamageTag.BREAK,), skill_id="weakness_break",
            base_damage_override=amount,
        )
        from ..core.enums import CritMode
        engine.deal_damage(state, ctx, crit_mode=CritMode.NEVER)

    spec = config.elements.get(element)
    if spec is not None and spec.effect_id:
        _apply_break_effect(engine, state, attacker, target, spec, config)

    engine.bus.emit(
        engine, state,
        WeaknessBroken(uid=target.uid, element=element, break_damage=amount),
    )
    return True


def _apply_break_effect(engine, state, attacker: Unit, target: Unit,
                        spec: BreakEffectSpec, config: BreakConfig) -> None:
    """속성별 격파 디버프를 부여한다. 기본 확률 150%. docs/mechanics.md 8.5"""
    from . import scheduler, status

    stacks = spec.initial_stacks
    if spec.elite_initial_stacks is not None and is_elite(target):
        stacks = spec.elite_initial_stacks

    applied = status.try_apply_effect(
        engine, state, target, spec.effect_id,
        source=attacker,
        base_chance=config.debuff_base_chance,
        stacks=stacks,
    )
    if not applied:
        return

    # 얽힘 20% / 속박 30% 의 추가 행동 지연. 격파의 25% 와는 별개다.
    if spec.action_delay:
        delay = spec.action_delay
        if spec.action_delay_scales_with_break_effect:
            delay *= 1.0 + attacker.stat(Stat.BREAK_EFFECT)
        scheduler.modify_gauge(target, delay=delay)


def on_hit(engine, state, attacker: Unit, target: Unit) -> None:
    """피격 시 중첩이 늘어나는 격파 효과 (얽힘). docs/mechanics.md 8.6

    지속 피해나 격파 피해로는 중첩되지 않는다 — 자료가 "피격 후마다"라고만 한다.
    """
    from . import status

    effect = target.effect(ENTANGLEMENT_EFFECT_ID)
    if effect is None or not target.alive:
        return
    status.apply_effect(
        engine, state, target, ENTANGLEMENT_EFFECT_ID,
        source=state.units.get(effect.source_uid) or attacker,
        duration=effect.remaining_turns,
        stacks=1,
    )


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
