# 붕괴: 스타레일 전투 메커니즘 조사 노트

이 문서는 시뮬레이터가 구현한 규칙의 **근거**를 기록한다.
코드에서 상수나 공식을 바꿀 때는 반드시 이 문서를 함께 갱신한다.

표기:

- **[확인됨]** 복수의 신뢰 가능한 자료가 일치함
- **[유도됨]** 자료들이 직접 서술하지는 않았지만, 서로 다른 자료의 식이 대수적으로 일치하여 도출됨
- **[미확인]** 근거를 찾지 못함. 코드에서는 명시적 가정으로 분리해 두었고 향후 실측 검증 필요

조사일: 2026-08-19

---

## 1. Speed / Action Value / Action Gauge

### 1.1 기본 식 **[확인됨]**

> "Base AV = Default AG / Speed, Default AG = 10000"
> — KQM Speed Guide

> "For every 1 AV that passes, a character's current Speed is subtracted from their Action Gauge."
> — KQM Speed Guide

즉 게임 내부는 **Action Gauge(AG)** 를 들고 있고, AV는 파생값이다.

```
AG_full = 10000
AV_남은시간 = AG_현재 / SPD
1 AV 경과 → AG -= SPD
```

**설계상 중요한 점**: 우리 시뮬레이터도 AV가 아니라 **AG를 상태로 저장**한다.
AV를 저장하면 턴 도중 SPD가 변할 때 남은 시간을 어떻게 환산할지 임의로 정해야 하지만,
AG를 저장하면 `AV = AG / SPD` 가 자동으로 올바르게 재계산된다.
(버프/디버프로 SPD가 바뀌는 상황을 정확히 재현하기 위한 핵심)

### 1.2 행동 후 **[확인됨]**

> "their AG goes back to its initial value of 10000 and they are placed back in the Action Order accordingly."
> — KQM Speed Guide

### 1.3 전투 시작 시 **[확인됨]**

> "At the beginning of the battle, each unit's Action Value ... is set to their Base Action Value"
> "effects that take effect upon entering battle, including SPD/AV modifying effects, are triggered on characters from left to right."
> — Fandom Wiki, Speed

### 1.4 행동 순서 선택 **[확인됨]**

> "The unit with the lowest Action Value ... is selected to be the next active unit.
> All units subtract that lowest Action Value from their current Action Value."
> — Fandom Wiki, Speed

### 1.5 행동 앞당기기 / 늦추기 **[확인됨]**

> "New Action Gauge = max(0, Current Action Gauge - 10000 * (Advance Forward% - Action Delay%))"
> "1% of AG Modify is equal to 100 Units of Action Gauge."
> — KQM Speed Guide

즉시 행동(`immediately take action`)은 비율이 아니라 **AG를 0으로 강제 설정**한다. **[확인됨, Fandom Wiki Speed]**

> "forcibly set the current Action Value of the target to 0, regardless of their Action Value prior to that."

### 1.6 사이클(Cycle) **[확인됨]**

> "The first cycle at the start of each wave in a battle lasts for 150 AV.
> Once the first cycle has passed, subsequent cycles last for 100 AV each."
> — Fandom Wiki, Speed

누적 AV 기준 경계: `150, 250, 350, 450, ...`

### 1.7 동점(tie) 처리 **[미확인]**

AV가 완전히 동일할 때 누가 먼저 행동하는지에 대한 명시적 규칙을 찾지 못했다.

- 구현: `TieBreakPolicy` 로 분리하고, 기본값은 **등록 순서(아군 파티 순서 → 적 순서)** 로 고정.
- 결정론은 보장되지만 **실제 게임과 일치한다는 보장은 없다.**
- 향후 실측(동일 SPD 캐릭터 2명 배치)으로 검증 필요. `docs/roadmap.md` 의 Open Questions 참고.

---

## 2. 데미지 공식

### 2.1 전체 구조 **[확인됨]**

> "Damage = Base DMG x CRIT x DMG% Multiplier x DEF Multiplier x RES Multiplier
> x DMG Taken Multiplier x Toughness Multiplier"
> — KQM SRL, complete damage formula

Fandom Wiki 는 여기에 **Weaken Multiplier** 와 **DMG Mitigation Multiplier** 를 추가로 나열한다.
따라서 우리 파이프라인은 다음 슬롯을 모두 가진다 (V0.1 에서 미구현 슬롯은 항등원 1.0).

```
DMG = BaseDMG
    x CritMultiplier
    x DmgBoostMultiplier
    x WeakenMultiplier          (V0.1: 1.0)
    x DefMultiplier
    x ResMultiplier
    x VulnerabilityMultiplier
    x MitigationMultiplier      (V0.1: 1.0)
    x BrokenMultiplier
```

### 2.2 Base DMG **[확인됨]**

> "(Skill MV + Extra MV) x ATK + Extra DMG" (ATK 스케일링)
> DEF 스케일링, Max HP 스케일링 형태도 동일 구조
> — KQM SRL

