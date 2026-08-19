# 아키텍처

## 1. 이 구조를 고른 이유

최종 목표는 "전투 1회 재생"이 아니라

```
현재 상태 -> 가능한 행동 -> 각 행동의 미래 상태 -> 수많은 미래 탐색 -> 평가 -> 최적 행동 추천
```

이다. 이 목표가 구조를 거의 전부 결정한다.

탐색을 하려면 **상태를 초당 수천~수만 번 복제**해야 한다.
따라서 다음 두 가지가 반드시 성립해야 한다.

1. 상태 복제가 싸고 안전할 것
2. 같은 상태 + 같은 행동이면 항상 같은 결과가 나올 것 (결정론)

그래서 이 프로젝트는 **상태 / 정의 / 동작을 3분할**한다.

| 구분 | 위치 | 성격 | 복제 대상 |
|---|---|---|---|
| 상태 (State) | `battle/state.py`, `entities/unit.py` | 순수 데이터. 전투 중 변함 | O |
| 정의 (Definition) | `entities/definitions.py`, `content/` | 불변 데이터. 캐릭터/스킬 설계도 | X (공유) |
| 동작 (Behavior) | `registries.py` 에 등록된 구현체 | 함수/객체. 상태를 갖지 않음 | X (공유) |

`BattleState` 안에는 **함수도, 클로저도, 이벤트 구독도 들어가지 않는다.**
유닛은 자기 특성을 `ability_ids: ("xxx",)` 같은 **문자열 id 로만** 들고 있고,
실제 구현은 레지스트리에 있다.

이 덕분에

- `BattleState.clone()` 이 dict/list 얕은 복사 수준으로 끝난다 (`copy.deepcopy` 불필요)
- 엔진 인스턴스 하나로 수많은 상태 복제본을 굴릴 수 있다
- 상태를 그대로 직렬화/스냅샷/리플레이할 수 있다

## 2. 모듈 구조

```
src/hsr_sim/
  core/
    enums.py       속성, 운명의 길, 데미지 태그, 치명타 모드 등
    rng.py         결정론적 난수 (상태에 저장되는 splitmix64)
    events.py      이벤트 정의 + 이벤트 버스 (트리거 시스템의 기반)
    registry.py    문자열 id -> 구현체 레지스트리
  stats/
    stat.py        Stat 열거형, 수정자, 최종 스탯 계산
  entities/
    definitions.py UnitDefinition / SkillDefinition / LocalizedName / TargetRule (불변 데이터)
    unit.py        Unit (전투 중 변하는 상태)
  battle/
    state.py       BattleState, BattleConfig (스킬 포인트 포함)
    resources.py   스킬 포인트 / 에너지 증감과 상한 처리
    scheduler.py   Action Gauge / Action Value / 사이클
    damage.py      데미지 계산 파이프라인
    targeting.py   대상 지정 규칙
    actions.py     Action (의도를 나타내는 데이터)
    handlers.py    Action 실행 처리기
    behaviors.py   적 AI / 자동 행동 선택기
    abilities.py   특성 인터페이스
    engine.py      BattleEngine (규칙 실행기)
    log.py         전투 로그 (탐색 시 끌 수 있음)
  content/
    dummies.py     V0.1 검증용 테스트 유닛
  registries.py    전역 레지스트리
  setup.py         정의 -> BattleState 생성
```

## 3. 핵심 결정 5가지

### 3.1 AV 가 아니라 Action Gauge 를 저장한다

```
AV = AG / SPD,   1 AV 경과 -> AG -= SPD,   행동 후 AG = 10000
```

AV 를 저장하면 턴 도중 SPD 가 바뀔 때 남은 시간 환산 규칙을 임의로 정해야 한다.
AG 를 저장하면 게임 내부 동작과 동일하게 자동 재계산된다.
(근거: `docs/mechanics.md` 1장)

이 결정 덕분에 속도 버프/디버프, 행동 앞당기기/늦추기가 전부 같은 식 하나로 처리된다.

### 3.2 데미지는 "이름 붙은 곱연산 단계의 목록"이다

```python
_STEPS = [("dmg_boost", ...), ("weaken", ...), ("def", ...), ("res", ...),
          ("vulnerability", ...), ("mitigation", ...), ("broken", ...), ("extra", ...)]
```

- 새로운 곱연산 항이 게임에 추가되면 `register_damage_step(name, fn, before=...)` 한 줄
- 각 단계의 결과가 `DamageResult.breakdown` 에 남아 **실제 게임 수치와 항목별로 대조**할 수 있다

