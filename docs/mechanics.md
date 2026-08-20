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

### 2.6 적 기본 DEF와 레벨 **[확인됨 — 실측]**

> **2026-08-19 실측으로 확정.** 보안의 충견 Lv56 의 DEF 가 정확히 760 = 200 + 10 x 56 이고,
> 이를 포함한 피해 계산이 실제 게임 값과 일치했다 (`tests/test_ingame_measurements.py`).
> 아래는 원래의 유도 과정이다.


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

**2026-08-19 실측**: 미격파 상태의 적을 때린 피해가 0.9 를 포함한 계산과 일치했다
(`tests/test_ingame_measurements.py`). 다만 격파 상태와의 비교는 아직 하지 못해
"0.9 가 곱해진다"는 것만 확인되었고 "격파 시 1.0 이 된다"는 아직 미확인이다.

**2026-08-20 게임 데이터 확인**: 이 항의 정체를 찾았다.
`GlobalModifier_Common_Specific.json` 의 `MonsterAllDamageReduce` 가
`AllDamageReduce +0.1` 짜리 모디파이어이고, 격파 상태(`StanceBreakState`)가
**풀릴 때 다시 붙는다**. 즉 격파 중에는 이 모디파이어가 없다
→ **"격파 시 1.0 이 된다"가 게임 데이터로 확인되었다.** 자세한 것은 8.4.

**적용 대상 [유도됨 → 보강]**: 이 10% 범용 피해 감소는 인성치 게이지를 가진 대상의 특성이다.
플레이어 캐릭터는 인성치 게이지가 없으므로 적용하지 않는다.
구현에서는 `max_toughness <= 0` 인 대상에는 배수 1.0 을 쓴다.
모디파이어 이름이 `**Monster**AllDamageReduce` 인 것이 이 해석을 뒷받침한다.

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

## 5. 상태 효과 (버프 / 디버프)

조사일: 2026-08-19

### 5.1 분류 **[확인됨]**

> "There are 3 distinct types of Status Effects: Buffs, Debuffs, and Other Effects."
> 디버프 하위 분류: "Crowd Control", "DoT", "Slow", "Weaken"
> — Fandom Wiki, Status Effect

### 5.2 해제 **[확인됨]**

> "Buffs applied to enemies can be removed by certain abilities, unless stated otherwise."
> 디버프도 "(Unremovable)" 표기가 없으면 제거 가능
> — Fandom Wiki, Status Effect

→ 효과 정의에 `removable` 플래그를 둔다.

### 5.3 중첩 **[확인됨 — 단, 일반 규칙은 없음]**

중첩 상한은 효과마다 데이터로 정해져 있다.

> "Wind Shear can stack up to 5 time(s)", "Arcana can stack up to 50 times",
> "Deep Freeze: Can stack up to 3 time(s)"
> — Fandom Wiki, Status Effect

일반 규칙이 존재하지 않으므로 `max_stacks` 를 **효과 데이터**로 둔다.
재적용 시 동작(지속시간 갱신 / 중첩 증가 / 둘 다)도 마찬가지로 `refresh` 정책으로 데이터화한다.

### 5.4 디버프 적용 확률 **[부분 확인]**

> "Real Chance = Skill Base Chance x (1 + Effect Hit Rate) x (1 - Effect RES) x (1 - Debuff RES)"
> — ManaBuy, Effect Hit Rate 가이드

공개된 EHR 계산기도 정확히 같은 4개 변수(기본 확률 / 효과 명중 / 효과 저항 / 디버프 저항)를
입력으로 받는다. Fandom 은 "Effect RES 가 Debuff RES 와 함께 확률을 낮춘다"고만 하고
식은 제시하지 않는다.

→ 위 곱연산 형태로 구현하되 **[부분 확인]** 으로 표시한다. 최종 확률은 1.0 으로 상한.

버프(아군이 아군에게 거는 것)는 이 판정을 거치지 않는다.

### 5.5 지속시간 감소 시점 **[미확인]**

Fandom 은 개별 효과 설명에서 "decreases by 1 turn at the start of Huohuo's every turn"
처럼 **효과마다 다르게** 서술하고, 일반 규칙은 제시하지 않는다.

구현:

