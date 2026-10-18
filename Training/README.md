# PPO 샷 배치 모델: 학습과 게임 연결

2026-10-19 기준. 자체 코드·모델 Apache-2.0. PyTorch·Stable-Baselines3·Gymnasium은 각 원래 라이선스를 따른다. 기존 NU40-DK+별도 외장 IMU, 최초12일·3명 계획과 무관한 후속 AI 확장이다.

## 무엇이 학습되고 무엇이 기존 코드인가

현재 제품은 **계층형 AI**다. PPO actor가 상대·공·자신의 상태에서 코스와 깊이를 선택한다. `AiPolicy`는 그 목표를 실제 샷 세기·각도로 변환하고, 기존 반응 지연/위치 오차/시도 확률을 적용한다. 이동 위치 예측, 서브 시작, 타격 타이밍/거리 검사, 스킬 충전/사용 시점은 기존 실행 계층이 담당한다. 게임은 같은 `SubmitInput`을 거치며 모델이 점수나 공 위치를 직접 바꾸지 않는다.

Unity ML-Agents도 학습/추론을 분리하는 선택지지만, 이번 구현은 기존 Unity 독립 C# 계약을 보존하려고 **Stable-Baselines3 PPO + PyTorch로 학습하고 C#에서 actor를 추론**한다. ML-Agents를 설치했다고 하거나 전체 경기·이동·서브·스킬을 end-to-end로 학습했다고 표시하지 않는다. 게임을 실행할 때 Python 서버, 인터넷, API 키가 필요하지 않다.

```text
Training/actions.csv + 검증된 gameplay CSV
 → Gymnasium 배치 환경 → Stable-Baselines3 PPO 학습
 → Runtime/Resources/DigitalTennisAI/placement-ppo.json
 → LearnedShotSelector → AiPolicy.PlanShot
 → game TennisAiOpponent → 일반 RacketInput/SubmitInput
```

## 재현 가능한 학습

Python3.10.12, 직접 의존성은 `requirements.txt`, 실제 환경 전체 버전은 `requirements-lock.txt`에 고정한다. 아래는 AI 저장소 root에서 실행한다. 학습은 CPU를 사용하며 센서/게임 창/다른 실행 앱을 조작하지 않는다.

```sh
python3.10 -m venv .work/rl-venv
.work/rl-venv/bin/python -m pip install -r Training/requirements-lock.txt
.work/rl-venv/bin/python Training/train.py --steps 65536 --seed 20261019
dotnet run --project tests/DigitalTennis.AI.Checks.csproj -c Release
```

현재 기본 `--balance`는 이 저장소의 `tests/balance.csv`다. 실제 제품 값을 쓰려면 `--balance /absolute/game/Assets/StreamingAssets/Balance/gameplay.csv`로 지정한다. `--actions`로 다른 액션 CSV를 지정할 수 있다. 액션의 순서/6개 출력은 모델 계약이며 재학습 없이 순서만 바꾸지 않는다. 현재 액션은 좌/중앙/우 × 깊게/짧게다. 배치 폭/깊이의 절대 값은 게임의 `ai.target_width`, `ai.target_depth`를 쓰고 CSV의 factor를 곱한다. 형상·유한값·정규화 스키마는 버전1로 검증한다.

출력은 배포용 actor JSON, `Models/placement-validation.json`, 비공개 생성물 `.work/placement-checkpoint.zip`이다. ZIP·venv·대규모 학습 로그를 Git에 넣지 않는다. 모델 재개 학습 기능은 아직 없다. 같은 seed/도구/데이터로 재학습할 수 있지만 OS·수치 라이브러리 간 비트 단위 동일성을 보장하지 않는다. 실제 배포 파일은 SHA256으로 식별한다.

## 관측·행동·보상 계약

- 관측12개: 공 XYZ·속도XYZ, 상대XZ, 자신XZ, 샷 multiplier, 중력. `LearnedShotSelector.Observe`는 자신의 코트를 +Z로 맞춘 뒤 `[4.115,4,11.885,30,30,30,4.115,11.885,4.115,11.885,2,30]`으로 나눈다. 정규화 상수는 단위/스키마이며 밸런스 값이 아니다. 학습과 C#의 순서를 함께 변경한다.
- actor는12→32(tanh)→32(tanh)→6(logit)이고 argmax로 배포 추론한다. 입력 프레임당 무한 재추론하지 않고 실제 타격 의도 한 번에 한 결정을 한다. 동일 incoming ball의 중복 스윙, pause/온라인/포인트 종료에는 새 판단을 하지 않는다.
- 환경은 무작위 접촉 위치·상대 위치·샷 multiplier에서 **한 번의 샷 배치**를 평가하는1단계 MDP다. 보상은 탄도·조준/세기 제한 후 네트/경계 통과와, 비행 시간 대비 상대의 필요한 이동 거리다. 학습은 이 보상으로 PPO를 최적화하며 정답 액션을 직접 가르치는 지도학습이 아니다.
- 반발·회복·장기 전술·실제 상대의 움직임을 포함한 완전한 매치 환경이 아니다. 보상의 네트 높이는 `Training/environment.csv`의0.97m이며 현재 게임의 정적 높이 기준을 사용한다. 네트 두께/충돌 적분을 근사하므로, 완전한 Unity 충돌 검증을 대체하지 않는다. 승률·랠리 길이 개선은 별도 실제 경기 평가가 필요하다.