V0.1 에서 아직 안 쓰는 항(나약, 피해 감소)도 슬롯을 미리 만들어 두었다.
나중에 공식 전체를 뜯어고치는 것보다 항등원 1.0 을 곱하는 편이 싸다.

### 3.3 트리거는 이벤트 버스로 처리한다

`BeforeDamage`, `TurnStart`, `AfterDamage`, `UnitDefeated` ... 를 엔진이 발행하고,
특성/패시브/광추/유물/보스 기믹은 **구독자로만** 존재한다.

캐릭터별 로직이 엔진에 들어가지 않는 이유가 이것이다.
`tests/test_extensibility.py` 가 "엔진을 수정하지 않고 새 메커니즘을 붙일 수 있는가"를
실제 코드로 고정하고 있다.

### 3.4 Action 은 데이터, 실행은 처리기

```python
BasicAttackAction(actor_uid="A1", target_uid="E1")   # 데이터 (frozen, 해시 가능)
ACTION_HANDLERS.get("BasicAttackAction")             # 실행
```

탐색 알고리즘은 행동을 생성/비교/저장해야 하므로, 행동이 실행 로직을 들고 있으면 곤란하다.

### 3.5 난수는 전역이 아니라 상태 안에 있다

`RngState(seed, counter)` 가 `BattleState` 의 필드다.
상태를 복제하면 난수 위치까지 복제되므로, 분기된 미래가 서로 간섭하지 않고 재현 가능하다.
`CritMode.AVERAGE` 로 분산을 아예 제거한 결정론적 평가도 가능하다.

### 3.6 필살기는 "행동"이지만 "턴"이 아니다

게임 규칙상 필살기는 턴을 소모하지 않고, 자기 턴이 아닐 때도 발동하며, 연쇄된다
(docs/mechanics.md 4.3). 그래서 일반 행동과 **다른 축**으로 모델링했다.

```python
engine.legal_actions(state)        # 이번 턴에 할 수 있는 것 (일반 공격 / 전투 스킬)
engine.available_ultimates(state)  # 지금 발동 가능한 필살기 (턴과 무관)
engine.use_ultimate(state, action) # 행동 게이지도 turn_count 도 건드리지 않는다
engine.resolve_ultimates(state, policy)  # 연쇄 발동
```

`run()` 은 전투 시작 직후 / 턴 시작 시 / 턴 종료 직후에 `resolve_ultimates()` 를 호출한다.

**탐색에 대한 함의**: 한 턴의 행동 공간은 "필살기 0회 이상 + 주 행동 1회"의 조합이다.
V0.2 는 정책 함수(`ultimate_policy`)로 이 축을 분리해 두었고,
탐색 단계에서 그 자리에 평가 기반 선택이 들어간다.

### 3.7 일반 공격 / 전투 스킬 / 필살기는 같은 실행 경로를 쓴다

셋의 차이는 전부 `SkillDefinition` 의 데이터(`sp_cost`, `sp_gain`, `energy_gain`,
`energy_cost`, `target_rule`)로 표현된다. 따라서 `handlers.execute_skill()` 하나가
세 행동을 모두 처리하고, `ACTION_HANDLERS` 에 세 이름으로 등록되어 있을 뿐이다.

캐릭터별 분기가 코드로 새어 나오지 않게 하는 두 번째 장치다.

## 4. 탐색을 위한 API (이미 준비된 부분)

```python
engine.legal_actions(state)        # 현재 행동자의 주 행동 후보
engine.available_ultimates(state)  # 지금 발동 가능한 필살기
engine.simulate(state, action)     # 원본을 건드리지 않고 미래 상태 반환
state.clone()                      # 값 복제
```

V0.1 에는 탐색 알고리즘도 평가 함수도 없다. 그러나 그것들이 필요로 하는
**상태 복제 / 행동 생성 / 결정론**은 이미 테스트로 고정되어 있다.
(`tests/test_determinism.py::test_branching_search_from_one_state`)

## 5. 성능에 대한 현재 입장

V0.1 은 정확성과 구조 우선이며 최적화는 하지 않았다. 다만 나중에 발목을 잡을 선택은 피했다.

- `copy.deepcopy` 대신 명시적 `clone()`
- 로그를 끌 수 있게 함 (`BattleConfig.log_enabled=False`)
- 상태에 순수 데이터만 두어 향후 `__slots__`, 배열 기반 표현, 다른 언어 이식이 모두 열려 있음

## 6. 새 메커니즘 추가 절차

```
새 구현 작성 (Ability / Behavior / ActionHandler / DamageStep)
  -> registries.py 의 레지스트리에 등록
  -> 데이터(UnitDefinition)에 id 추가
  -> 테스트 추가
```

엔진 코어 파일을 수정할 필요가 없다.