- `DurationTiming` 열거형으로 효과마다 지정 (`OWNER_TURN_END` / `OWNER_TURN_START`)
- 기본값은 **소유자의 턴 종료 시 1 감소**

기본값을 이렇게 정한 이유: "2턴 지속" 인 DoT 가 정확히 2번 발동하려면
`턴 시작 → DoT 발동 → 행동 → 턴 종료 → 지속시간 감소` 순서여야 한다.
턴 시작에 감소시키면 발동 횟수가 1회 줄어든다.
**게임 자료로 확인한 것이 아니라 관측되는 동작에 맞춘 선택**이므로 실측 대상이다.

### 5.6 DoT (지속 피해)

**발동 시점 [확인됨]**

> "DoT is a type of damage dealt through certain debuffs at the beginning of a target's turn."
> — Fandom Wiki, DoT

**치명타 [확인됨, 2개 자료]**

> "Unlike regular damage, DoT cannot score CRIT hits." — Fandom Wiki, DoT
> "all types of DoT, whether normal or break, cannot land critical hits." — GachaGuru

**계산식 [확인됨]**

> "DoTs applied by character abilities ... have their DMG calculated very similarly to
> regular damage, with the only difference being that CRIT is not taken into account."
> — Fandom Wiki, DoT

즉 우리 데미지 파이프라인을 그대로 쓰되 치명타 배수만 1.0 으로 고정한다.
`DMG% Multiplier` 에 DoT DMG% 가 포함된다는 것도 Prydwen 에서 확인됨.

**처리 순서 [확인됨]**

> "DoTs are dealt in chronological order based on when they are inflicted, with DoTs
> inflicted earlier dealt first"
> — Fandom Wiki, DoT

→ 효과에 부여 순번(`applied_seq`)을 저장하고 그 순서로 발동한다.

**스냅샷 여부 [미확인]**

부여 시점의 시전자 스탯을 고정하는지, 발동 때마다 다시 계산하는지 자료를 찾지 못했다.

구현: `BattleConfig.dot_snapshot` (기본 True) 로 두 방식을 모두 지원하고,
스냅샷 모드에서는 부여 시점의 기본 피해량과 시전자 레벨을 효과에 저장한다.
방어 측 배수(DEF/RES/취약/격파)는 두 모드 모두 **발동 시점의 값**을 쓴다.

---

## 6. 어그로 (도발치) — 적의 대상 선택

조사일: 2026-08-19

적의 공격 대상은 **완전 무작위가 아니다.** 캐릭터의 운명의 길에 따라 정해지는
기본 어그로 값에 비례한 확률로 결정된다.

### 6.1 운명의 길별 기본 어그로 **[확인됨 — 3개 자료 교차검증]**

| 운명의 길 | 기본 어그로 | Fandom 표기 |
|---|---|---|
| 보존 (Preservation) | 150 | 6 |
| 파멸 (Destruction) | 125 | 5 |
| 동조 (Harmony) | 100 | 4 |
| 허무 (Nihility) | 100 | 4 |
| 풍요 (Abundance) | 100 | 4 |
| 기억 (Remembrance) | 100 | 4 |
| 환락 (Elation) | 100 | 4 |
| 수렵 (The Hunt) | 75 | 3 |
| 지식 (Erudition) | 75 | 3 |

Fandom 과 KQM 은 3/4/5/6 으로, GamesRadar 와 GachaGuru 는 75/100/125/150 으로 적는다.
**두 스케일은 정확히 25배 관계**이므로 같은 값이다 (75/25=3, 100/25=4, 125/25=5, 150/25=6).
서로 다른 출처가 같은 비율을 제시한다는 점에서 신뢰도가 높다.

우리 구현은 게임 내부 값에 가까운 **75/100/125/150** 을 쓴다.

### 6.2 대상 선택 확률 **[확인됨 — 2개 자료]**

> "Probability of Being Targeted = Aggro Character / ∑ Aggro Team"
> — Fandom Wiki, Aggro / GachaGuru

즉 각 캐릭터가 노려질 확률은 **자신의 어그로 / 살아 있는 아군 어그로 총합**이다.

### 6.3 어그로 수정자 **[확인됨 — 2개 자료]**

> "Aggro = Base Aggro x (1 + Aggro Modifier)"
> — Fandom Wiki, Aggro / GachaGuru

여러 수정자는 괄호 안에서 **가산**된다.

