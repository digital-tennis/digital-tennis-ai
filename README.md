# Digital Tennis 독립 AI 플레이어

예상 착지점, 이동·타격 의사결정, 하·중·상 난이도를 담당하는 독립 제품 저장소입니다. 전체 프로젝트는 **외장 IMU를 별도로 부착한 NU40-DK**, Unity PC 게임, 1인 AI와 온라인 2인 대전을 12일·3명으로 개발합니다.

## 현재 상태

개발 계획과 초기 문서가 준비된 단계입니다. 제품 코드는 아직 구현되지 않았습니다. 실행 명령은 D1 도구 선택과 실제 구현 뒤에 추가합니다. 모의 입력으로 먼저 검증하고 실물/다른 제품과 통합합니다.

## 개발할 기능과 제출 기준

[초보 개발자용 상세 과제](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md)에서 상황·입력·출력·예제·예외·완료 기준을 확인합니다.

- [AI-01 Unity에 의존하지 않는 AI 상태와 결정 API](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md#ai-01)
- [AI-02 공 착지점과 이동 목표 예측](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md#ai-02)
- [AI-03 하·중·상 난이도 정책](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md#ai-03)
- [AI-04 반복 실행과 난이도 검증 도구](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/products/digital-tennis-ai.md#ai-04)

## 개발 환경과 예상 구조

초기 담당 역할은 B입니다. 실제 IMU·배선·펌웨어 SDK·Unity·Windows·런타임 버전은 D1에 [환경표](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/project/overview.md)와 결정 기록에 남깁니다.

예상 폴더는 `src/ · tests/ · examples/ · difficulty/`입니다. 아직 존재하지 않는 폴더와 실행 명령을 구현 완료로 해석하지 않습니다. 채택 도구와 실제 구현에 맞게 갱신합니다.

## 검증과 협업

- [12일 WBS](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/planning/wbs.md)
- [컨트롤러 계약](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/contracts/controller-protocol.md)
- [온라인 계약](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/contracts/online-protocol.md)
- [수용 테스트](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/testing/acceptance.md)
- [브랜치·PR 작업 방법](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/guides/contributing.md)
- [모든 제품과 의존 관계](https://github.com/digital-tennis/digital-tennis-docs/blob/main/docs/project/repositories.md)

라이선스는 코드와 제3자 자산 조건을 검토한 뒤 팀이 선택합니다.
