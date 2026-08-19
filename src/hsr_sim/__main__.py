"""데모 실행.

    python -m hsr_sim                 # 전투 1회 자동 진행
    python -m hsr_sim --mode search   # 미래 상태 탐색(1수) 데모
"""

from __future__ import annotations

import argparse

from . import BattleConfig, BattleEngine, CritMode, build_battle, definitions


def make(
    config: BattleConfig,
    allies=("test_ally_a", "test_ally_b"),
    enemies=("test_enemy_a", "test_enemy_b"),
):
    state = build_battle(
        allies=definitions(*allies),
        enemies=definitions(*enemies),
        config=config,
    )
    engine = BattleEngine(config)
    engine.bind_abilities(state)
    return engine, state


def print_aggro(state) -> None:
    """적이 누구를 노릴 확률. 운명의 길에서 나온다 (docs/mechanics.md 6장)."""
    from .battle import aggro
    from .core.enums import Side
    from .registries import UNIT_DEFINITIONS

    weights = aggro.target_weights(state.living(Side.ALLY))
    print("파티 어그로 (적이 노릴 확률):")
    for unit in state.living(Side.ALLY):
        definition = UNIT_DEFINITIONS.get(unit.definition_id)
        path = definition.path.value if definition.path else "-"
        print(
            f"  {unit.uid} {definition.name!s:<12} {path:<12}"
            f" 어그로 {aggro.aggro_of(unit):6.1f}  ->  {weights[unit.uid]:.1%}"
        )
    print()


def demo_battle(config: BattleConfig) -> None:
    engine, state = make(
        config,
        allies=("test_ally_a", "test_ally_b", "test_ally_c"),
        enemies=("test_enemy_sequence", "test_enemy_smasher"),
    )
    engine.start_battle(state)
    print_aggro(state)
    outcome = engine.run(state)
    print(state.log.render())
    print("-" * 62)
    print(
        f"결과: {outcome.value} | 턴 수: {state.turn_count} | 누적 AV: {state.elapsed_av:.2f}"
        f" | 스킬 포인트: {state.skill_points}/{state.max_skill_points}"
    )
    for unit in state.all_units():
        energy = (
            f"  에너지 {unit.energy:6.1f} / {unit.max_energy:6.1f}"
            if unit.max_energy
            else ""
        )
        effects = (
            "  효과: " + ", ".join(f"{e.effect_id}x{e.stacks}" for e in unit.effects)
            if unit.effects
            else ""
        )
        print(
            f"  {unit.uid} HP {unit.current_hp:8.1f} / {unit.max_hp:8.1f}"
            f"  생존={unit.alive}{energy}{effects}"
        )


def demo_search(config: BattleConfig) -> None:
    """현재 상태에서 가능한 모든 행동을 분기시켜 미래 상태를 만들어 본다.

    최종 목표(행동 추천)의 기반이 되는 API 를 보여주는 데모다.
    평가 함수는 아직 없으므로 '적에게 준 총 피해'라는 임시 지표만 쓴다.
    """
    engine, state = make(config)
    engine.start_battle(state)
    uid = engine.advance_to_next_turn(state)
    print(
        f"현재 행동자: {uid} (누적 AV {state.elapsed_av:.2f}, 사이클 {state.cycle}, "
        f"스킬 포인트 {state.skill_points}/{state.max_skill_points})\n"
    )

    actions = engine.legal_actions(state)
    print(f"가능한 행동 {len(actions)}개:")
    for action in actions:
        branch = state.clone()
        engine.perform(branch, action)
        engine.end_turn(branch)
        dealt = sum(
            u.max_hp - u.current_hp for u in branch.all_units() if u.side.value == "enemy"
        )
        print(
            f"  - {action.describe():<32} 누적 피해 {dealt:8.1f}"
            f"   SP {branch.skill_points}   에너지 {branch.unit(uid).energy:5.1f}"
        )

    print("\n원본 상태는 변경되지 않는다:")
    for unit in state.all_units():
        print(f"  {unit.uid} HP {unit.current_hp:8.1f} / {unit.max_hp:8.1f}")


def demo_monster(config: BattleConfig, query: str, level: int) -> None:
    """임포트한 실제 적 데이터를 조회한다."""
    from .content import monsters
    from .stats.stat import Stat

    found = monsters.search(name=query, limit=8)
    if not found:
        print(f"'{query}' 에 해당하는 적을 찾지 못했습니다.")
        return

    for raw in found:
        definition = monsters.build_definition(raw["id"], level=level)
        stats = definition.base_stats
        print(f"[{raw['id']}] {definition.name.ko}  ({definition.name.en})  등급 {raw['rank']}")
        print(
            f"   Lv{level}  HP {stats[Stat.MAX_HP]:>10,.0f}  ATK {stats[Stat.ATK]:>7,.0f}"
            f"  DEF {stats[Stat.DEF]:>7,.0f}  SPD {stats[Stat.SPD]:>6,.1f}"
            f"  인성치 {definition.max_toughness:>5,.0f}"
        )
        weak = ", ".join(w.value for w in definition.weaknesses) or "없음"
        print(f"   약점: {weak}   효과 저항: {stats[Stat.EFFECT_RES]:.0%}")
        if definition.debuff_res:
            print(f"   상태이상 저항: {definition.debuff_res}")
        for skill in definition.skills.values():
            mult = "미해결" if not skill.multiplier_verified else f"{skill.multiplier:.2f}"
            print(
                f"     - {skill.name.ko:<24} {(skill.element.value if skill.element else '-'):<10}"
                f" {skill.target_rule.shape:<7} 배율 {mult}"
                f"  피격에너지 {skill.energy_grant_to_target:g}  지연 {skill.delay_ratio:g}"
            )
        print()
    print("※ 적 스킬의 피해 배율은 게임 데이터에서 복원하지 못했습니다. docs/data_sources.md 참고")


def main() -> None:
    parser = argparse.ArgumentParser(description="HSR 전투 시뮬레이터 V0.1 데모")
    parser.add_argument("--mode", choices=["battle", "search", "monster"], default="battle")
    parser.add_argument("--monster", default="쿠쿠리아", help="적 이름 검색어 (--mode monster)")
    parser.add_argument("--level", type=int, default=80, help="적 레벨 (--mode monster)")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--crit", choices=[mode.value for mode in CritMode], default=CritMode.ROLL.value
    )
    args = parser.parse_args()

    config = BattleConfig(seed=args.seed, crit_mode=CritMode(args.crit))
    if args.mode == "monster":
        demo_monster(config, args.monster, args.level)
    elif args.mode == "search":
        demo_search(config)
    else:
        demo_battle(config)


if __name__ == "__main__":
    main()