> 예: 겁화 150 x (1 + 3 + 2) = 900 — GachaGuru

이 형태는 우리 스탯 계산식 `기본값 x (1 + 퍼센트 합) + 고정값 합` 과 **정확히 같다.**
따라서 어그로를 별도 시스템이 아니라 `Stat.AGGRO` 로 두면
기존 버프/디버프/특성 시스템이 그대로 어그로를 조작할 수 있다.

실제 예시 (자료에 언급된 값):

- 인랑(Blade) 스킬: 자신 어그로 +1000%
- 클라라(Clara) 필살기: 자신 어그로 +500%
- 단항(Dan Heng), 제레(Seele): 행적으로 자신 기본 어그로 -50%
- 옌칭(Yanqing): 특성으로 자신 기본 어그로 -60%

### 6.4 어그로를 무시하는 공격 **[확인됨]**

> "Some enemies have Bounce attacks - such attacks are unaffected by Aggro and all
> characters have an equal chance to get hit."
> 또한 적은 "Lock On" 으로 특정 캐릭터를 지정할 수 있다.
> — Fandom Wiki, Aggro

→ 대상 규칙(`TargetRule.selection`)에 `"aggro"` / `"uniform"` / `"lowest_hp"` 를 두어
   스킬 데이터로 표현한다.

### 6.5 미확인 **[미확인]**

| 항목 | 현재 처리 |
|---|---|
| 확산/전체 적 공격이 주 대상을 어그로로 고르는지 | 주 대상 선택에 어그로를 적용 |
| 전투 불능 캐릭터가 후보에서 제외되는지 | 제외 (생존 캐릭터만 후보) |
| 아군이 적을 자동 선택할 때의 규칙 | 어그로 개념 없음. 별도 정책 사용 |

---

## 7. 적의 행동 패턴 (AI)

조사일: 2026-08-19. **게임 데이터 파일을 직접 확인한 결과다** (docs/data_sources.md 참고).

적은 무작위로 행동하지 않는다. `Config/ConfigAI/Monster_*.json` 에 362개의 AI 정의가 있다.

### 7.1 AI 구조 **[확인됨 — 게임 데이터]**

```json
{
  "AIName": "Monster_AML_Minion01_00",
  "VariableList": [ { "Name": "CurrentPhase", "Value": "DG_010_Phase01" } ],
  "DecisionList": [
    {
      "DecisionName": "UseSkill01",
      "RootTask": { "$type": "SequenceConfig", "TaskList": [
          { "$type": "SelectAISkillTarget", "SkillName": "Skill01", "Selector": {...} },
          { "$type": "UseSkill", "SkillName": "Skill01" } ] },
      "ScoreEvaluatorType": "DefaultDSE",
      "ConsiderAxisList": [
        { "$type": "CheckSkillUsabilityAxis", "SkillName": "Skill01",
          "InitialCD": 1, "CD": 1, "CheckScore": { "Value": 0.1 } } ]
    }
  ]
}
```

즉 **효용 기반(Utility AI) 결정 시스템**이다.

- AI 는 `Decision` 목록을 가진다
- 각 Decision 은 `ConsiderAxisList` 로 **점수**를 계산한다
- 점수가 가장 높은 Decision 의 `RootTask` 를 실행한다 (`ScoreEvaluatorType` 은 전부 `DefaultDSE`)

362개 AI 전체 통계:

- Decision 개수: 1~11개 (2개가 가장 흔함)
- 결정당 axis 개수: **1개가 1917건**, 0개 17건, 2개 13건 → 사실상 "조건 1개 + 점수 1개"
- axis 종류: `CheckPredicateAxis` 1889 / `CheckSkillUsabilityAxis` 52 / `ChoseSequencedSkillAxis` 2
- `SuccessScore` 분포: **0.5 가 1362건**, 1 이 437건, 0.4 / 0.9 / 0.99 / 1.5 / 2 소수
- 스킬 쿨다운 `(InitialCD, CD)`: (1,1) 43건, (2,2) 3건, (5,6) / (3,3) / (2,1) / (1,3) / (1,2) / (1,0) 각 1건

### 7.2 가장 흔한 AI: 고정 스킬 순환 **[확인됨 — 게임 데이터]**

