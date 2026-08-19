# 적 데이터 소스 조사 결과

조사일: 2026-08-19. 실제로 저장소를 받아서 파일 구조를 확인한 결과다.

## 결론 요약

| 필요한 것 | 어디에 있나 | 상태 |
|---|---|---|
| 적 기본 스탯 | Dimbreath `ExcelOutput/MonsterTemplateConfig.json` | 있음 |
| 적 개체별 배율/약점/저항 | Dimbreath `ExcelOutput/MonsterConfig.json` | 있음 |
| 적 스킬(배율, 속성, 에너지, 페이즈) | Dimbreath `ExcelOutput/MonsterSkillConfig.json` | 있음 |
| **적 AI (행동 패턴)** | Dimbreath `Config/ConfigAI/Monster_*.json` (362개) | **있음** |
| 공식 한국어 명칭 | Dimbreath `TextMap/TextMapKR_0.json` (38MB) | **있음** |
| 사람이 읽기 쉬운 적 요약 | HSRMaps `en/monster/*.json` (2258개) | 있음 (영어만) |

즉 **적의 행동 패턴 데이터는 존재하며**, 한국어 공식 명칭도 확보 가능하다.

---

## 1. Dimbreath / TurnBasedGameData

주의: 사용자가 준 URL `github.com/DimbreathBot/TurnBasedGameData` 가 맞다.
`github.com/Dimbreath/TurnBasedGameData` 는 존재하지 않는다.

용량이 크므로 `--filter=blob:none --sparse` 로 필요한 파일만 받는 것이 좋다.

### MonsterTemplateConfig.json (613개)

템플릿(외형/기본 스탯) 단위.

```
MonsterTemplateID, MonsterName(Hash), Rank
AttackBase, DefenceBase, HPBase, SpeedBase, CriticalDamageBase
StanceBase(인성치), StanceCount, StanceType
StatusResistanceBase   <- 적의 기본 효과 저항
InitialDelayRatio      <- 전투 시작 시 행동 게이지 배수
AIPath                 <- 이 적이 쓰는 AI 파일 경로
AISkillSequence        <- 고정 스킬 순환 목록
```

- `Rank` 분포: MinionLv2 259 / Elite 151 / LittleBoss 144 / BigBoss 35 / Minion 24
- `StatusResistanceBase` 분포: **0.2 가 267개, 0.3 이 193개, 0.1 이 77개**
  → 적은 기본적으로 효과 저항을 가지고 있다. 우리 구현의 기본값 0 은 틀렸다.
- `InitialDelayRatio` 분포: 1 이 545개, **0.5 가 51개**, 0.25/0.75/0.2/1.5 소수
  → 일부 적은 전투 시작 시 행동이 빠르거나 느리다.

### MonsterConfig.json (2591개)

실제 배치되는 개체 단위. 템플릿에 배율과 약점을 덧씌운다.

```
MonsterID, MonsterTemplateID, MonsterName(Hash)
EliteGroup, HardLevelGroup            <- 레벨/난이도 스케일링 그룹
AttackModifyRatio, DefenceModifyRatio, HPModifyRatio,
SpeedModifyRatio, StanceModifyRatio
StanceWeakList                        <- 약점 속성
DamageTypeResistance                  <- 속성별 저항
DebuffResist                          <- 상태 이상 태그별 저항
SkillList, SummonIDList
OverrideAIPath, OverrideAISkillSequence, OverrideSkillParams
```

`DebuffResist` 는 **개별 효과 id 가 아니라 태그(카테고리) 단위**다.

```
STAT_CTRL        530개  (행동 불능 전반)
STAT_CTRL_Frozen 351개  (빙결)
STAT_Confine     118개
STAT_Entangle    113개
STAT_DOT_Burn    103개
STAT_DOT_Poison    8개
STAT_DOT_Electric  5개
```

→ 우리 구현의 `debuff_res` 도 효과 id 가 아니라 **태그 기준**이어야 한다.

### MonsterSkillConfig.json (3462개)

```
SkillID, SkillName(Hash), SkillTriggerKey("Skill01"...), SkillDesc(Hash)
DamageType(속성), AttackType, ParamList(배율)
SPHitBase     <- 이 스킬에 맞은 캐릭터가 얻는 에너지
DelayRatio    <- 이 스킬 사용 후의 행동 게이지 배수
PhaseList     <- 이 스킬이 사용 가능한 페이즈
AI_CD, AI_ICD, IsThreat, ModifierList, ExtraEffectIDList
```

- `SPHitBase` 분포: **10 이 903개**, 15 가 350개, 5 가 193개, 20 이 138개, 25/2/30/40/8/12 소수
  → 자료의 "적에 따라 다르다" 가 데이터로 확인된다. 가장 흔한 값은 10.
- `DelayRatio` 분포: 1 이 3389개, 1.25 / 1.5 / 1.75 / 0.5 / 2 등 소수
  → 큰 기술을 쓰면 다음 턴이 늦게 온다.
- `PhaseList`: (1,) 1709개, () 623개, (1,2) 480개, (2,) 265개, (1,2,3) 214개 ...
  → 보스 페이즈별로 쓸 수 있는 스킬이 다르다.
- `AI_CD`, `AI_ICD` 는 이 파일에서는 전부 1 이고, 실제 쿨다운은 AI 파일에 들어 있다.

### TextMap/TextMapKR_0.json

공식 한국어 텍스트. 위 파일들의 `Hash` 값을 키로 조회한다.
→ **요구사항 6(공식 한국어 명칭)을 임의 번역 없이 만족할 수 있다.**

---

## 2. HSRMaps (FortOfFans)

`en/monster.json` (2520개 요약) + `en/monster/<id>.json` (2258개 상세).

Dimbreath 를 가공해서 사람이 읽기 쉽게 만든 형태다.

```json
{ "name": "Ice Edge", "stats": {"baseAttack":18,"baseDefense":210,"baseHealth":69.75,
  "hardLevelGroup":1,"eliteGroup":1,"baseStance":60,"speed":100,"type":"MinionLv2"},
  "skills":[{"name":"Icy Wind","tag":"AoE ATK","element":"Ice","params":[2],
             "spGain":10,"delay":1}],
  "resistance":[...], "weakness":["Fire","Thunder"], "stanceType":"Ice" }
```

- 장점: 스킬 이름/설명이 이미 풀려 있고 구조가 단순하다
- 단점: **영어만 있고, AI(행동 패턴) 정보가 없다**

→ 교차검증용으로 쓰고, 실제 임포트는 Dimbreath 를 원본으로 한다.

---

## 3. 다음 단계 제안

1. Dimbreath 에서 `MonsterTemplateConfig` + `MonsterConfig` + `MonsterSkillConfig` +
   `TextMapKR` 만 sparse-checkout 하는 임포터 작성
2. HSRMaps 와 대조해 스탯/배율이 일치하는지 자동 검증
3. `LocalizedName(ko=..., en=..., ko_verified=True)` 로 저장
4. `Config/ConfigAI` 를 우리 `EnemyAI` 정의로 변환 (자주 쓰이는 패턴부터)
