# Digital Tennis 독립 AI 플레이어

`AiSkillPolicy.ShouldActivate`는 캐릭터 스킬 사용 시점을 순수 함수로 판단합니다. 유효 리턴 직후 주입한 `SkillStock` 이상일 때 사용합니다. 기본 CSV는 Easy=3개, Medium=2개, Hard=1개입니다. 온라인·일시정지·활성 효과 중·무효 입력에는 사용하지 않습니다. 실제 게이지 차감·경기 규칙·연출은 게임 어댑터가 검증하고 실행합니다.

Unity에 의존하지 않는 C# AI입니다. 게임 상태를 읽고 **이동 목표와 라켓 입력**을 반환합니다. 난이도 상·중·하, 착지/타격 위치 예측, 재현 가능한 seed와 단독 검증을 제공합니다. 공·점수·캐릭터를 직접 변경하지 않습니다.

전체 Digital Tennis 프로젝트는 **NU40-DK에 외장 IMU를 별도 부착**하고 Unity PC 게임, 1인 AI와 온라인 2인 대전을 12일·3명으로 개발합니다. 이 저장소는 AI만 담당합니다.

## 실행과 테스트

.NET 10 SDK를 설치한 뒤 저장소 루트에서 실행합니다. 라이브러리 자체는 Unity 6에서 사용할 수 있는 **netstandard2.1**이고, 검증 도구만 .NET 10을 사용합니다. 처음 실행할 때 공식 NuGet의 NETStandard 참조 팩을 받을 수 있습니다. 외부 테스트 라이브러리는 사용하지 않습니다.

```bash
bash tools/check.sh
# 또는
dotnet run --project tests/DigitalTennis.AI.Checks.csproj --configuration Release
```

25개 검증 묶음이 예측 수치, 난이도 반응 경계, 같은 입력·seed의 동일 출력, 공별 1회 표본과 타격, 온라인·일시정지·종료·잘못된 입력을 확인합니다. GitHub Actions도 같은 명령을 실행합니다. 전체 성공은 `ALL 25 CHECKS PASSED`입니다. `bin/`, `obj/`, `.work/`는 커밋하지 않습니다.

## 입력과 출력: 초보 개발자용 문제 설명

가정: AI는 Far(주황색, z>0)를 맡고 사람은 Near(청록색, z<0)를 맡습니다. 경기의 매 업데이트마다 `AiState`를 하나 만들고 `AiPolicy.Decide`를 한 번 호출합니다. 벡터는 Unity Vector3 대신 독립적인 `Vec3`입니다.

| 입력 | 의미와 제한 |
| --- | --- |
| Tick / DeltaTime | 계속 증가하는 정책 업데이트 번호, 0초 초과~1초의 경과 시간. 공의 발사마다 초기화되는 물리 Tick을 넘기지 않습니다. |
| PlayerId / LastHitter | Near=0, Far=1. AI와 마지막 타격자 |
| PlayerPosition / OpponentPosition | 두 선수의 코트 기준 위치 |
| BallPosition / BallVelocity | 공 중심 위치와 초당 속도 |
| Phase | 서브 대기/비행/랠리/득점/종료/일시정지 |
| BounceCount / IncomingBallId | 현재 발사의 바운스 횟수, 유일한 발사 ID. 게임은 `(rallyId << 32) | shotId` 사용 |
| HasBall / IsStopped / IsOnline | 공의 존재·정지와 온라인 실행 여부 |
| Gravity / Radius / BounceRestitution / SpeedRetention | 게임에서 반드시 전달하는 실제 물리 계수. 생략하면 잘못된 상태로 거부 |