613개 몬스터 템플릿 중 **158개**가 `Monster_Common_SequenceThree_AI.json` 을 쓴다.
그 내용은 단 하나의 Decision 이다.

```json
{ "DecisionName": "UseSequenceSkill",
  "RootTask": { "TaskList": [ { "$type": "UseSequencedSkill" } ] },
  "ConsiderAxisList": [ { "$type": "ChoseSequencedSkillAxis", "CheckScore": 1 } ] }
```

실제 순환 목록은 몬스터 데이터의 `AISkillSequence` (또는 `OverrideAISkillSequence`) 에 있다.
길이 분포: 1개 175, 3개 37, 2개 28, 5개 19, 6개 7, 8개 2, 4개 2.

즉 **대부분의 잡몹은 "정해진 스킬을 순서대로 반복"** 한다.

### 7.3 조건(Predicate)의 종류 **[확인됨 — 게임 데이터]**

`CheckPredicateAxis` 안에서 쓰이는 조건들 (등장 횟수):

| 조건 | 횟수 | 의미 |
|---|---|---|
| `ByIsContainModifier` | 328 | 특정 상태 효과를 가지고 있는가 |
| `ByCompareCharacterNumber` | 199 | 살아 있는 캐릭터 수 비교 |
| `ByCompareDynamicValue` | 90 | AI 내부 카운터 비교 |
| `ByCompareMonsterID` | 43 | 특정 몬스터인가 |
| `ByCheckCustomValueBool` | 35 | 커스텀 플래그 |
| `ByCompareMonsterPhase` | - | 현재 페이즈 비교 |
| `ByAnd` / `ByAny` | 37 / 36 | 논리 조합 |

행동 순환은 `DefineDynamicValue` (1845회), `SetDynamicValue` (165회),
`SetDynamicValueByAddValue` (166회) 로 관리되는 **카운터**로 구현되어 있다.

### 7.4 대상 선택 **[확인됨 — 게임 데이터]**

`UseSkill` 2393건 중 `SelectAISkillTarget` 이 붙은 것은 301건뿐이다.
나머지는 **기본 대상 선택(=어그로, docs/mechanics.md 6장)** 을 쓴다.
지정 선택은 `AIModifierNameSelector` (특정 상태 효과가 걸린 대상) 형태가 대부분이다.

### 7.5 행동 게이지 관련 데이터 **[확인됨 — 게임 데이터]**

- `MonsterSkillConfig.DelayRatio` — 스킬 사용 후 행동 게이지 배수.
  1 이 3389건이고 1.25 / 1.5 / 1.75 / 2 / 0.5 등이 존재.
  → 큰 기술일수록 다음 턴이 늦게 온다.
- `MonsterTemplateConfig.InitialDelayRatio` — 전투 시작 시 행동 게이지 배수.
  1 이 545건, **0.5 가 51건**, 0.25 / 0.75 / 0.2 / 1.5 소수.
  → 일부 적은 처음부터 빠르게/느리게 등장한다.

두 값 모두 우리 AG 모델에 그대로 대응한다: `AG = 10000 x ratio`.

**[유도됨]**: 데이터 필드명과 값 분포로부터의 해석이다. 필드 설명 문서는 없다.

### 7.6 적의 기본 저항 **[확인됨 — 게임 데이터]**

`MonsterTemplateConfig.StatusResistanceBase` 분포: 0.2 가 267개, 0.3 이 193개, 0.1 이 77개.
→ **적은 기본 효과 저항을 가진다.** 기본값 0 으로 두면 안 된다.

`MonsterConfig.DebuffResist` 는 **효과 id 가 아니라 태그** 단위다
(`STAT_CTRL`, `STAT_CTRL_Frozen`, `STAT_Confine`, `STAT_Entangle`, `STAT_DOT_Burn` ...).
따라서 상태 효과에 태그를 붙이고, 저항은 태그로 조회해야 한다.

`STAT_CTRL` 과 `STAT_CTRL_Frozen` 이 동시에 존재하므로 태그는 계층적이다.
여러 태그가 걸리면 **가장 큰 저항**을 쓴다 — **[유도됨]**, 합산인지 최댓값인지는 미확인.

### 7.7 미확인 **[미확인]**

