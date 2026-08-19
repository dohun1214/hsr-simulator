"""데미지 계산 파이프라인.

전체 공식과 근거는 docs/mechanics.md 2장.

    DMG = BaseDMG
        x CritMultiplier
        x DmgBoostMultiplier
        x WeakenMultiplier
        x DefMultiplier
        x ResMultiplier
        x VulnerabilityMultiplier
        x MitigationMultiplier
        x BrokenMultiplier

**확장 설계**

- 각 배수는 이름이 붙은 `DamageStep` 이며 순서가 있는 목록에 등록된다.
- 새로운 곱연산 항이 게임에 추가되면 `register_damage_step()` 로 끼워 넣으면 되고
  기존 코드는 건드리지 않는다.
- 이벤트 `BeforeDamage` 핸들러는 `DamageContext` 의 입력 필드
  (dmg_bonus, def_ignore, vulnerability, ...) 를 더해서 기여할 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..core.enums import CritMode, DamageTag, Element, ScalingStat
from ..core.rng import RngState
from ..entities.unit import Unit
from ..stats.stat import Stat, stat_components

#: 적의 기본 DEF = 200 + 10 x 레벨.
#: [유도됨] KQM 의 레벨 기반 식과 Prydwen 의 DEF 기반 식이 이 값에서 일치한다.
#: 근거와 유도 과정: docs/mechanics.md 2.6
DEF_LEVEL_CONSTANT = 200.0
DEF_LEVEL_SLOPE = 10.0

#: 유효 저항 허용 범위. 근거: docs/mechanics.md 2.7
MIN_EFFECTIVE_RES = -1.0
MAX_EFFECTIVE_RES = 0.9

#: 인성치가 남아 있을 때의 범용 피해 감소. 근거: docs/mechanics.md 2.8
UNBROKEN_MULTIPLIER = 0.9
BROKEN_MULTIPLIER = 1.0


def default_base_def(level: int) -> float:
    """레벨로부터 기본 DEF 추정값. 실제 데이터가 있으면 그쪽을 우선한다."""
    return DEF_LEVEL_CONSTANT + DEF_LEVEL_SLOPE * level


@dataclass
class DamageContext:
    """한 번의 데미지 판정에 필요한 모든 입력.

    아래 '조정 가능한 입력' 필드들은 `BeforeDamage` 이벤트 핸들러가
    자유롭게 가산할 수 있는 지점이다 (버프/디버프/패시브의 진입점).
    """

    attacker: Unit
    defender: Unit
    element: Element
    multiplier: float
    scaling: ScalingStat = ScalingStat.ATK
    flat_bonus: float = 0.0
    tags: Tuple[DamageTag, ...] = ()
    skill_id: str = ""

    # --- 조정 가능한 입력 -------------------------------------------------
    dmg_bonus: float = 0.0          # 속성 DMG% + 전체 DMG% + ...
    weaken: float = 0.0             # 나약 (피해량 감소)
    def_reduction: float = 0.0      # 방어력 감소
    def_ignore: float = 0.0         # 방어력 무시
    res_pen: float = 0.0            # 속성 저항 관통
    vulnerability: float = 0.0      # 받는 피해 증가
    mitigations: List[float] = field(default_factory=list)  # 피해 감소 (곱연산)
    crit_rate_bonus: float = 0.0
    crit_dmg_bonus: float = 0.0

    #: 아직 이름이 없는 미래 메커니즘용 곱연산 슬롯
    extra_multipliers: Dict[str, float] = field(default_factory=dict)

    #: DoT 스냅샷용 오버라이드. 지정되면 시전자의 현재 스탯 대신 이 값을 쓴다.
    #: docs/mechanics.md 5.6
    base_damage_override: Optional[float] = None
    attacker_level_override: Optional[int] = None

    @property
    def attacker_level(self) -> int:
        if self.attacker_level_override is not None:
            return self.attacker_level_override
        return self.attacker.level


@dataclass
class DamageResult:
    amount: float
    is_crit: bool
    base_damage: float
    breakdown: Dict[str, float] = field(default_factory=dict)


# --- 개별 배수 계산 --------------------------------------------------------


def base_damage(ctx: DamageContext) -> float:
    """BaseDMG = (스킬 배율) x (기준 스탯) + 고정 추가값. 근거: docs/mechanics.md 2.2

    DoT 스냅샷 모드에서는 부여 시점에 계산해 둔 값을 그대로 쓴다.
    """
    if ctx.base_damage_override is not None:
        return ctx.base_damage_override
    if ctx.scaling is ScalingStat.ATK:
        scale_value = ctx.attacker.stat(Stat.ATK)
    elif ctx.scaling is ScalingStat.DEF:
        scale_value = ctx.attacker.stat(Stat.DEF)
    else:
        scale_value = ctx.attacker.stat(Stat.MAX_HP)
    return ctx.multiplier * scale_value + ctx.flat_bonus


def crit_multiplier(ctx: DamageContext, mode: CritMode, rng: Optional[RngState]):
    """(배수, 치명타 여부) 반환. 근거: docs/mechanics.md 2.3"""
    rate = min(max(ctx.attacker.stat(Stat.CRIT_RATE) + ctx.crit_rate_bonus, 0.0), 1.0)
    dmg = ctx.attacker.stat(Stat.CRIT_DMG) + ctx.crit_dmg_bonus

    if mode is CritMode.NEVER:
        return 1.0, False
    if mode is CritMode.ALWAYS:
        return 1.0 + dmg, True
    if mode is CritMode.AVERAGE:
        return 1.0 + rate * dmg, False
    # CritMode.ROLL
    if rng is None:
        return 1.0 + rate * dmg, False
    is_crit = rng.random() < rate
    return (1.0 + dmg) if is_crit else 1.0, is_crit


def dmg_boost_multiplier(ctx: DamageContext) -> float:
    """근거: docs/mechanics.md 2.4"""
    return 1.0 + ctx.dmg_bonus


def weaken_multiplier(ctx: DamageContext) -> float:
    return max(0.0, 1.0 - ctx.weaken)


def def_multiplier(ctx: DamageContext) -> float:
    """근거: docs/mechanics.md 2.5

        DEF   = Base DEF x (1 + DEF% - (DEF 감소 + DEF 무시)) + Flat DEF   (최소 0)
        배수  = 1 - DEF / (DEF + 200 + 10 x 공격자 레벨)
    """
    base, percent, flat = stat_components(
        Stat.DEF, ctx.defender.base_stats.get(Stat.DEF, 0.0), ctx.defender.modifiers
    )
    effective_def = base * (1.0 + percent - (ctx.def_reduction + ctx.def_ignore)) + flat
    effective_def = max(0.0, effective_def)
    denominator = effective_def + DEF_LEVEL_CONSTANT + DEF_LEVEL_SLOPE * ctx.attacker_level
    return 1.0 - effective_def / denominator


def res_multiplier(ctx: DamageContext) -> float:
    """근거: docs/mechanics.md 2.7"""
    res = ctx.defender.res_to(ctx.element) - ctx.res_pen
    res = min(max(res, MIN_EFFECTIVE_RES), MAX_EFFECTIVE_RES)
    return 1.0 - res


def vulnerability_multiplier(ctx: DamageContext) -> float:
    return 1.0 + ctx.vulnerability


def mitigation_multiplier(ctx: DamageContext) -> float:
    """피해 감소는 서로 곱연산으로 합쳐진다."""
    total = 1.0
    for value in ctx.mitigations:
        total *= max(0.0, 1.0 - value)
    return total


def broken_multiplier(ctx: DamageContext) -> float:
    """인성치가 남아 있으면 0.9, 격파되었으면 1.0. 근거: docs/mechanics.md 2.8

    이 10% 범용 피해 감소는 **인성치 게이지를 가진 대상(적)** 의 특성이다.
    캐릭터는 인성치가 없으므로 (max_toughness == 0) 적용하지 않는다.
    """
    if ctx.defender.max_toughness <= 0.0:
        return BROKEN_MULTIPLIER
    return BROKEN_MULTIPLIER if ctx.defender.toughness_broken else UNBROKEN_MULTIPLIER


def extra_multiplier(ctx: DamageContext) -> float:
    total = 1.0
    for _key in sorted(ctx.extra_multipliers):
        total *= ctx.extra_multipliers[_key]
    return total


# --- 파이프라인 -------------------------------------------------------------

DamageStep = Callable[[DamageContext], float]

#: (이름, 계산 함수) 의 순서 있는 목록.
#: 치명타는 RNG 가 필요해 별도로 처리한다.
_STEPS: List[Tuple[str, DamageStep]] = [
    ("dmg_boost", dmg_boost_multiplier),
    ("weaken", weaken_multiplier),
    ("def", def_multiplier),
    ("res", res_multiplier),
    ("vulnerability", vulnerability_multiplier),
    ("mitigation", mitigation_multiplier),
    ("broken", broken_multiplier),
    ("extra", extra_multiplier),
]


def register_damage_step(name: str, step: DamageStep, before: Optional[str] = None) -> None:
    """새로운 곱연산 항을 파이프라인에 추가한다.

    미래에 새 데미지 배수가 게임에 생겨도 이 함수 호출 한 번으로 확장된다.
    """
    if any(existing == name for existing, _ in _STEPS):
        raise KeyError(f"이미 등록된 데미지 단계: {name}")
    if before is None:
        _STEPS.append((name, step))
        return
    for index, (existing, _) in enumerate(_STEPS):
        if existing == before:
            _STEPS.insert(index, (name, step))
            return
    raise KeyError(f"기준 단계를 찾을 수 없습니다: {before}")


def damage_step_names() -> List[str]:
    return [name for name, _ in _STEPS]


def compute_damage(
    ctx: DamageContext,
    crit_mode: CritMode = CritMode.ROLL,
    rng: Optional[RngState] = None,
) -> DamageResult:
    """최종 데미지 계산."""
    base = base_damage(ctx)
    crit_mult, is_crit = crit_multiplier(ctx, crit_mode, rng)

    total = base * crit_mult
    breakdown: Dict[str, float] = {"base": base, "crit": crit_mult}
    for name, step in _STEPS:
        value = step(ctx)
        breakdown[name] = value
        total *= value

    return DamageResult(amount=total, is_crit=is_crit, base_damage=base, breakdown=breakdown)
