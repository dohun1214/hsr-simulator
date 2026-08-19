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

## 3. 임포터 (구현 완료)

```bash
python tools/import_monsters.py --fetch          # 필요한 파일만 받아서 임포트
python tools/import_monsters.py --source <path>  # 이미 받아 둔 저장소에서
python tools/validate_monsters.py --hsrmaps <path>   # HSRMaps 와 교차검증
```

결과: `data/monsters.json.gz` (264 KB) — 적 **2591종**, 고유 스킬 **3462개**,
**공식 한국어 명칭 100% 확보**.

레벨을 고정하지 않고 **기본값 + 배율 표**를 저장하므로 로더가 원하는 레벨로 계산한다.

```
스탯 = 기본값 x 개체 배율 x HardLevelGroup 배율 x EliteGroup 배율
```

### 3.1 교차검증 결과 (요구사항 8)

HSRMaps 와 2485종을 대조했다. **불일치 2건**.

- 두 건 모두 같은 적(5024011 과 그 변종)의 바람 저항 하나가 0.2 vs 0.4
- 나머지 항목(HP/ATK/DEF/속도/인성치/등급/약점/속성 저항/스킬 에너지/지연/파라미터)은 전부 일치
- HSRMaps 는 더 오래된 게임 버전에서 생성되었을 가능성이 크다

검증 과정에서 발견한 **표현 방식 차이** (둘 다 맞음):

- HSRMaps 는 개체 배율(`*ModifyRatio`)을 기본 스탯에 **미리 곱해서** 저장한다.
  우리는 분리해 저장하므로 비교할 때 곱해서 맞춰야 한다.
- `SpeedBase` 가 0 인 개체가 65종 있다 (보스의 부위, 일부 소환물).
  HSRMaps 는 100 으로 채우지만 원본은 0 이다. 우리는 원본을 유지하고,
  스케줄러가 속도 0 인 개체를 행동 순서에서 제외한다.

---

## 4. 가져오지 못한 것: 적 스킬의 피해 배율

**이것만은 못 가져왔다.** 조사 과정을 남겨 둔다.

1. `MonsterSkillConfig.ParamList` 에 숫자가 들어 있지만 **배율이라는 보장이 없다.**
   스킬 설명에 숫자 자리표시자가 있는 스킬은 3462개 중 10개뿐이라
   설명과 대조해서 확인할 수도 없다.
2. 실제 배율은 능력 설정 `Config/ConfigAbility/Monster/*_Ability.json` 의
   `AttackData.DamagePercentage` 에 있다. 그런데 이 값은 **동적 표현식**이다.

```json
"DamagePercentage": { "IsDynamic": true,
  "PostfixExpr": { "OpCodes": "AQAR", "DynamicHashes": [-1126825319] } }
```

3. `OpCodes` 는 스택 기계다 (base64 디코딩 결과):
   `[1, i]` = 동적값 i 밀어넣기, `[0, i]` = 고정값 i, `[4]` = 곱하기, `[17]` = 끝.
   `AQAR` = "동적값 0 을 그대로 사용" 이며 이것이 전체의 64% 다.
4. 문제는 `DynamicHashes` 가 **이름 해시**라는 것이다. 이 해시가 무엇을 가리키는지 모른다.
   - 파라미터 개수와 참조 해시를 상관분석했으나 일관된 대응이 나오지 않았다
     (파라미터 1개인 스킬이 5가지 서로 다른 해시를 참조)
   - fnv1/fnv1a/djb2/crc32 로 `SkillParam_1` 류 이름을 해싱해 봤으나 일치 없음
   - 능력 파일의 문자열 `DynamicKey` 는 전부 게임플레이 카운터이지 피해 파라미터가 아님

**결론**: 조용히 `params[0]` 을 배율로 쓰지 않는다.
임포트한 스킬은 `multiplier=0.0`, `multiplier_verified=False` 로 들어오고,
`params` 는 원본 그대로 보존한다.
`assume_first_param=True` 를 명시적으로 주면 `params[0]` 을 쓰지만
그 경우에도 `multiplier_verified` 는 False 로 남는다.

**해결 방법 후보**

- HoYo 의 이름 해시 함수를 찾아 `DynamicHashes` 를 역산
- 실제 전투에서 특정 적의 피해를 측정해 역산 (적 ATK 는 이미 정확히 안다)
- 커뮤니티 위키에 적 스킬 배율이 정리되어 있는지 확인

---

## 5. 다음 단계 제안

1. `Config/ConfigAI` 를 우리 `EnemyAI` 정의로 변환 (지금은 전부 고정 순환으로 근사)
2. 캐릭터/광추/유물 임포터 (`AvatarConfig`, `EquipmentConfig`, `RelicConfig`)
3. 위 배율 문제 해결