| 항목 | 현재 처리 |
|---|---|
| 동점 점수 Decision 의 선택 규칙 (0.5 가 압도적으로 많다) | 목록 순서상 먼저 오는 것을 선택 |
| 스킬 순환의 시작 위치와 되감기 규칙 | 0번부터 시작해 순환 |
| 쿨다운이 감소하는 시점 | 소유자의 턴 종료 시 1 감소 |
| 페이즈 전환 조건 | 데이터에 조건 없음. 외부에서 `set_phase()` 로 지정 |
| 태그별 저항이 합산인지 최댓값인지 | 최댓값 |

---

## 8. 인성치와 약점 격파

조사일: 2026-08-19

### 8.1 인성치 감소 조건 **[확인됨 — 게임 데이터]**

공격의 속성이 대상의 **약점 속성과 일치할 때만** 인성치가 깎인다.

게임 데이터 근거:

- 캐릭터 스킬의 `ShowStanceList[0]` 이 인성치 감소량이다 (일반 공격 30, 전투 스킬 60, 필살기 90 등)
- 스킬마다 `StanceDamageType` 이 따로 있다 → 인성치를 깎는 속성이 명시되어 있다
- 적의 `StanceWeakList` 가 약점 속성, `StanceBase` 가 최대 인성치

예외가 존재한다는 것도 데이터로 확인된다. 아케론의 특성 「비에 젖은 단풍, 끝없는 하늘」:

> 필살기 발동 중에는 **약점 속성을 무시하고 적의 강인성을 소모할 수 있으며**

→ "약점 속성 무시" 옵션을 스킬/효과 데이터로 표현할 수 있어야 한다.

### 8.2 격파 기본 피해 **[확인됨 — 게임 데이터 1차 자료]**

`ExcelOutput/AvatarBreakDamage.json` 에 **공격자 레벨별 격파 기본 피해**가 있다.

| 레벨 | 기본 피해 |
|---|---|
| 1 | 54 |
| 40 | 363.6658 |
| 60 | 1640.3068 |
| 70 | 2659.6406 |
| **80** | **3767.5535** |
| 90 | 6020.884 |

커뮤니티에서 널리 쓰이는 Lv80 값 `3767.5533` 과 일치한다 (반올림 차이).
**게임 원본 테이블을 직접 확보했으므로 이 값은 확정이다.**

### 8.3 격파 피해 공식 **[확인됨 — 게임 데이터 + 자료 2곳 교차검증]**

조사 갱신: 2026-08-20. 8월 19일에는 "찾지 못했다"고 적었으나, 정확한 용어
(Level Multiplier / Max Toughness Multiplier)를 알게 된 뒤 다시 찾아 확보했다.

```
격파 피해 기본값 = 속성 배수 x 격파 기본 피해(공격자 레벨) x 최대 인성치 배수(대상)
격파 피해       = 기본값 x (1 + 격파 특효) x DEF 배수 x RES 배수 x 취약 x 피해감소 x 1.0
```

**속성 배수**

| 속성 | 배수 | 격파 효과 |
|---|---|---|
| 물리 | 2 | 열상 |
| 화염 | 2 | 연소 |
| 얼음 | 1 | 빙결 |
| 번개 | 1 | 감전 |
| 바람 | 1.5 | 풍화 |
| 양자 | 0.5 | 얽힘 |
| 허수 | 0.5 | 속박 |

**최대 인성치 배수 = 0.5 + 최대 인성치 / 120** (우리 단위 기준)

단위에 함정이 있다. 자료는 `0.5 + 최대인성치 / 40` 으로 쓰고, 최적화 도구
(Fribbels)는 `0.5 + 최대인성치 / 120` 으로 쓴다. 모순이 아니라 **단위가 다르다**:

- 자료의 인성치 단위 = 일반 공격 10 (자료 원문: "10 Toughness Reduction = 1 Toughness Unit")
- 게임 데이터와 우리 단위 = 일반 공격 30, 적 인성치 30/60/90/…/720

즉 자료 단위 x 3 = 우리 단위이고, `(x/3)/40 = x/120` 으로 두 식이 같다.
Fribbels 의 기본 적 인성치가 360 인 것도 우리 데이터의 값 분포와 정확히 일치한다.

교차검증 근거:

1. 우리가 게임 데이터에서 임포트한 `AvatarBreakDamage` 표가 자료의 "Level Multiplier"
   표와 **Lv1 = 54, Lv95 = 7494.371 까지 일치**한다 → 같은 값이다