## 포함한 모델의 근거

seed20261019,65,536학습 단계와 겹치지 않는 seed의2,048상황에서 배치 보상은 **0.568433**, 무작위 정책은**0.214257**, 같은6액션 중 최고 보상은**0.580682**이다. 이는 테니스 승률이 아니다. 평가에서는 네 가지 코너/깊이 액션이 사용됐고 중앙 두 액션은 선택되지 않았다. 현재 보상이 코너 압박을 선호하는 한계로 기록한다. 재훈련 결과를 이 숫자로 덮어 맞추지 않는다.

모델 SHA256은 `3e6bcdc207315fc8dbd284bec82ca41727ce44ffbffc4917a030d8ac150fb4eb`다. 평가 파일의64개 분리 관측에서 SB3와 C# actor의 액션 일치를 검사한다. C# 검사는 변조된 형상/NaN 거부·입력 대칭·비활성 상태·중복 판단도 확인한다. 실제 Unity 경기를 확인한 결과는 게임 PR/문서에 따로 기록한다.

## Unity 사용과 모델 교체

게임은 이 패키지의 Git 커밋을 UPM에 고정하고 `Resources/DigitalTennisAI/placement-ppo`를 불러온다. 게임의 `TennisLearnedPolicy.Load`, `TennisAiOpponent`가 연결 지점이다. 일반1인 경기에서 학습 코스 선택이 기본이며 상/중/하의 기존 CSV 반응/오차/확률/세기 제한은 계속 적용한다. 온라인 대전이나 연습용 자동 스윙에 모델을 섞지 않는다.

게임 실행 머신의 `Application.persistentDataPath/AI/placement-ppo.json`에 검증한 actor를 두면 다음 경기/AI 재생성 때 적용한다. macOS 기본 앱에서는 `~/Library/Application Support/Digital Tennis/Digital Tennis/AI/placement-ppo.json`이다. 파일은 임시 파일에 완성한 뒤 원자적으로 교체한다. 실행 중 매 프레임 파일을 읽지 않으며 재빌드가 필요하지 않다. 크기256KiB 이하·스키마/형상/유한값 검사를 통과해야 한다. 교체 파일이 잘못됐으면 경고와 함께 번들 모델, 번들까지 잘못됐으면 화면에 기본 AI 대체 상태를 표시한다. 조용히 정지하지 않는다.

일반 창에서 상대 HUD의 **학습 AI**와 **내 서브를 기다리는 중 / 서브 준비 중 / 경기 진행 중**을 확인한다. 사람 차례의 서브 대기는 AI 정지가 아니다. 게임이 일시정지됐거나 선택한 무선 기기가 끊기면 먼저 화면의 원인을 해결한다. 진단 로그 `TENNIS_AI_MODEL`과 `TENNIS_AI ... learnedDecisions=N learnedAction=N`은 모델 로드·실제 판단과 타격 승인 여부를 구분한다.

## 다음 학습 단계와 변경 지점

| 개선 | 수정할 곳 | 함께 검증할 것 |
| --- | --- | --- |
| 새 관측 | `Observe`, `Training/train.py`, 스키마 | 정규화·코트 반전·C#/Python parity, 기존 모델 거부 |
| 새 행동/보상 | `Training/actions.csv`, `Placement.reward`, actor 스키마 | 재학습·분리 평가·실제 경기 결과 |
| 완전한 경기/자기 대전 | 새 Unity ML-Agents 또는 Gym bridge 환경 | 진짜 점수·종료·reset, ordinary input, pause/online 격리 |
| 이동/서브/스킬까지 직접 학습 | 명시적인 새 action contract와 게임 actuator | 기존 도달 거리·스킬 사용권·호스트 권한 우회 금지 |

학습 보고서에 seed·스텝·데이터/모델 해시·보상 정의·무작위 기준선·실제 경기 여부를 남긴다. 학습 도구의 설치 성공과 학습/게임 검증을 서로 대체하지 않는다.

공식 참고: [SB3 PPO](https://stable-baselines3.readthedocs.io/en/v2.3.2/modules/ppo.html), [정책 네트워크](https://stable-baselines3.readthedocs.io/en/v2.3.2/guide/custom_policy.html), [Unity ML-Agents 설치](https://unity-technologies.github.io/ml-agents/Installation/).
