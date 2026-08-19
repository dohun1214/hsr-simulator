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


def demo_verify(args) -> None:
    """실제 게임과 대조할 피해 계산 명세를 출력한다 (요구사항 13).

    **게임 화면의 최종 스탯을 그대로 입력받는 것**이 핵심이다.
    그러면 광추/유물/행적이 무엇이든 상관없이 **데미지 공식과 스킬 배율만** 검증된다.

        python -m hsr_sim --mode verify --character 카프카 \
            --atk 3200 --crit-rate 0.75 --crit-dmg 1.8 --dmg-bonus 0.466 \
            --enemy "얼음 서슬" --enemy-level 80 --skill-level 10
    """
    from .battle.damage import DamageContext, compute_damage
    from .content import characters, monsters
    from .core.enums import CritMode as _CritMode
    from .setup import spawn_unit
    from .stats.stat import Stat

    found_c = characters.search(name=args.character, limit=1)
    found_e = monsters.search(name=args.enemy, limit=1)
    if not found_c:
        print(f"'{args.character}' 캐릭터를 찾지 못했습니다.")
        return
    if not found_e:
        print(f"'{args.enemy}' 적을 찾지 못했습니다.")
        return

    cdef = characters.build_definition(
        found_c[0]["id"], level=args.level,
        skill_levels=args.skill_level, with_traces=args.traces,
    )
    edef = monsters.build_definition(found_e[0]["id"], level=args.enemy_level)
    attacker = spawn_unit(cdef, "A1", level=args.level)
    defender = spawn_unit(edef, "E1", level=args.enemy_level)

    # 게임 화면 값으로 덮어쓰기 (지정한 것만)
    overrides = {
        Stat.ATK: args.atk, Stat.CRIT_RATE: args.crit_rate, Stat.CRIT_DMG: args.crit_dmg,
    }
    manual = []
    for stat, value in overrides.items():
        if value is not None:
            attacker.base_stats[stat] = value
            manual.append(stat.value)

    source = "게임 화면 입력값" if manual else (
        "데이터 계산값 (행적 포함)" if args.traces else "데이터 계산값 (본체만)"
    )
    print(f"공격: {cdef.name.ko} Lv{args.level}  스킬 레벨 {args.skill_level}  [{source}]")
    print(f"  ATK {attacker.stat(Stat.ATK):,.2f}   치확 {attacker.stat(Stat.CRIT_RATE):.1%}"
          f"   치피 {attacker.stat(Stat.CRIT_DMG):.1%}   피해 증가 {args.dmg_bonus:.1%}")
    print(f"방어: {edef.name.ko} Lv{args.enemy_level}")
    print(f"  HP {defender.max_hp:,.0f}   DEF {defender.stat(Stat.DEF):,.0f}"
          f"   약점 {[w.value for w in edef.weaknesses]}   격파됨 {args.broken}")
    print()

    defender.toughness_broken = args.broken
    for skill in cdef.skills.values():
        if not skill.multiplier_verified:
            print(f"[{skill.kind.value}] {skill.name.ko} — 배율 미해결 (건너뜀)")
            continue
        element = skill.element or cdef.element
        ctx = DamageContext(
            attacker=attacker, defender=defender, element=element,
            multiplier=skill.multiplier, scaling=skill.scaling, tags=(skill.tag,),
            dmg_bonus=args.dmg_bonus, res_pen=args.res_pen,
            def_reduction=args.def_reduction, vulnerability=args.vulnerability,
        )
        plain = compute_damage(ctx, crit_mode=_CritMode.NEVER)
        crit = compute_damage(ctx, crit_mode=_CritMode.ALWAYS)
        print(f"[{skill.kind.value}] {skill.name.ko}   배율 {skill.multiplier:.0%} "
              f"{skill.scaling.value}   {element.value}   {skill.target_rule.shape}")
        print(f"   비치명타 {plain.amount:>12,.1f}      치명타 {crit.amount:>12,.1f}")
        print("   배수: " + "  ".join(
            f"{k} {v:.4f}" for k, v in plain.breakdown.items() if k not in ("base", "crit")
        ))

    warnings = [t for t in characters.major_traces(found_c[0]["id"]) if t["affects_damage"]]
    if warnings:
        print("\n※ 이 캐릭터의 특성 중 피해에 개입할 수 있는 것:")
        for trace in warnings:
            name = trace["name"]["ko"] or trace["name"]["en"] or trace["point_id"]
            desc = (trace["desc"]["ko"] or "").replace("\n", " ")[:90]
            print(f"   - {name}: {desc}")
        print("   측정할 때 이 조건들이 발동하지 않는 상황을 고르세요.")

    print("\n측정 방법")
    print("  1. 버프/디버프 없는 상태에서 첫 턴에 공격 (적 미격파, HP 만피)")
    print("  2. 비치명타 값을 기록 (치명타는 노란색으로 표시됨)")
    print("  3. 위 '비치명타' 값과 비교")


def main() -> None:
    parser = argparse.ArgumentParser(description="HSR 전투 시뮬레이터 V0.1 데모")
    parser.add_argument(
        "--mode", choices=["battle", "search", "monster", "verify"], default="battle"
    )
    parser.add_argument("--character", default="단항", help="캐릭터 검색어 (--mode verify)")
    parser.add_argument("--enemy", default="얼음 서슬", help="적 검색어 (--mode verify)")
    parser.add_argument("--enemy-level", type=int, default=80)
    parser.add_argument("--skill-level", type=int, default=10, help="스킬 레벨 (--mode verify)")
    parser.add_argument("--traces", action="store_true", help="스탯 행적을 모두 찍은 것으로 계산")
    parser.add_argument("--broken", action="store_true", help="적이 약점 격파된 상태")
    parser.add_argument("--atk", type=float, help="게임 화면의 최종 공격력")
    parser.add_argument("--crit-rate", type=float, help="게임 화면의 치명타 확률 (0.75)")
    parser.add_argument("--crit-dmg", type=float, help="게임 화면의 치명타 피해 (1.8)")
    parser.add_argument("--dmg-bonus", type=float, default=0.0, help="속성 피해 증가 (0.466)")
    parser.add_argument("--res-pen", type=float, default=0.0, help="속성 저항 관통")
    parser.add_argument("--def-reduction", type=float, default=0.0, help="방어력 감소")
    parser.add_argument("--vulnerability", type=float, default=0.0, help="받는 피해 증가")
    parser.add_argument("--monster", default="쿠쿠리아", help="적 이름 검색어 (--mode monster)")
    parser.add_argument("--level", type=int, default=80, help="적 레벨 (--mode monster)")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--crit", choices=[mode.value for mode in CritMode], default=CritMode.ROLL.value
    )
    args = parser.parse_args()

    config = BattleConfig(seed=args.seed, crit_mode=CritMode(args.crit))
    if args.mode == "verify":
        demo_verify(args)
    elif args.mode == "monster":
        demo_monster(config, args.monster, args.level)
    elif args.mode == "search":
        demo_search(config)
    else:
        demo_battle(config)


if __name__ == "__main__":
    main()
