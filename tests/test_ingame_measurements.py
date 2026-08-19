"""실제 게임에서 측정한 값과의 대조 (요구사항 13).

여기 있는 테스트는 **게임에서 직접 측정한 숫자**를 고정한다.
시뮬레이터가 이 값을 재현하지 못하면 어딘가가 회귀한 것이다.

측정할 때마다 이 파일에 사례를 추가한다.
"""

import pytest

from hsr_sim.battle.damage import DamageContext, compute_damage
from hsr_sim.content import characters, monsters
from hsr_sim.core.enums import CritMode
from hsr_sim.setup import spawn_unit
from hsr_sim.stats.stat import Stat

ACHERON = 1308
SECURITY_HOUND = 5012020  # 보안의 충견


def test_acheron_basic_attack_on_security_hound():
    """2026-08-19 측정 — 도훈

    조건
      - 아케론 Lv80, 성혼 2, 행적 전부, **광추/유물 해제**
      - 파티에 아케론 혼자 (허무 캐릭터 없음 -> 특성 「나락」 비활성)
      - 일반 공격 Lv6 (배율 100%)
      - 대상: 모조 꽃받침의 보안의 충견 Lv56, 번개 약점 아님, 미격파
      - 비치명타

    게임 표시 스탯: 치확 5.0% / 치피 74.0% / 번개 피해 증가 8%
    **실측 피해: 395**

    이 한 사례가 동시에 검증하는 것
      1. 데미지 곱연산 파이프라인 전체
      2. DEF 배수 = 1 - DEF / (DEF + 200 + 10 x 공격자 레벨)
      3. 적 기본 DEF = 200 + 10 x 레벨  (Lv56 -> 760)
      4. 비약점 속성 저항 20%
      5. 미격파 시 범용 피해 감소 0.9
      6. 적 레벨 스케일링 (HardLevelGroup)
      7. 캐릭터 레벨 스케일링 (승급 Base + Add x (Lv-1))
      8. 행적 스탯 합계 (공격력 +28%)
      9. 스킬 배율 추출 (일반 공격 Lv6 = 100%)
     10. 속성 피해 증가가 데미지 파이프라인에 반영되는지
    """
    MEASURED = 395.0

    character = characters.build_definition(
        ACHERON, level=80, skill_levels={"basic": 6}, with_traces=True
    )
    enemy = monsters.build_definition(SECURITY_HOUND, level=56)

    attacker = spawn_unit(character, "A1", level=80)
    defender = spawn_unit(enemy, "E1", level=56)

    # 게임 화면에 표시된 값과 일치하는지 먼저 확인
    assert attacker.stat(Stat.CRIT_RATE) == pytest.approx(0.05)
    assert attacker.stat(Stat.CRIT_DMG) == pytest.approx(0.74)
    assert attacker.extra["elemental_dmg_bonus"]["lightning"] == pytest.approx(0.08)
    assert attacker.stat(Stat.ATK) == pytest.approx(894.14, abs=0.01)
    # 적 Lv56 방어력 = 200 + 10 x 56
    assert defender.stat(Stat.DEF) == pytest.approx(760.0, abs=0.5)
    # 번개는 약점이 아니다
    assert defender.res_to(character.element) == pytest.approx(0.2)

    basic = character.skills[character.basic_attack_id]
    assert basic.multiplier == pytest.approx(1.0)  # Lv6

    ctx = DamageContext(
        attacker=attacker,
        defender=defender,
        element=character.element,
        multiplier=basic.multiplier,
        scaling=basic.scaling,
        tags=(basic.tag,),
        dmg_bonus=attacker.extra["elemental_dmg_bonus"]["lightning"],
    )
    result = compute_damage(ctx, crit_mode=CritMode.NEVER)

    # 게임은 정수로 표시하므로 반올림 오차 1 이내면 일치로 본다
    assert result.amount == pytest.approx(MEASURED, abs=1.0)

    # 각 배수도 개별로 고정한다
    assert result.breakdown["dmg_boost"] == pytest.approx(1.08)
    assert result.breakdown["def"] == pytest.approx(1 - 760 / (760 + 200 + 800))
    assert result.breakdown["res"] == pytest.approx(0.8)
    assert result.breakdown["broken"] == pytest.approx(0.9)


def test_acheron_nihility_trace_is_inactive_when_solo():
    """특성 「나락」은 허무 캐릭터가 있어야 발동한다 (115% / 160%).

    측정을 아케론 혼자 한 이유이며, 실측이 맞았다는 것은
    혼자일 때 이 배수가 곱해지지 않는다는 뜻이기도 하다.
    """
    traces = characters.major_traces(ACHERON)
    abyss = next(t for t in traces if t["name"]["ko"] == "나락")
    assert abyss["params"] == [1.15, 1.6]
    assert abyss["affects_damage"] is True