### 2.3 CRIT **[확인됨]**

```
치명타 발생 시: 1 + CRIT DMG
비발생 시:      1
기대값 계산 시: 1 + clamp(CRIT Rate, 0, 1) x CRIT DMG
```

### 2.4 DMG% Multiplier **[확인됨]**

```
1 + 속성 DMG% + 전체 DMG% + DoT DMG% ...
```

### 2.5 DEF Multiplier **[확인됨]**

> "DEF Multiplier = 100% - [DEF / (DEF + 200 + 10 * Attacker Level)]"
> "DEF = Base DEF * (100% + DEF% - (DEF Reduction + DEF Ignore)) + Flat DEF, 최소 0"
> — Prydwen, Damage Formula

**방어 감소(DEF Reduction)와 방어 무시(DEF Ignore)는 계산식에서 같은 자리에 더해지지만,
개념적으로 다르다** (감소는 실제 DEF 스탯을 낮추고, 무시는 해당 판정에만 적용).
구현에서도 필드를 분리해 두었다. **[확인됨, Fandom Wiki DEF]**

### 2.6 적 기본 DEF와 레벨 **[유도됨]**

KQM 은 같은 식을 레벨만으로 표현한다.

> "DEF Multiplier = (Level_Character + 20) / ((Level_Enemy + 20) + (Level_Character + 20))"
> — KQM SRL

Prydwen 식에 `DEF = 200 + 10 x Level_Enemy` 를 대입하면

```
1 - (200 + 10Le) / ((200 + 10Le) + (200 + 10La))
  = (200 + 10La) / ((200 + 10Le) + (200 + 10La))
  = (20 + La) / ((20 + Le) + (20 + La))
```

로 KQM 식과 정확히 일치한다. 따라서 **적의 기본 DEF = 200 + 10 x 레벨** 로 본다.

단, Fandom Wiki 는 "적의 기본 DEF는 레벨로 결정된다"고만 하고 식을 제시하지 않았다.
→ 코드에서는 `default_enemy_base_def(level)` 헬퍼로 **분리**해 두었고,
   적 데이터에 DEF 가 명시되어 있으면 그 값을 우선한다.
   (즉 이 유도가 틀려도 실제 적 데이터를 넣는 순간 영향이 없다.)

### 2.7 RES Multiplier **[확인됨]**

```
RES Multiplier = 100% - (RES% - RES PEN%)
```

- 적의 기본 속성 저항은 20% (약점/저항 속성 제외)
- 약점 속성이면 RES = 0%
- 저항 속성이면 RES = 40%
- 유효 RES 범위는 -100% ~ 90% 로 제한 → 배수 범위 0.1 ~ 2.0
— Prydwen, Damage Formula

### 2.8 Toughness / Broken Multiplier **[확인됨]**

> "0.9 if Enemy has Toughness; 1.0 if Toughness broken" — KQM SRL
> "10% Universal DMG Reduction, which is reduced to 0% when broken" — Prydwen

V0.1 은 Toughness 시스템 자체(약점 격파, 감소량, 회복)를 구현하지 않지만,
**데미지 수치를 실제 게임과 맞추려면 이 0.9 는 반드시 필요**하므로
유닛에 `toughness_broken: bool` 플래그만 두고 기본값 `False`(=0.9 적용)로 시작한다.

**적용 대상 [유도됨]**: 이 10% 범용 피해 감소는 인성치 게이지를 가진 대상의 특성이다.
플레이어 캐릭터는 인성치 게이지가 없으므로 적용하지 않는다.
구현에서는 `max_toughness <= 0` 인 대상에는 배수 1.0 을 쓴다.
(자료가 "Enemy has Toughness" 라고만 서술하므로, 캐릭터 피격 시 이 항이 없다는 것은
직접 인용이 아니라 해석이다. 향후 실측 검증 대상 — roadmap 의 Open Questions 참고.)

---

## 3. 스킬 포인트 (Skill Point)

조사일: 2026-08-19

### 3.1 기본 규칙 **[확인됨]**

> "You start each battle with 3 Skill Points"
> "You can hold up to 5 Skill Points, and Skill Points are shared across all characters within the team."
> "Basic ATKs generate one Skill Point, while most Skills consume one Skill Point."
> — KQM Beginner Guide

> "You can hold up to a maximum of 5 Skill Points and they are shared between the whole team."
> "You cannot activate a Skill ability if you do not have any Skill Points."
> — Prydwen, Introduction to the Game

정리:

```
시작       3
최대       5   (파티 공유. 일부 캐릭터가 상한을 올리는 경우가 있어 가변 필드로 둔다)
일반 공격  +1
전투 스킬  -1  (대부분. 캐릭터별로 다를 수 있어 스킬 데이터에 둔다)
상한 초과분은 버려진다
```

- 스킬 포인트는 **아군 파티의 공유 자원**이다. 적은 사용하지 않는다.
- 포인트가 없으면 전투 스킬을 선택할 수 없다 → `legal_actions()` 에서 걸러야 한다.