출력 `AiDecision`에는 `MoveTarget`, `ShouldSwing`, `Stroke`, `Power01`, `AimX`, `AimZ`, `Status`가 있습니다. 목표는 자기 코트 안으로 제한됩니다. 게임은 목표를 향해 CSV와 캐릭터 상태로 계산한 최대 속도로 이동시키고, `ShouldSwing=true`일 때 **일반 RacketInput 타격 경계**에 전달합니다. 게임은 높이·거리·권위를 다시 검사합니다. `ShouldSwing=false`이면 공을 발사하지 않습니다.

```csharp
// settings: 게임이 CSV에서 검증해 만든 DifficultySettings
// tuning: 같은 CSV의 이동·타격·샷 값으로 만든 불변 AiTuning
var ai = new DigitalTennis.AI.AiPolicy(settings, tuning, seed: 42);
// 같은 ai 인스턴스를 계속 보관합니다. 매 프레임 새로 만들지 않습니다.
AiDecision decision = ai.Decide(snapshot);
// decision.MoveTarget으로 제한 속도 이동
// decision.ShouldSwing이면 게임의 일반 타격 입력에 전달
```

`Runtime`은 UnityEngine·GameObject·Transform과 게임 어셈블리를 참조하지 않습니다. Unity asmdef도 `noEngineReferences=true`입니다. 게임은 Git SHA로 고정한 UPM 의존성으로 이 저장소를 사용하며 정책을 복사하지 않습니다. 단독 검증 코드의 asmdef는 기본 Unity 컴파일에서 제외합니다.

## 난이도 정책 (아래 표는 기본 CSV 값)

| 난이도 | 반응 지연 | x/z 각각의 목표 오차 | 공별 타격 시도 확률 | 파워 상한 |
| --- | --- | --- | --- | --- |
| 하 Easy | 350 ms | ±1.5 m | 0.65 | 0.50 |
| 중 Medium | 200 ms | ±0.8 m | 0.85 | 0.65 |
| 상 Hard | 100 ms | ±0.25 m | 0.95 | 0.80 |

상대의 새 공이 들어올 때 x/z 오차와 시도 여부를 **각각 한 번** 표본으로 뽑습니다. xorshift32를 사용해 .NET/Unity의 System.Random 구현 차이와 전역 난수를 피합니다. 같은 seed·상태 스트림이면 같은 결과를 냅니다. seed=0도 정해진 비영점 상태로 재현합니다. 반응은 Tick/DeltaTime 누적으로 계산하며 잠들거나 스레드를 멈추지 않습니다.

반응 시간이 지난 뒤 `Rally`, 자신의 코트, CSV의 타격 높이와 캐릭터의 현재 타격 범위 안에 들어온 첫 순간에 최대 한 번 타격합니다. 실수 표본이면 그 공에는 타격하지 않습니다. 멈춘 공·서브 대기·일시정지·득점·승리·온라인 상태에서는 타격과 반응 타이머를 진행하지 않습니다. 같은 Tick을 다시 호출해도 반응 시간을 추가하지 않습니다. 난이도 변경은 새 정책과 새 경기로 시작해 이전 공의 표본을 섞지 않습니다.

## 예측과 샷 선택

`BallPrediction.Landing`은 `y(t)=y0+vy*t-0.5*g*t²`가 바운스 면에 닿는 양의 근을 계산합니다. 최대 3초이며 유효하지 않은 값은 invalid입니다. y=1, vy=0, vx=2, vz=4, 바운스 면 0이면 t≈0.451524초, x≈0.903047 m, z≈1.806095 m입니다.

첫 바운스 전에는 착지점과 반발 계수로 약 1 m 높이의 상승 구간을 예측합니다. 현재 물리의 네트 접촉·스핀은 별도로 예측하지 않습니다. 목표 오차를 더해 x=±4.115 m, 자기 진영 z=0.8~11.885 m로 제한합니다. 상대 쪽으로 가는 공은 추격하지 않고 중앙으로 복귀합니다. 이미 바운스한 공을 새로 관찰하면 현재 위치를 목표로 사용합니다.

