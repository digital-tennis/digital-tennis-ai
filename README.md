# Digital Tennis AI

**같은 경기 규칙으로 겨루는 테니스 AI.** 게임 상태를 받아 이동 목표와 타격 의도를 반환하는, Unity와 독립된 C# 라이브러리입니다.

이 패키지는 **Stable-Baselines3 PPO로 실제 학습한 샷 배치 모델**도 포함합니다. 게임은 학습 모델의 코스·깊이 선택과 기존 자동 이동/접촉 실행 계층을 함께 사용합니다. 전체 경기를 처음부터 학습한 end-to-end 모델이나 실시간 외부 AI API가 아닙니다. [학습·재학습·Unity 연결 안내](Training/README.md)에서 역할과 한계를 확인하세요.

[빠른 시작](#빠른-시작) · [사용 예](#사용-예) · [게임 연결](#게임에-연결하기) · [기여하기](CONTRIBUTING.md)

## 왜 별도 라이브러리인가요?

화면·물리 엔진 없이 AI 정책을 검사하고, 같은 seed와 입력으로 판단을 재현하기 위해 분리했습니다. `netstandard2.1`을 대상으로 하며 UnityEngine, 장면, BLE와 네트워크에 의존하지 않습니다.

- **착지·접촉 위치 예측:** 게임이 전달한 중력·반발·공 크기와 샷 계수를 사용합니다.
- **세 가지 난이도:** 반응 지연, 위치 오차, 스윙 시도 확률, 세기 제한과 스킬 사용 기준을 주입합니다.
- **재현 가능한 판단:** 명시적 seed와 tick으로 진행하고, 들어오는 공마다 난수와 스윙 시도를 제한합니다.
- **공정한 입력:** 공·점수·체력을 직접 바꾸지 않고 일반 플레이어와 같은 타격 검사를 거칩니다.
- **명확한 중단:** 일시 정지·포인트 종료·경기 종료·온라인 상태에서는 판단을 진행하지 않습니다.

## 빠른 시작

검사에는 **.NET 10 SDK와 Git**이 필요합니다. Unity Editor와 실물 컨트롤러는 필요하지 않습니다.

```sh
git clone https://github.com/digital-tennis/digital-tennis-ai.git
cd digital-tennis-ai
bash tools/check.sh
```

직접 실행할 때는 `dotnet run --project tests/DigitalTennis.AI.Checks.csproj --configuration Release`를 사용합니다. 라이브러리 빌드는 `dotnet build DigitalTennis.AI.csproj -c Release`입니다.

## 사용 예

아래는 정책 생성 예입니다. 수치는 API 설명용이며, 실제 게임에서는 검증한 CSV 값을 전달합니다. **정책은 상대 선수당 한 번 생성**하고 매 tick 같은 인스턴스의 `Decide(snapshot)`를 호출합니다.

```csharp
using System.Collections.Generic;
using DigitalTennis.AI;

var balance = new Dictionary<string, float>
{
    ["move.home_depth"] = 8f, ["move.min_depth"] = 0.8f,
    ["move.contact_height"] = 1f, ["hit.net_gap"] = 0.2f,
    ["hit.reach"] = 1.5f, ["hit.min_height"] = 0.2f,
    ["hit.max_height"] = 2.5f, ["ai.target_width"] = 2.5f,
    ["ai.target_depth"] = 8f, ["shot.base_speed"] = 10f,
    ["shot.power_speed"] = 12f, ["shot.yaw"] = 25f,
    ["shot.pitch"] = 20f
};
var settings = new DifficultySettings(
    Difficulty.Medium, reaction: 0.2f, error: 0.8f,
    probability: 0.85f, power: 0.65f, skillStock: 2);
var opponent = new AiPolicy(settings, new AiTuning(balance), seed: 42);
```

게임은 tick·경기 단계·선수와 공의 위치/속도·현재 샷 ID·물리 계수를 [`AiState`](Runtime/AiContracts.cs)로 전달합니다. `AiDecision`의 `MoveTarget`은 이동 목표, `ShouldSwing`·`Stroke`·`Power01`·`AimX`·`AimZ`는 타격 의도입니다. 스킬 사용 제안은 [`AiSkillPolicy`](Runtime/AiSkillPolicy.cs)가 맡습니다.

## 난이도 조정

| 조정값 | 낮은 난이도 방향 | 높은 난이도 방향 |
| --- | --- | --- |
| 반응 시간 | 더 오래 기다림 | 더 빠르게 반응 |
| 위치 오차 | 목표 위치 오차 증가 | 예측 위치에 가깝게 이동 |
| 스윙 시도 확률 | 놓치는 시도 증가 | 시도 빈도 증가 |
| 최대 세기 | 낮은 세기 상한 | 높은 세기 상한 |
| 스킬 사용 재고 기준 | 더 모은 뒤 사용 | 적은 재고에서도 사용 |

라이브러리에 게임 밸런스 기본값을 숨겨 두지 않습니다. 게임의 [밸런스 CSV](https://github.com/digital-tennis/digital-tennis-game/blob/main/docs/gameplay-balance.md)가 값을 소유하고 `DifficultySettings`와 `AiTuning`으로 전달합니다.

## 게임에 연결하기

```text
호스트 경기 상태 → AiState → AiPolicy.Decide
                           → 이동 목표·타격 의도 → 일반 이동·입력 검사
```

1. 경기 좌표를 AI의 고정 선수 좌표계로 변환합니다.
2. 단조 증가하는 tick과 현재 공 ID로 상태를 전달합니다. 서브 준비와 정지 상태도 정확히 표시합니다.
3. 이동에는 게임의 속도 제한을 적용하고, 스윙은 일반 입력 경계로 보냅니다.
4. 코트 끝 교대 후에도 선수 ID를 유지하고 좌표 변환을 갱신합니다.

UPM 이름은 `com.digital-tennis.ai`입니다. Unity에서는 Git 패키지를 검토한 커밋으로 고정해 사용합니다. 실제 통합 예는 게임의 [`TennisAiOpponent`](https://github.com/digital-tennis/digital-tennis-game/tree/main/Assets/Scripts)와 [1인 플레이 문서](https://github.com/digital-tennis/digital-tennis-game/blob/main/docs/single-player-ai.md)에 있습니다. AI는 온라인 상대를 대신 실행하지 않습니다.

## 소스 안내

| 파일 | 역할 |
| --- | --- |
| [AiContracts.cs](Runtime/AiContracts.cs) | 상태·결정·난이도 공개 타입 |
| [AiPolicy.cs](Runtime/AiPolicy.cs) | 반응·이동·타격 정책 |
| [BallPrediction.cs](Runtime/BallPrediction.cs) | 공 궤적·접촉 목표 예측 |
| [AiTuning.cs](Runtime/AiTuning.cs) | 주입할 밸런스 스키마와 검증 |
| [tests/](tests/) | 재현성·난이도·오류 상태 검사 |

독립 검사와 실제 Unity 경기 검증은 구분합니다. 게임 연결 결과는 [게임 저장소](https://github.com/digital-tennis/digital-tennis-game)에서 확인할 수 있습니다.

## 도움말·기여

[Digital Tennis](https://github.com/digital-tennis)가 관리합니다. [Issues](https://github.com/digital-tennis/digital-tennis-ai/issues)에 seed·난이도·입력 상태·기대 결정을 남겨 주세요. [기여 안내](CONTRIBUTING.md)와 [초보자용 AI 과제](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md)를 참고하세요.

## 라이선스

직접 작성한 코드·문서는 [Apache-2.0](LICENSE)입니다. [NOTICE](NOTICE)와 [외부 코드 고지](THIRD_PARTY_NOTICES.md)를 함께 확인하세요.

실제 Unity 전체 경기 Gym/PPO와 별도 C# actor는 [Training/README.md](Training/README.md#실제-unity-전체-경기-학습-2026-10-21)를 참조한다. 기존 한 샷 placement 결과와 구분하며 전체 경기 학습 증거는 게임 저장소 `docs/evidence/ai-full-match/training.json`에 기록한다.
