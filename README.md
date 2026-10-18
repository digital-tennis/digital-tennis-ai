# Digital Tennis · 독립 AI 플레이어

게임 상태를 받아 상·중·하 난이도의 이동 목표와 라켓 입력을 반환하는 재현 가능한 C# 정책이다.

전체 제품은 NU40-DK에 **별도 외장 IMU**를 부착하는 라켓 컨트롤러와 Unity PC 테니스 게임으로 구성한다. 최초 계획은 **12일·3명**이다.

## 주요 기능

- 물리 계수를 주입받는 착지/타격 위치 예측
- seed 기반 반응/오차·공별1회 판단
- CSV 난이도 주입과 스킬 사용 제안

## 빠른 시작

검증 도구: .NET10 SDK. 라이브러리: netstandard2.1, UnityEngine 참조 없음.

```sh
bash tools/check.sh
```

## 책임과 현재 범위

AI는 공·점수·체력·스킬 재고를 직접 바꾸지 않는다. 게임이 정책 출력을 일반 입력 경계로 보내고 거리/권한/경기 상태를 검사한다. 온라인 상대를 대신 실행하지 않는다.

## 구조와 문서

`Runtime/`: 정책/수학/설정 · `tests/`: 독립 검사 · `package.json`: Unity UPM 메타데이터

[공개 정책 API](Runtime), [AI 개발 과제](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md)

## 도움말과 기여

재현 가능한 문제는 [이슈](https://github.com/digital-tennis/digital-tennis-ai/issues)로 남긴다. 관리 주체는 [Digital Tennis](https://github.com/digital-tennis)이며 [기여 안내](CONTRIBUTING.md)를 따른다. 검증 커밋을 고정하고 실제 장치 성공·모의 검사·교차 빌드를 구분한다.

## 라이선스

프로젝트 자체 코드·문서는 **[Apache-2.0](LICENSE)**이다. [NOTICE](NOTICE)와 [외부 코드·자산 고지](THIRD_PARTY_NOTICES.md)를 함께 확인한다. 외부 자산에 Apache-2.0을 덮어쓰지 않는다.