샷은 상대가 서 있는 x의 반대쪽 ±2.5 m, 깊이 8 m를 겨냥합니다. 게임의 20° 상향각에서 그 지점에 착지할 속도를 역산하고 난이도별 파워 상한을 적용합니다. 선수 로컬 조준값을 반환하며 게임이 코트 방향 변환을 한 번 수행합니다. 라켓의 로컬 오른쪽 공은 포핸드, 왼쪽 공은 백핸드입니다.

**초기 명세에서 조정한 점:** 고정 파워 0.50/0.65/0.80을 그대로 쓰면 속도 16/17.8/19.6 m/s입니다. 높이 1 m·서비스 라인 z≈6 m에서 20°로 19.6 m/s를 보내면 상대 베이스라인을 크게 넘습니다. 따라서 기존 값은 상한으로 유지하고 실제 접촉 위치로 파워를 계산합니다. aimX도 초기 고정 ±0.5 대신 빈 코트의 실제 위치로 계산합니다. 단독 수치 검증은 두 진영에서 목표 착지 오차 1 cm 이내를 확인합니다. 이 조정은 세 난이도의 반응·오차·시도 확률을 바꾸지 않습니다.

## 검증 기록 (2026-10-15)

.NET 10.0.105에서 **25/25 묶음 통과**. 각 난이도에서 seed 42로 새 공 10,000개를 표본화한 시도 비율은 하 **0.6577**, 중 **0.8535**, 상 **0.9498**이었습니다. 이는 타격 시도 난수의 관측값이며 경기 승률이 아닙니다. 각 묶음은 같은 공에 대한 중복 타격·중복 표본도 검사합니다.

독립 수치 테스트와 실제 Unity 게임 플레이 증거는 구분합니다. 실제 IMU/Windows 컨트롤러로 세 난이도를 완주하는 AT-11은 하드웨어 검증이 별도로 필요합니다. 게임 연동 결과는 [게임 저장소](https://github.com/digital-tennis/digital-tennis-game)의 1인 플레이 문서에서 확인합니다.

## 구조와 협업

| 경로 | 역할 |
| --- | --- |
| Runtime/AiContracts.cs | 상태·결정·벡터와 난이도 설정 |
| Runtime/BallPrediction.cs | 착지·타격 위치 예측과 코트 제한 |
| Runtime/AiPolicy.cs | 반응·난수·의도적 실수·샷 결정 |
| tests/Program.cs | Unity 없이 실행하는 재현 가능한 검증 |
| tools/check.sh | 로컬 실행 |
| .github/workflows/checks.yml | 독립 CI |

[전체 AI 과제](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md), [12일 WBS](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/planning/wbs.md)를 함께 참고합니다. PR은 스쿼시 병합하고 병합한 원격·로컬 브랜치를 삭제합니다. 라이선스는 팀이 코드와 자산 조건을 검토한 뒤 선택합니다.

## CSV 기반 설정 주입

AI 런타임은 기본 난이도 수치나 파일 경로를 갖지 않습니다. 게임이 검증한 `gameplay.csv`의 설정으로 `DifficultySettings`와 `AiTuning`을 만들고 `new AiPolicy(settings, tuning, seed)`로 전달합니다. `AiState`에는 실제 공 물리 계수와 캐릭터의 현재 타격 범위·샷 배율을 전달해야 합니다. 미전달 물리는 NaN으로 거부됩니다.

조절 항목은 반응 시간·위치 오차·스윙 확률·최대 세기·스킬 사용권 임계값, 이동 목표, 타격 높이·범위, 조준 위치와 게임의 공통 샷 속도·각도입니다. 서브 대기에서 설정 변경 시 게임이 정책을 새 세션으로 교체합니다. 기본 생성자와 `DifficultySettings.For`는 제거되었습니다. `tests/balance.csv`는 독립 검사 전용 데이터이며 실제 제품의 배포 설정은 게임 저장소에서 관리합니다.
