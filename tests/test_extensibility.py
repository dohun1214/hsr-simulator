"""확장성 테스트 (요구사항 11).

"엔진 코어를 수정하지 않고 새 메커니즘을 추가할 수 있는가"를 코드로 고정한다.
아래 테스트들은 전부 **엔진 파일을 건드리지 않고** 새 동작을 붙인다.
"""

import pytest

from hsr_sim import BattleConfig, BattleEngine, CritMode, build_battle, definitions
from hsr_sim.battle import damage as damage_module
from hsr_sim.battle.actions import Action, BasicAttackAction
from hsr_sim.battle.damage import DamageContext, register_damage_step
from hsr_sim.core.events import BeforeDamage, TurnStart
from hsr_sim.registries import ABILITIES, ACTION_HANDLERS, BEHAVIORS
from hsr_sim.stats.stat import ModifierKind, Stat, StatModifier


@pytest.fixture
def battle():
    config = BattleConfig(crit_mode=CritMode.NEVER, log_enabled=False)
    state = build_battle(
        definitions("test_ally_a"), definitions("test_enemy_a"), config=config
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    engine.start_battle(state)
    return engine, state


def base_hit(engine, state, target_uid="E1"):
    before = state.unit(target_uid).current_hp
    state.active_uid = "A1"
    engine.perform(state, BasicAttackAction(actor_uid="A1", target_uid=target_uid))
    return before - state.unit(target_uid).current_hp


def test_new_ability_can_modify_damage_via_events(battle):
    """새 패시브: '내 공격의 피해 +50%'.

    엔진/데미지 코드 수정 없이 BeforeDamage 구독만으로 동작해야 한다.
    """
    engine, state = battle
    baseline = base_hit(engine, state)
    state.unit("E1").current_hp = state.unit("E1").max_hp

    class DamageUpAbility:
        def bind(self, bus, owner_uid):
            def handler(engine_, state_, event: BeforeDamage):
                if event.ctx.attacker.uid == owner_uid:
                    event.ctx.dmg_bonus += 0.5

            bus.subscribe(BeforeDamage, handler, source=owner_uid)

    DamageUpAbility().bind(engine.bus, "A1")
    boosted = base_hit(engine, state)
    assert boosted == pytest.approx(baseline * 1.5)


def test_new_ability_can_buff_stats_on_turn_start(battle):
    """새 패시브: '턴 시작 시 공격력 +20%'."""
    engine, state = battle

    class AtkBuffOnTurnStart:
        def bind(self, bus, owner_uid):
            def handler(engine_, state_, event: TurnStart):
                if event.uid != owner_uid:
                    return
                state_.unit(owner_uid).modifiers.append(
                    StatModifier(Stat.ATK, ModifierKind.PERCENT_OF_BASE, 0.2, "test_buff")
                )

            bus.subscribe(TurnStart, handler, source=owner_uid)

    AtkBuffOnTurnStart().bind(engine.bus, "A1")
    assert state.unit("A1").stat(Stat.ATK) == pytest.approx(1000.0)
    while engine.advance_to_next_turn(state) != "A1":
        engine.end_turn(state)
    assert state.unit("A1").stat(Stat.ATK) == pytest.approx(1200.0)


def test_new_damage_step_can_be_inserted(battle):
    """새로운 곱연산 항이 게임에 추가되는 상황."""
    engine, state = battle
    baseline = base_hit(engine, state)
    state.unit("E1").current_hp = state.unit("E1").max_hp

    saved = list(damage_module._STEPS)
    try:
        register_damage_step("test_new_mechanic", lambda ctx: 0.5, before="broken")
        assert damage_module.damage_step_names().index(
            "test_new_mechanic"
        ) < damage_module.damage_step_names().index("broken")
        halved = base_hit(engine, state)
        assert halved == pytest.approx(baseline * 0.5)
    finally:
        damage_module._STEPS[:] = saved


def test_new_action_type_only_needs_a_handler(battle):
    """새 행동 유형 추가 = Action 클래스 + 처리기 등록."""
    engine, state = battle

    from dataclasses import dataclass

    @dataclass(frozen=True)
    class TrueDamageAction(Action):
        target_uid: str = ""
        amount: float = 0.0

    def handle(engine_, state_, action):
        engine_.apply_hp_change(state_, state_.unit(action.target_uid), -action.amount)

    ACTION_HANDLERS.register("TrueDamageAction", handle)
    try:
        before = state.unit("E1").current_hp
        state.active_uid = "A1"
        engine.perform(state, TrueDamageAction(actor_uid="A1", target_uid="E1", amount=1234.0))
        assert before - state.unit("E1").current_hp == pytest.approx(1234.0)
    finally:
        ACTION_HANDLERS._items.pop("TrueDamageAction", None)


def test_new_behavior_only_needs_registration():
    def always_skip(engine, state, unit):
        from hsr_sim.battle.actions import SkipAction

        return SkipAction(actor_uid=unit.uid, reason="테스트")

    BEHAVIORS.register("test_always_skip", always_skip)
    try:
        assert BEHAVIORS.get("test_always_skip") is always_skip
    finally:
        BEHAVIORS._items.pop("test_always_skip", None)


def test_new_status_effect_only_needs_registration(battle):
    """새 상태 효과 추가 = 정의 작성 + 레지스트리 등록.

    엔진/상태 효과 코드 수정 없이 동작해야 한다.
    """
    from hsr_sim.battle import status
    from hsr_sim.core.enums import DebuffKind, EffectCategory, RefreshPolicy
    from hsr_sim.entities.definitions import LocalizedName, StatusEffectDefinition
    from hsr_sim.registries import STATUS_EFFECTS

    engine, state = battle
    definition = StatusEffectDefinition(
        effect_id="test_new_mechanic_spd_down",
        name=LocalizedName(ko="테스트 신규 효과", en="Test New Effect", ko_verified=True),
        category=EffectCategory.DEBUFF,
        debuff_kind=DebuffKind.SLOW,
        base_duration=2,
        max_stacks=2,
        refresh=RefreshPolicy.STACK_AND_REFRESH,
        stat_modifiers=(
            StatModifier(Stat.SPD, ModifierKind.PERCENT_OF_BASE, -0.25, "test_new"),
        ),
    )
    STATUS_EFFECTS.register(definition.effect_id, definition)
    try:
        enemy = state.unit("E1")
        base_spd = enemy.spd
        status.apply_effect(engine, state, enemy, definition.effect_id)
        assert enemy.spd == pytest.approx(base_spd * 0.75)
        status.apply_effect(engine, state, enemy, definition.effect_id)
        assert enemy.spd == pytest.approx(base_spd * 0.5)
    finally:
        STATUS_EFFECTS._items.pop(definition.effect_id, None)