### 3.2 미확인

- 상한 초과 시 버려지는 것이 맞는지 명시적 서술은 못 찾았다. 일반적인 이해대로 버린다. **[유도됨]**

---

## 4. 에너지와 필살기

### 4.1 에너지 획득량 **[확인됨]**

> Basic Attack: "Generates 20 Energy"
> Skill ability: "Generates 30 Energy"
> Ultimate ability: "Generates 5 Energy"
> Defeating enemies: "Generates 10 Energy/enemy"
> Getting hit: "Energy gained will vary depending on the enemy"
> — Prydwen, Introduction to the Game

### 4.2 에너지 회복 효율 (ERR) **[확인됨]**

> "The amount of Energy gained from each of the actions listed above can be increased by
> increasing the Character's Energy Regeneration Rate stat."
> — Prydwen

> "Note that some Energy-generating effects are not affected by Energy Regeneration Rate."
> — Fandom Wiki, Energy Regeneration Rate

> 위 4가지 행동 기반 획득에 대해 "increased based on the character's Energy Regeneration Rate"
> — KQM Beginner Guide

즉 **행동으로 얻는 에너지에는 ERR 이 곱해지고, 특성/광추의 "에너지 N 회복" 같은
고정 회복에는 곱해지지 않는다.**

구현: 에너지 지급 함수에 `apply_err: bool` 인자를 두고, 행동 기반은 True, 고정 회복은 False.

```
실제 획득량 = 기본 획득량 x (1 + ERR 보너스)
```

우리 구현에서 `Stat.ENERGY_REGEN_RATE` 는 게임 표기 100% 를 **0.0(=+0%)** 으로 잡는다.
즉 배수는 `1 + stat` 이다. (치명타 확률 등 다른 가산 스탯과 표현을 통일하기 위함)

### 4.3 필살기 사용 규칙 **[확인됨]**

> "Using an Ultimate ability during the Character's turn does not end that Character's turn."
> "Ultimate abilities can also be used when it is not currently the Character's turn ...
> the Character will immediately activate their Ultimate ability after the current turn ends.
> This allows you to interrupt the normal turn order flow."
> "Multiple Ultimates can also be chained in this way."
> — Prydwen

> "Ultimates can be cast at any time; they immediately interrupt the action queue after the
> current attack is completed."
> — KQM Beginner Guide

정리 (구현에 중요):

- 필살기는 **턴을 소모하지 않는다.** 행동 게이지를 되돌리지 않고, AV 도 흐르지 않는다.
- 자기 턴 중에 써도 그 턴은 유지된다 (필살기 후 일반 공격/스킬을 그대로 할 수 있다).
- 자기 턴이 아닐 때 쓰면 **현재 턴이 끝난 직후**에 발동한다.
- 여러 필살기를 연달아 발동할 수 있다.

> "Most Ultimates can only be used once Energy reaches max"
> — Fandom Wiki, Energy

### 4.4 미확인 **[미확인]**

| 항목 | 현재 처리 |
|---|---|
| 피격 시 얻는 에너지의 정확한 값 | 자료가 "적에 따라 다르다"고만 함. 스킬 데이터의 `energy_grant_to_target` 필드로 두고 기본 10 |
| 필살기의 +5 가 소모 이후에 지급되는지, ERR 이 곱해지는지 | 소모 후 지급, ERR 적용으로 구현 |
| 처치 시 +10 을 누가 받는지 (막타 캐릭터인지 전원인지) | 막타를 넣은 캐릭터가 받도록 구현 |
| 에너지 상한 초과분 처리 | 버린다 (일부 캐릭터의 초과 저장은 예외 메커니즘으로 취급) |

이 항목들은 실측으로 확정되면 `docs/roadmap.md` 의 Open Questions 에서 제거한다.

---

## 5. 참고 자료

- KQM — How Do Speed and Turn Order Work in Honkai: Star Rail? <https://hsr.keqingmains.com/misc/speed-guide/>
- KQM SRL — Complete Damage Formula <https://github.com/KQM-git/SRL/blob/master/docs/combat-mechanics/damage/damage-formula.md>
- Fandom Wiki — Speed <https://honkai-star-rail.fandom.com/wiki/Speed>
- Fandom Wiki — Damage <https://honkai-star-rail.fandom.com/wiki/Damage>
- Fandom Wiki — DEF <https://honkai-star-rail.fandom.com/wiki/DEF>
- Prydwen — Damage Formula <https://www.prydwen.gg/star-rail/guides/damage-formula>
- Prydwen — Introduction to the Game <https://www.prydwen.gg/star-rail/guides/introduction-to-the-game>
- KQM — Beginner Guide <https://hsr.keqingmains.com/misc/beginner-guide/>
- Fandom Wiki — Energy <https://honkai-star-rail.fandom.com/wiki/Energy>
- Fandom Wiki — Energy Regeneration Rate <https://honkai-star-rail.fandom.com/wiki/Energy_Regeneration_Rate>
