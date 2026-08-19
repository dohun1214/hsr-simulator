"""전투 중 변하는 유닛 상태."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.enums import Element, Side
from ..stats.stat import Stat, StatModifier, compute_stat

#: 게임 내부 Action Gauge 의 최대치. AV = AG / SPD.
#: 근거: KQM Speed Guide ("Default AG = 10000")  -> docs/mechanics.md 1.1
ACTION_GAUGE_FULL = 10000.0

#: 약점이 아닌 속성에 대한 적의 기본 저항. 근거: docs/mechanics.md 2.7
DEFAULT_ENEMY_RES = 0.20
#: 약점 속성에 대한 저항
WEAKNESS_RES = 0.0


@dataclass
class StatusEffect:
    """유닛에 걸려 있는 상태 효과 인스턴스 (순수 데이터).

    정의(중첩 상한, 스탯 수정자, DoT 설정)는 레지스트리에 있고
    여기에는 "지금 몇 중첩이고 몇 턴 남았는가"만 저장한다.
    """

    effect_id: str
    source_uid: str = ""
    stacks: int = 1
    #: 남은 턴 수. -1 이면 무한 (조건부 해제 효과)
    remaining_turns: int = -1
    #: 부여 순번. DoT 는 부여된 순서대로 발동한다 (docs/mechanics.md 5.6)
    applied_seq: int = 0
    #: DoT 스냅샷 (부여 시점의 시전자 정보). docs/mechanics.md 5.6
    snapshot: Optional[Dict[str, float]] = None

    def clone(self) -> "StatusEffect":
        return StatusEffect(
            effect_id=self.effect_id,
            source_uid=self.source_uid,
            stacks=self.stacks,
            remaining_turns=self.remaining_turns,
            applied_seq=self.applied_seq,
            snapshot=dict(self.snapshot) if self.snapshot is not None else None,
        )


@dataclass
class Unit:
    """전투에 참여하는 하나의 개체.

    **여기에는 순수 데이터만 둔다.** 동작은 레지스트리의 구현체가 담당한다.
    그래야 clone() 이 싸고, 결정론적이며, 탐색에 쓸 수 있다.
    """

    uid: str
    definition_id: str
    side: Side
    slot: int
    level: int = 1

    base_stats: Dict[Stat, float] = field(default_factory=dict)
    modifiers: List[StatModifier] = field(default_factory=list)

    current_hp: float = 0.0
    #: 남은 행동 게이지. AV = action_gauge / SPD
    action_gauge: float = ACTION_GAUGE_FULL
    alive: bool = True

    #: 필살기 에너지. max_energy 가 0 이면 에너지 시스템을 쓰지 않는 개체.
    energy: float = 0.0
    max_energy: float = 0.0

    #: V0.1 에서는 격파 시스템을 구현하지 않지만, 데미지 공식의
    #: Broken Multiplier(0.9 / 1.0) 를 실제 게임과 맞추기 위해 플래그만 둔다.
    #: 근거: docs/mechanics.md 2.8
    toughness_broken: bool = False
    current_toughness: float = 0.0
    max_toughness: float = 0.0

    weaknesses: frozenset = field(default_factory=frozenset)
    res_overrides: Dict[Element, float] = field(default_factory=dict)
    #: 특정 디버프에 대한 개별 저항 (effect_id -> 저항값)
    debuff_res: Dict[str, float] = field(default_factory=dict)

    #: 걸려 있는 상태 효과. 순수 데이터이며 동작은 레지스트리의 정의가 담당한다.
    effects: List["StatusEffect"] = field(default_factory=list)

    # --- 적 AI 런타임 상태 (docs/mechanics.md 7장) ---
    #: 현재 페이즈. 스킬/결정의 사용 가능 여부를 가른다.
    phase: int = 1
    #: 고정 스킬 순환의 다음 위치
    sequence_index: int = 0
    #: 스킬별 남은 쿨다운 (자신의 턴 기준)
    skill_cooldowns: Dict[str, int] = field(default_factory=dict)
    #: AI 내부 카운터 (게임의 DynamicValue 에 대응)
    counters: Dict[str, float] = field(default_factory=dict)
    #: 이번 턴에 사용한 스킬의 행동 게이지 배수. 턴 종료 시 적용되고 1.0 으로 돌아간다.
    pending_delay_ratio: float = 1.0

    #: 향후 메커니즘이 임의의 값을 붙일 수 있는 확장 슬롯
    #: (에너지, 스택 카운터 등. 엔진 코어를 고치지 않고 확장하기 위함)
    extra: Dict[str, Any] = field(default_factory=dict)

    # --- 파생 값 ---------------------------------------------------------

    def effect(self, effect_id: str) -> Optional["StatusEffect"]:
        for eff in self.effects:
            if eff.effect_id == effect_id:
                return eff
        return None

    def has_effect(self, effect_id: str) -> bool:
        return self.effect(effect_id) is not None

    def stat(self, stat: Stat) -> float:
        return compute_stat(stat, self.base_stats.get(stat, 0.0), self.modifiers)

    @property
    def max_hp(self) -> float:
        return self.stat(Stat.MAX_HP)

    @property
    def spd(self) -> float:
        return max(self.stat(Stat.SPD), 1e-9)

    @property
    def energy_full(self) -> bool:
        return self.max_energy > 0.0 and self.energy >= self.max_energy

    @property
    def hp_ratio(self) -> float:
        mhp = self.max_hp
        return self.current_hp / mhp if mhp > 0 else 0.0

    def res_to(self, element: Element) -> float:
        """해당 속성에 대한 저항.

        근거: docs/mechanics.md 2.7
        - 약점 속성이면 0%
        - 그 외에는 적 기본 20% (아군은 0%)
        - 데이터에 명시된 오버라이드가 최우선
        """
        if element in self.res_overrides:
            return self.res_overrides[element]
        if element in self.weaknesses:
            return WEAKNESS_RES
        if self.side is Side.ENEMY:
            return DEFAULT_ENEMY_RES
        return 0.0

    # --- 복제 -----------------------------------------------------------

    def clone(self) -> "Unit":
        """탐색용 얕은-깊은 복제.

        copy.deepcopy 는 느리고, 정의(불변 데이터)까지 복사할 위험이 있어 쓰지 않는다.
        """
        return Unit(
            uid=self.uid,
            definition_id=self.definition_id,
            side=self.side,
            slot=self.slot,
            level=self.level,
            base_stats=dict(self.base_stats),
            modifiers=[m.clone() for m in self.modifiers],
            current_hp=self.current_hp,
            action_gauge=self.action_gauge,
            alive=self.alive,
            energy=self.energy,
            max_energy=self.max_energy,
            toughness_broken=self.toughness_broken,
            current_toughness=self.current_toughness,
            max_toughness=self.max_toughness,
            weaknesses=self.weaknesses,
            res_overrides=dict(self.res_overrides),
            debuff_res=dict(self.debuff_res),
            effects=[e.clone() for e in self.effects],
            phase=self.phase,
            sequence_index=self.sequence_index,
            skill_cooldowns=dict(self.skill_cooldowns),
            counters=dict(self.counters),
            pending_delay_ratio=self.pending_delay_ratio,
            extra=dict(self.extra),
        )
