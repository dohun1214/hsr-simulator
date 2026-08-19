"""전투 엔진.

엔진은 **상태를 갖지 않는 실행기**에 가깝다.
- 가변 전투 상태는 전부 BattleState 에 있고
- 동작 구현은 전부 레지스트리에 있으며
- 엔진은 그 둘을 규칙에 따라 연결한다.

덕분에 하나의 엔진 인스턴스로 수많은 BattleState 복제본을 병렬 탐색할 수 있다.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from ..core.enums import BattleOutcome, DamageTag, Element, ScalingStat, Side, SkillKind
from ..core.events import (
    AfterAction,
    AfterUltimate,
    BeforeUltimate,
    AfterDamage,
    BattleEnd,
    BattleStart,
    BeforeAction,
    BeforeDamage,
    CycleStart,
    EventBus,
    HpChanged,
    TurnEnd,
    TurnStart,
    UnitDefeated,
)
from ..entities.unit import Unit
from ..registries import ABILITIES, ACTION_HANDLERS, BEHAVIORS, ENEMY_AI, UNIT_DEFINITIONS
from ..stats.stat import Stat
from . import scheduler
from .actions import Action, BasicAttackAction, SkillAction, SkipAction, UltimateAction
from .damage import DamageContext, DamageResult, compute_damage
from . import ai as enemy_ai
from . import status
from . import toughness
from .resources import can_pay_skill_points
from .state import BattleConfig, BattleState

ActionChooser = Callable[["BattleEngine", BattleState, Unit], Action]


def auto_ultimate_policy(engine, state, candidates):
    """기본 필살기 정책: 쓸 수 있으면 곧바로 쓴다 (등록 순서대로).

    실제 플레이는 타이밍을 재지만, V0.2 의 기본 자동 진행은 결정론이 우선이다.
    탐색 단계에서는 이 자리에 평가 기반 정책이 들어간다.
    """
    return candidates[0] if candidates else None


def never_ultimate_policy(engine, state, candidates):
    """필살기를 쓰지 않는 정책 (테스트/비교용)."""
    return None


class BattleEngine:
    def __init__(self, config: Optional[BattleConfig] = None) -> None:
        self.config = config or BattleConfig()
        self.bus = EventBus()

    # ------------------------------------------------------------------
    # 준비
    # ------------------------------------------------------------------

    def bind_abilities(self, state: BattleState) -> None:
        """상태에 있는 유닛들의 특성을 이벤트 버스에 연결한다.

        유닛이 추가/제거될 때(소환수, 웨이브 전환) 다시 호출하면 된다.
        """
        self.bus.clear()
        for unit in state.all_units():
            definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
            if definition is None:
                continue
            for ability_id in definition.ability_ids:
                ABILITIES.get(ability_id).bind(self.bus, unit.uid)

    def start_battle(self, state: BattleState) -> None:
        """전투 시작.

        각 유닛의 AV 를 기본값으로 세팅한다 (AG = 10000).
        근거: docs/mechanics.md 1.3
        """
        if state.started:
            return
        for unit in state.all_units():
            definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
            ratio = definition.initial_delay_ratio if definition else 1.0
            scheduler.reset_gauge(unit, ratio)
            if definition is not None and definition.ai_id:
                enemy_ai.start_cooldowns(unit, ENEMY_AI.try_get(definition.ai_id))
        state.started = True
        state.cycle = 1
        state.max_skill_points = self.config.max_skill_points
        state.skill_points = min(self.config.starting_skill_points, state.max_skill_points)
        state.log.enabled = self.config.log_enabled
        state.log.add(state.elapsed_av, state.cycle, "battle", "전투 시작")
        self.bus.emit(self, state, BattleStart())
        self.bus.emit(self, state, CycleStart(cycle=1))
        self._check_outcome(state)

    # ------------------------------------------------------------------
    # 시간 진행
    # ------------------------------------------------------------------

    def peek_next_actor(self, state: BattleState) -> Optional[Tuple[Unit, float]]:
        return scheduler.pick_next_actor(state.all_units(), state.order)

    def advance_to_next_turn(self, state: BattleState) -> Optional[str]:
        """다음 행동자까지 시간을 흘리고, 그 유닛의 턴을 시작한다."""
        if state.is_over:
            return None
        picked = self.peek_next_actor(state)
        if picked is None:
            return None
        actor, delta_av = picked

        scheduler.advance_time(state.all_units(), delta_av)
        state.elapsed_av += delta_av
        self._sync_cycle(state)

        actor.action_gauge = 0.0
        state.active_uid = actor.uid
        state.log.add(
            state.elapsed_av,
            state.cycle,
            "turn",
            f"{self._label(state, actor)} 턴 시작",
            uid=actor.uid,
        )
        self.bus.emit(self, state, TurnStart(uid=actor.uid))
        # 지속 피해 발동과 턴 시작 기준 지속시간 감소 (docs/mechanics.md 5.5~5.6)
        status.on_turn_start(self, state, actor)
        return actor.uid

    def _sync_cycle(self, state: BattleState) -> None:
        new_cycle = scheduler.cycle_of(state.elapsed_av)
        while state.cycle < new_cycle:
            state.cycle += 1
            state.log.add(state.elapsed_av, state.cycle, "cycle", f"사이클 {state.cycle} 시작")
            self.bus.emit(self, state, CycleStart(cycle=state.cycle))

    # ------------------------------------------------------------------
    # 행동
    # ------------------------------------------------------------------

    def legal_actions(self, state: BattleState, uid: Optional[str] = None) -> List[Action]:
        """해당 유닛이 이번 **턴에** 할 수 있는 행동 (일반 공격 / 전투 스킬).

        필살기는 턴을 소모하지 않는 별개의 행동이므로 여기 포함되지 않는다.
        `available_ultimates()` 를 따로 쓴다. 근거: docs/mechanics.md 4.3

        탐색 알고리즘의 분기 생성 지점이다.
        """
        uid = uid or state.active_uid
        if uid is None:
            return []
        unit = state.unit(uid)
        if not unit.alive:
            return []
        if status.is_action_blocked(unit):
            return [SkipAction(actor_uid=uid, reason="행동 불능")]

        definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
        if definition is None:
            return [SkipAction(actor_uid=uid, reason="정의 없음")]

        actions: List[Action] = []
        actions += self._actions_for_skill(
            state, unit, definition.basic_attack_id, BasicAttackAction
        )
        if definition.skill_id:
            actions += self._actions_for_skill(
                state, unit, definition.skill_id, SkillAction
            )
        if not actions:
            return [SkipAction(actor_uid=uid, reason="가능한 행동 없음")]
        return actions

    def _actions_for_skill(self, state, unit, skill_id, action_cls) -> List[Action]:
        from .targeting import candidate_targets

        definition = UNIT_DEFINITIONS.get(unit.definition_id)
        skill = definition.skills.get(skill_id) if skill_id else None
        if skill is None:
            return []
        if unit.side is Side.ALLY and not can_pay_skill_points(state, skill.sp_cost):
            return []
        if skill.energy_cost and unit.energy < skill.energy_cost:
            return []
        targets = candidate_targets(state, unit, skill.target_rule)
        if not targets:
            return []
        if skill.target_rule.shape == "aoe":
            targets = targets[:1]  # 전체 공격은 대상 선택이 의미 없다
        return [
            action_cls(actor_uid=unit.uid, target_uid=target.uid, skill_id=skill.skill_id)
            for target in sorted(targets, key=lambda u: (u.slot, u.uid))
        ]

    # ------------------------------------------------------------------
    # 필살기 (턴을 소모하지 않는 별도 행동)
    # ------------------------------------------------------------------

    def available_ultimates(
        self, state: BattleState, side: Optional[Side] = Side.ALLY
    ) -> List[UltimateAction]:
        """지금 발동 가능한 필살기 목록.

        에너지가 가득 찬 유닛이면 자기 턴이 아니어도 발동할 수 있다.
        근거: docs/mechanics.md 4.3
        """
        if state.is_over:
            return []
        result: List[UltimateAction] = []
        for unit in state.living(side):
            definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
            if definition is None or not definition.ultimate_id:
                continue
            if not unit.energy_full:
                continue
            actions = self._actions_for_skill(
                state, unit, definition.ultimate_id, UltimateAction
            )
            if actions:
                result.append(actions[0])
        return result

    def use_ultimate(self, state: BattleState, action: UltimateAction) -> None:
        """필살기 발동. **턴도 행동 게이지도 소모하지 않는다.**"""
        self.bus.emit(self, state, BeforeUltimate(uid=action.actor_uid))
        state.log.add(
            state.elapsed_av, state.cycle, "ultimate",
            f"{self._label(state, state.unit(action.actor_uid))} 필살기 발동",
            uid=action.actor_uid,
        )
        ACTION_HANDLERS.get(action.kind)(self, state, action)
        self.bus.emit(self, state, AfterUltimate(uid=action.actor_uid))
        self._check_outcome(state)

    def resolve_ultimates(self, state: BattleState, policy=None) -> int:
        """발동 가능한 필살기를 정책에 따라 연달아 처리한다.

        "Multiple Ultimates can also be chained in this way" 를 반영한다.
        """
        policy = policy if policy is not None else auto_ultimate_policy
        used = 0
        while not state.is_over:
            candidates = self.available_ultimates(state)
            if not candidates:
                break
            chosen = policy(self, state, candidates)
            if chosen is None:
                break
            self.use_ultimate(state, chosen)
            used += 1
            if used > 32:  # 안전장치
                break
        return used

    def choose_action(self, state: BattleState, uid: str) -> Action:
        """유닛의 등록된 행동 선택기로 행동을 고른다 (적 AI / 자동 진행)."""
        unit = state.unit(uid)
        definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
        behavior_id = definition.behavior_id if definition else "basic_attack_aggro"
        behavior = BEHAVIORS.get(behavior_id)
        return behavior(self, state, unit)

    def perform(self, state: BattleState, action: Action) -> None:
        """행동을 실행한다 (턴 종료는 하지 않는다)."""
        self.bus.emit(self, state, BeforeAction(uid=action.actor_uid, action=action))
        handler = ACTION_HANDLERS.get(action.kind)
        handler(self, state, action)
        self.bus.emit(self, state, AfterAction(uid=action.actor_uid, action=action))

    def end_turn(self, state: BattleState) -> None:
        uid = state.active_uid
        if uid is None:
            return
        unit = state.unit(uid)
        if unit.alive:
            # 사용한 스킬의 행동 게이지 배수를 반영한다 (docs/mechanics.md 7.5)
            scheduler.reset_gauge(unit, unit.pending_delay_ratio)
            unit.pending_delay_ratio = 1.0
            enemy_ai.tick_cooldowns(unit)
            toughness.on_turn_end(self, state, unit)
            status.on_turn_end(self, state, unit)
        self.bus.emit(self, state, TurnEnd(uid=uid))
        state.active_uid = None
        state.turn_count += 1
        self._check_outcome(state)

    def take_turn(self, state: BattleState, action: Optional[Action] = None) -> Optional[Action]:
        """턴 1회 = 행동자 선정 -> 행동 -> 턴 종료."""
        uid = self.advance_to_next_turn(state)
        if uid is None:
            return None
        unit = state.unit(uid)
        if not unit.alive or state.is_over:
            self.end_turn(state)
            return None
        chosen = action if action is not None else self.choose_action(state, uid)
        self.perform(state, chosen)
        self.end_turn(state)
        return chosen

    def simulate(self, state: BattleState, action: Optional[Action] = None) -> BattleState:
        """상태를 복제한 뒤 턴 1회를 진행한 **새 상태**를 반환한다.

        탐색 알고리즘이 미래 상태를 만들 때 쓰는 진입점. 원본 상태는 변경되지 않는다.
        """
        future = state.clone()
        self.take_turn(future, action)
        return future

    def run(
        self,
        state: BattleState,
        ally_chooser: Optional[ActionChooser] = None,
        max_turns: Optional[int] = None,
        ultimate_policy=None,
    ) -> BattleOutcome:
        """전투가 끝날 때까지 자동 진행."""
        if not state.started:
            self.start_battle(state)
        limit = max_turns if max_turns is not None else self.config.max_turns
        self.resolve_ultimates(state, ultimate_policy)
        while not state.is_over and state.turn_count < limit:
            uid = self.advance_to_next_turn(state)
            if uid is None:
                break
            # 자기 턴 시작 시점에도 필살기를 쓸 수 있다 (턴은 유지된다)
            self.resolve_ultimates(state, ultimate_policy)
            if state.is_over:
                break
            unit = state.unit(uid)
            if not unit.alive:
                self.end_turn(state)
                continue
            if ally_chooser is not None and unit.side is Side.ALLY:
                action = ally_chooser(self, state, unit)
            else:
                action = self.choose_action(state, uid)
            self.perform(state, action)
            self.end_turn(state)
            self.resolve_ultimates(state, ultimate_policy)
        return state.outcome

    # ------------------------------------------------------------------
    # 데미지 / HP
    # ------------------------------------------------------------------

    def deal_damage(self, state: BattleState, ctx: DamageContext, crit_mode=None) -> DamageResult:
        """데미지 판정 1회. 이벤트를 통해 외부 효과가 개입할 수 있다.

        ``crit_mode`` 를 지정하면 설정을 무시한다. DoT 는 치명타가 없으므로
        항상 ``CritMode.NEVER`` 로 호출된다 (docs/mechanics.md 5.6).
        """
        self.bus.emit(self, state, BeforeDamage(ctx=ctx))
        result = compute_damage(
            ctx, crit_mode=crit_mode or self.config.crit_mode, rng=state.rng
        )
        state.log.add(
            state.elapsed_av,
            state.cycle,
            "damage",
            "{} -> {} {:.1f} {}{}".format(
                self._label(state, ctx.attacker),
                self._label(state, ctx.defender),
                result.amount,
                "지속 피해" if DamageTag.DOT in ctx.tags else "피해",
                " (치명타)" if result.is_crit else "",
            ),
            attacker=ctx.attacker.uid,
            defender=ctx.defender.uid,
            amount=result.amount,
            is_crit=result.is_crit,
        )
        self.apply_hp_change(state, ctx.defender, -result.amount)
        self.bus.emit(self, state, AfterDamage(ctx=ctx, result=result))
        return result

    def apply_hp_change(self, state: BattleState, unit: Unit, delta: float) -> None:
        if not unit.alive:
            return
        before = unit.current_hp
        after = min(max(before + delta, 0.0), unit.max_hp)
        unit.current_hp = after
        self.bus.emit(self, state, HpChanged(uid=unit.uid, before=before, after=after))
        if after <= 0.0:
            self._defeat(state, unit)

    def _defeat(self, state: BattleState, unit: Unit) -> None:
        unit.alive = False
        unit.current_hp = 0.0
        # 쓰러진 유닛의 상태 효과는 사라진다
        unit.effects.clear()
        status.rebuild_effect_modifiers(unit)
        state.log.add(
            state.elapsed_av, state.cycle, "defeat",
            f"{self._label(state, unit)} 전투 불능", uid=unit.uid,
        )
        self.bus.emit(self, state, UnitDefeated(uid=unit.uid))
        self._check_outcome(state)

    # ------------------------------------------------------------------
    # 종료 판정
    # ------------------------------------------------------------------

    def _check_outcome(self, state: BattleState) -> BattleOutcome:
        if state.is_over:
            return state.outcome
        allies = state.living(Side.ALLY)
        enemies = state.living(Side.ENEMY)
        if not allies and not enemies:
            state.outcome = BattleOutcome.DRAW
        elif not enemies:
            state.outcome = BattleOutcome.VICTORY
        elif not allies:
            state.outcome = BattleOutcome.DEFEAT
        if state.is_over:
            state.log.add(
                state.elapsed_av, state.cycle, "battle", f"전투 종료: {state.outcome.value}"
            )
            self.bus.emit(self, state, BattleEnd(outcome=state.outcome))
        return state.outcome

    # ------------------------------------------------------------------

    @staticmethod
    def _label(state: BattleState, unit: Unit) -> str:
        definition = UNIT_DEFINITIONS.try_get(unit.definition_id)
        name = str(definition.name) if definition else unit.definition_id
        return f"{name}({unit.uid})"


# 행동 처리기와 기본 행동 선택기를 등록한다 (임포트 부수효과).
from . import behaviors  # noqa: E402,F401
from . import handlers  # noqa: E402,F401