2. 우리 데이터의 기술(overworld) 공격 인성치 감소량 30 ↔ 자료의 10 → 단위비 3 확인
3. 격파 효과의 게임 데이터 구조가 자료의 서술과 하나씩 대응한다 (8.6)

### 8.4 격파 시 일어나는 일 **[확인됨 — 게임 데이터 1차 자료]**

2026-08-20 추가 조사에서 `Config/ConfigGlobalModifier/GlobalModifier_Common_Specific.json`
의 `StanceBreakState` 를 찾았다. 격파 상태 그 자체의 정의다.

```json
"StanceBreakState": {
  "LifeStepMoment": "ModifierPhase1End",
  "OnCreate":  [ AddModifier StanceBreakState_Effect,
                 ModifyActionDelay +0.25,
                 TriggerBreak(Caster) ],
  "OnDestroy": [ RemoveModifier StanceBreakState_Effect,
                 ResetStance, SetStanceCount,
                 AddModifier MonsterAllDamageReduce ]
}
"MonsterAllDamageReduce": { OnStack: StackProperty AllDamageReduce +0.1 }
```

여기서 한 번에 확정되는 것들:

| 항목 | 값 | 어디서 |
|---|---|---|
| 격파 시 행동 지연 | **25% 고정** (격파 특효 영향 없음) | `ModifyActionDelay 0.25` 가 `IsDynamic: false` |
| 격파 상태가 풀리는 시점 | **격파된 유닛의 턴 Phase1 끝** | `LifeStepMoment: ModifierPhase1End` |
| 인성치 회복 시점 | 격파가 풀릴 때 | `OnDestroy` 의 `ResetStance` |
| 10% 범용 피해 감소의 정체 | `AllDamageReduce +0.1` 짜리 모디파이어 | 격파가 **풀릴 때 다시 붙는다** → 격파 중에는 없다 = 배수 1.0 |
| 그 감소가 적 전용인지 | 이름이 `**Monster**AllDamageReduce` | 8.4 아래 참고 |

디버프 부여 확률은 자료 원문의 "150% base chance to apply a debuff" 를 쓴다.
기존 디버프 확률 공식(5.4)에 그대로 태운다.

**[유도됨 — 실측 필요] 격파 피해 자신은 0.9 를 받는가?**

한 커뮤니티 자료는 격파 피해 공식에 `0.9` 를 명시하고, 디버프 피해에는
"파괴 후 첫 턴이면 1, 그 이후 0.9" 를 붙인다. 그리고 "열상 첫 턴 피해가
격파 피해의 약 1.1배" 라고 적는다 — `1 / 0.9 = 1.111` 이므로 세 서술이 서로 맞물린다
(열상의 상한 기본값이 물리 격파 피해 기본값과 같기 때문).

게임 데이터로는 결론이 나지 않았다. `TriggerBreak` 는 `StanceBreakState` 의 `OnCreate`
안에 있어서 그 시점엔 이미 격파 상태지만, `MonsterAllDamageReduce` 를 **언제 떼는지**가
이 파일에 없다.

구현: `BreakConfig.break_damage_before_broken_state` (기본 True = 0.9) 로 분리했다.
실측 방법은 아래 8.8.

### 8.5 인성치 회복 **[확인됨 — 게임 데이터]**

`StanceBreakState.LifeStepMoment = ModifierPhase1End` 이고 `OnDestroy` 에서
`ResetStance` 를 한다. 즉 **격파된 유닛이 자기 턴을 맞으면 그 턴에 격파가 풀리고
인성치가 회복된다.** 기존에 미확인으로 두고 그렇게 구현했던 것이 맞았다.

### 8.6 속성별 격파 효과 **[확인됨 — 게임 데이터 + 자료]**

이름은 게임 데이터 `ExcelOutput/StatusConfig.json` 의 공식 한국어 명칭이다
(StatusID 30020020~30020026). 임의 번역이 아니다.

