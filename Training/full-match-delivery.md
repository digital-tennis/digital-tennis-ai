# 전체 경기 학습·평가·재개 계약과 실행 결과

2026-10-21 실행 결과다. 기본 규칙은 best-of-3, 6게임 세트와 6–6의 7점 타이브레이크(마지막 세트 포함)다. 점수·게임·세트·완료는 Unity authoritative BallFlight/TennisMatch에서만 발생한다.

| 단계 | 실제 측정 | 해석·제한 |
| --- | --- | --- |
| 학습 전 확장 baseline | 15명 cyclic offset+1 × 3난이도 × 2시드 = 90사례, 972점, AI 승인 1,608/거부 0 | 사례별 2서비스게임, 225개 전체 대진이나 완료 매치 아님 |
| 전체 경기 PPO | 65,536 step, 32 rollout update/128 optimizer epoch, 완료 8경기·96게임·16세트, 부분 경기 포함 500점 | Hard Near 대 Medium Far, 완료 8경기 모두 Near 2–0. 대등한 승률·개선 증거 아님 |
| 동결 상대 self-play | 133,120 학습 step, 65 rollout update/260 epoch, 학습 중 2경기 완료 | 완료를 위해 초기 32,768 예산 연장. 추가 45,729 finish-only step은 학습 아님. 전체 3경기·523점 |
| 분리 평가 | 6경기·952점, scripted 1/2승, random 0/2승, frozen 2/2승 | 역할 교대, 학습과 분리된 seed/대진, update 0·전후 가중치 동일. 인간 승률·개선 보장 아님 |
| complete-state 재개 | 준비 4,096 step 후 trainer 종료·새 프로세스에서 8,192 step/4 rollout update/16 epoch 추가 | global step 137,216→145,408, 실제 46점. 같은 partial match이며 추가 완료 경기 0 |
| 일반 runtime 자동 검사 | EditMode 210, PlayMode 48통과/6제외, 별도 scene 1통과. scene 79점·AI 승인150/거부0·Far 2세트승 | 기존 fixture 상대이며 인간 평가 아님 |
| Mac GPU batch | 빌드·실제 카메라/UI/일반 입력, 86점·2–6/2–6, 오류0·pause/rematch 통과 | **일반 창 육안 검수는 시스템 잠금으로 미완료**. batch를 ordinary window로 세지 않음 |

학습은 관측 v2의32개 경기 상태에 따른 action v1의6개 코스·깊이 전술이다. actor는 32→32→32→6 tanh이며 고정 scale/clip 정규화를 사용한다. 이동·서브·반응·타격 시점/세기·스킬 안전 실행은 결정적 코드다. 모든 타격은 SubmitInput, 서브/Skill은 일반 PlayerAction과 실제 재고 gate를 통과한다. Near/Far identity는 end change에도 고정된다. pause/menu/online/비권한 상태에서 정책을 진행하지 않는다. 정상 추론은 독립 netstandard2.1 C#이며 Python/네트워크/API를 요구하지 않는다.

동결 풀은 초기 actor+16개 snapshot이고 경기 시작에 `(episode-1) % poolSize`를 선택해 경기 내내 고정한다. 학습자 Near/Far를 교대하며 평가에서 학습하지 않는다. CSV가 학습량·보상·PPO·snapshot 간격·seed를 검증한다. 모델은 버전/shape/finite/크기 검사 후 적용한다.

체크포인트는 actor/critic·Adam·SB3/Monitor/VecEnv·관측·counter·Python/NumPy/Torch/양쪽 RNG·고정 normalization·버전/설정/소스 hash·실제 상대 풀 bytes·schedule을 저장한다. fsync한 immutable ZIP 뒤 원자 pointer를 교체하고 deserialize 전 hash를 검증한다. 저장된 rollout 경계와 살아 있는 같은 Unity world/lease가 필요하다. **Unity 종료 후 world 복원은 지원하지 않는다**. 손상/환경 불일치는 실패시키고 직전 generation은 명시적으로만 선택한다. 로컬 신뢰 checkpoint만 읽으며 hash가 악성 pickle의 보안 경계라는 주장은 하지 않는다.

기존 software-followup 자료는 보존한다. 새 raw·작은 보고서·모델·캡처는 game의 `docs/evidence/ai-full-match/`에 있다. gzip raw는 손실 없는 기록이며 전체 idle step 생략 범위와 finish-only를 보고서에 구분한다. venv·전체 checkpoint·빌드·큰 로그는 무시되는 `.work/`/`Builds/`에 남긴다. 모델/설정/소스 SHA-256은 각 JSON에 있다. 당시 baseline과 재개의 `unity.sh`를 hash가 정확히 일치하는 감사 사본으로 보존하며, 이후 제품 통합으로 바뀐 파일을 당시 실행 소스로 오인하지 않는다.

NU40-DK+별도 외장 IMU, 최초12일·3명·36PD 계획은 그대로다. 이번 확장에서 하드웨어·Windows 실기·두 PC/WAN 검증은 수행하지 않았다. 자체 코드/문서/학습 가중치는 Apache-2.0, SB3/Gymnasium MIT 및 Torch/NumPy BSD 계열과 기존 자산 라이선스·NOTICE는 유지한다. Python 3.10.12, SB3 2.3.2, Gymnasium 0.29.1, Torch 2.2.2, NumPy 1.26.4와 전이 의존성은 AI `Training/requirements-lock.txt`로 고정한다.

## 실행 경계와 명령

AI 저장소의 `Training/full_match.py`, `self_play.py`, `checkpoint.py`, `resume.py`가 학습/동결/완전 저장을 맡는다. game의 테스트 전용 loopback bridge만 Unity를 step한다. 일반 사용자 경기에는 bridge를 켜지 않는다. 기본 placement `train.py`는 과거 한 샷 실험이며 현재 전체 경기 성과로 세지 않는다.

```sh
python3.10 -m venv .work/rl-venv
.work/rl-venv/bin/python -m pip install -r Training/requirements-lock.txt
.work/rl-venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
dotnet run --project tests/DigitalTennis.AI.Checks.csproj --configuration Release
```

다음 명령은 game feature checkout에서 실행한다. `<venv-python>`과 `<ai-checkout>`은 위 환경과 이 AI feature checkout이다.

```sh
python3 tools/train-ai-full-match.py --python <venv-python> --ai <ai-checkout>
python3 tools/run-ai-self-play.py --python <venv-python> --ai <ai-checkout>
python3 tools/run-ai-resume.py --python <venv-python> --ai <ai-checkout>
```

원본을 덮어쓰지 않는 별도 출력/checkout이 필요하다. game의 `docs/ai-full-match-*.md`와 `docs/evidence/ai-full-match/delivery.json`이 실행 명령·hash·PR·미완료 정본이다. 이 package의 full-match 번들은 최초 전체 경기 PPO(65,536 step)다. game은 별도 Resources에 재개 actor(145,408 step)를 보유한다. placement/full-match/resumed 모델을 혼동하지 않는다.

본 feature는 draft PR이며 main에 merge하지 않는다. game은 공개 feature commit을 pin한다. 승인된 squash merge 뒤 새 squash SHA로 repin하고 Unity resolve/검사를 재실행한다. 일반 창 검수와 물리 검증을 CI 성공으로 대체하지 않는다.