| 속성 | 이름 | 기본 피해 | 턴 | 그 밖 |
|---|---|---|---|---|
| 물리 | **열상** | 일반 `0.16 x 대상 최대HP`, 정예·보스 `0.07 x 대상 최대HP` (상한 `2 x 레벨배수 x 인성치배수`) | 2 | 지속 피해 |
| 화염 | **연소** | `1 x 레벨배수` | 2 | 지속 피해 |
| 얼음 | **빙결** | `1 x 레벨배수` | 1 | 행동 불가. 풀릴 때 다음 턴 50% 앞당김 |
| 번개 | **감전** | `2 x 레벨배수` | 2 | 지속 피해 |
| 바람 | **풍화** | `1 x 중첩 x 레벨배수` | 2 | 일반 1중첩 / 정예·보스 3중첩, 최대 5 |
| 양자 | **얽힘** | `0.6 x 중첩 x 레벨배수 x 인성치배수` | 1 | 행동 `20% x (1+격파특효)` 지연, 피격 시 +1중첩(최대 5) |
| 허수 | **속박** | 없음 | 1 | 행동 `30% x (1+격파특효)` 지연, 속도 -10% |

모든 기본 피해에 `(1 + 격파 특효)` 가 곱해진다. 열상의 상한은 격파 특효를 곱하기
**전**의 기본 피해에 걸린다.

게임 데이터가 이 서술을 구조적으로 뒷받침한다
(`Config/ConfigGlobalModifier/GlobalModifier_Common_Specific.json` 의 `MCommon_Element_*`):

| 자료의 서술 | 게임 데이터에서 확인되는 것 |
|---|---|
| 열상이 정예/보스일 때 배율이 다르다 | `ByCompareMonsterRank > 2` 로 분기가 갈린다 |
| 열상에 상한이 있다 | 계산한 값을 다른 값과 비교해 더 작은 쪽으로 덮어쓴다 |
| 열상/연소/감전/풍화가 지속 피해다 | `BehaviorFlagList` 에 `STAT_DOT` |
| 풍화는 최대 5중첩 | `MaxLayer: 5` (열상·연소·감전은 1) |
| 격파 피해가 격파 특효로 늘어난다 | `BreakDamageAddedRatio` 를 읽어 쓴다 |
| 빙결이 행동 불가다 | `DisableAction` |
| 속박이 속도를 낮춘다 | `STAT_SpeedDown` |
| 지속 피해가 부여 시점 스탯을 고정한다 | `UseSnapshotEntity: true` |

저항 태그(`STAT_DOT_Bleed`, `STAT_CTRL_Frozen` 등)도 이 정의에서 그대로 옮겼다.
적의 `DebuffResist` 가 이 태그 단위이므로(7.6) 여기서 지어내면 저항 계산이 어긋난다.

게임 데이터에서 직접 확인한 수식 두 개:

- 얽힘/속박의 추가 행동 지연 = `ModifyActionDelay(기본값 x (1 + 격파 특효))`
  — PostfixExpr `AQAAAAEBAgQR` 를 풀면 `D0 x (1 + D1)` 이고, 바로 앞에서 `D1` 에
  시전자의 `BreakDamageAddedRatio`(격파 특효)를 넣는다. **자료의 서술과 일치한다.**
- 속박의 속도 감소 = `StackProperty SpeedAddedRatio (0 - D)`
  — 여기에는 `(1 + 격파 특효)` 항이 **없다**. 같은 모디파이어 안에서 지연에는 곱하고
  속도에는 곱하지 않는다. 한 자료가 "둘 다 격파 특효 적용"이라고 적었지만
  게임 데이터와 다른 자료가 모두 아니라고 하므로 **곱하지 않는 쪽**을 택했다.
- 빙결 = 소유자 턴에 `ModifyCurrentSkillDelayCost = Set 0.5`.
  행동을 못 한 대신 다음 턴 진입 비용이 1.0 이 아니라 0.5 가 된다.
  "다음 턴이 50% 앞당겨진다"(영문 자료)와 "얼음 격파의 총 행동 지연은 0.75"(한국어 자료)는
  같은 것을 다르게 말한 것이다 — 적이 **다음에 행동하는 시점**은 25% + 50% 만큼 밀린다.

**[미확인] 두 가지**

1. 게임 데이터의 얽힘·속박 정의에는 `DisableAction` 플래그가 있는데
   자료와 게임 내 설명("행동 게이지가 감소한다")은 행동 지연만 말한다.
   우리는 **행동을 막지 않고 지연만** 적용했다.
2. **얽힘의 추가 지연이 20% 인지 30% 인지 자료가 엇갈린다.**
   영문 위키는 얽힘 20% / 속박 30%, 한국어 자료는 둘 다 30% 라고 한다.
   게임 데이터의 기본값은 이름 해시 뒤에 있어 읽지 못했다.
   비대칭(20/30)을 주장하는 쪽이 우연히 나오기 어려운 값이라 보고 **20%** 를 기본값으로 두되
   `BreakEffectSpec.action_delay` 로 분리했다.

### 8.7 정리 — 무엇을 믿을 수 있나

| 항목 | 근거 |
|---|---|
| 인성치 감소량 / 감소 속성 | 게임 데이터 |
| 적 최대 인성치 / 약점 속성 | 게임 데이터 |
| 격파 기본 피해 (레벨별) | 게임 데이터 (= 자료의 Level Multiplier) |
| 격파 시 행동 지연 25% | 게임 데이터 `StanceBreakState` |
| 인성치 회복 시점 | 게임 데이터 `LifeStepMoment` + `ResetStance` |
| 10% 범용 피해 감소의 정체와 격파 중 1.0 | 게임 데이터 `MonsterAllDamageReduce` |
| 얽힘·속박 지연에 격파 특효가 곱해짐 | 게임 데이터 PostfixExpr 해독 |
| 속박 속도 감소에는 안 곱해짐 | 게임 데이터 PostfixExpr + 영문 자료 |
| 빙결의 다음 턴 진입 비용 0.5 | 게임 데이터 `ModifyCurrentSkillDelayCost` |
| 속성 배수 / 최대 인성치 배수 | 자료 3곳 일치 (단위만 다름) |
| 격파 효과 7종의 이름 · 구조 · 태그 | 게임 데이터 |
| 격파 효과 7종의 수치 | 자료 2곳 (게임 데이터의 수치는 이름 해시 뒤) |
| 격파 피해가 0.9 를 받는지 | **유도 — 실측 필요** (8.8) |
| 얽힘 추가 지연 20% vs 30% | **자료 충돌 — 실측 필요** (8.8) |
| 얽힘·속박이 행동을 막는지 | **미확인 — 실측 필요** |

### 8.8 이 절을 닫으려면 필요한 실측

한 판이면 세 개가 한꺼번에 정리된다. 물리 또는 화염 약점 적을 격파하고:

1. **격파 피해 숫자**와 **다음 턴 열상/연소 피해 숫자**를 적는다.
   비가 `1.11` 이면 격파 피해에 0.9 가 곱해지는 것이고, `1.00` 이면 아니다.
2. 양자 약점 적을 격파 특효 0% 상태로 격파하고 행동 순서 표가 얼마나 밀리는지 본다.
   총 지연이 45% 면 얽힘 20%, 55% 면 30% 다.
3. 그때 적이 턴을 건너뛰는지(행동 불가) 그냥 늦게 행동하는지 본다.

---

## 9. 참고 자료

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
- Fandom Wiki — Status Effect <https://honkai-star-rail.fandom.com/wiki/Status_Effect>
- Fandom Wiki — DoT <https://honkai-star-rail.fandom.com/wiki/DoT>
- Fandom Wiki — Effect RES <https://honkai-star-rail.fandom.com/wiki/Effect_RES>
- ManaBuy — How to Calculate Effect Hit Rate <https://manabuy.com/blog/news/how-to-calculate-effect-hit-rate-honkai-star-rail-guide>
- GachaGuru — Ultimate Guide to DoT <https://www.gachaguru.com/honkai-star-rail/ultimate-guide-damage-over-time-dot>
- Fandom Wiki — Aggro <https://honkai-star-rail.fandom.com/wiki/Aggro>
- GachaGuru — Navigating the Aggro System <https://www.gachaguru.com/honkai-star-rail/navigating-the-aggro-system-your-ultimate-guide>
- GamesRadar — Honkai Star Rail taunt values <https://www.gamesradar.com/honkai-star-rail-taunt-values/>

게임 데이터 (직접 확인):

- DimbreathBot/TurnBasedGameData — `ExcelOutput/Monster*.json`, `Config/ConfigAI/Monster_*.json`, `TextMap/TextMapKR_0.json`
- FortOfFans/HSRMaps — `en/monster/*.json`
- 상세는 docs/data_sources.md
