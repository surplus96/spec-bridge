# 온톨로지 범위 정의 v0

작성: 2026-10-06 · 작업: W1 범위 정의 / FR-01 · 근거: [D-002·D-005](../decisions.md)

**정의표 작성: 6/6 완료.** 속성 의미·자료형·정규 단위·조건·필수 여부 후보와 미해결 사항을 작성했다. 데이터 작성용 [온톨로지 YAML 명세](../../data/ontology/README.md)를 후속 작업으로 정리했다. 로더·JSON Schema 등 기능 구현은 이번 데이터셋 세션에서 제외하며 실제 도메인 사실의 사용자 검증은 별도다. 이 문서는 산업 표준 온톨로지가 아니라 프로젝트가 정한 범위 정의다(`origin: synthetic`).

## 범위와 문서

```text
Equipment
├── Engine
│   ├── TwoStrokeMainEngine
│   └── FourStrokeEngine
├── FluidMachinery
│   ├── Pump
│   ├── AirCompressor
│   └── Separator
└── EngineComponent
    └── Turbocharger
```

| 클래스              | 정의표                                                | 원본           |
| ------------------- | ----------------------------------------------------- | -------------- |
| Pump                | [pump.md](pump.md)                                     | REF-PUMP-01/02 |
| AirCompressor       | [air-compressor.md](air-compressor.md)                 | REF-COMP-01/02 |
| Separator           | [separator.md](separator.md)                           | REF-SEP-01/02  |
| TwoStrokeMainEngine | [two-stroke-main-engine.md](two-stroke-main-engine.md) | REF-2S-01/02   |
| FourStrokeEngine    | [four-stroke-engine.md](four-stroke-engine.md)         | REF-4S-01/02   |
| Turbocharger        | [turbocharger.md](turbocharger.md)                     | REF-TC-01/02   |

공통 정의는 [common-attributes.md](common-attributes.md), 결정·보류 사항은 [open-issues.md](open-issues.md), 원본 판본·페이지·짧은 관찰 표기는 [reference-evidence.yaml](reference-evidence.yaml)에 있다. 원본 문서 전체의 수치를 일반적인 허용 범위로 사용하지 않는다.

후속 작업 W1-SCHEMA-DESIGN의 [공통 관찰값·등록 필수 정책 실행 스키마 설계안](schema-design.md)을 작성했다. 실행 구현과 사용자 의미 검증은 별개이며 기존 미해결 사항을 자동으로 해결 처리하지 않는다.

## 정의표를 읽는 기준

- **필수(안):** 제품 등록 정책으로 제안한 항목. 실제 기업의 필수 항목이라는 주장이 아니다. 클래스별 이유와 함께 사용자 검토 후 실행 스키마로 옮긴다.
- **조건부(안):** 특정 형식 또는 값의 의미를 확정할 때 필요한 항목. 조건의 판단 근거가 없으면 오류로 강제하지 않고 검토 대상으로 남긴다.
- **선택:** 값이 없다고 생성하거나 오류로 판단하지 않는다. 원본에 없거나 단품/모듈 범위가 다르면 그 사실을 보존한다.
- **정의·자료형·정규 단위·등록 필수 정책의 origin:** synthetic. 속성명이 원본에 있다는 관찰과 프로젝트의 구조 설계를 구별한다.
- **원본 관찰의 확인 상태:** 이번 작업의 자동 텍스트 존재 대조 완료, 속성 의미/일반 규칙에 대한 `verified_by: null`, 사용자 검증 대기. manifest의 문서 식별 검증 서명을 관찰이나 새 도메인 규칙에 옮겨 적지 않는다.
- **합성 근거 S:** 현재 합성 문서의 기술 본문에서 직접 정의한 사항. 실제 제조사 원본의 사실처럼 사용하지 않는다.

새 ID인 `reported_weight`, `differential_pressure`, `discharge_pressure`, `working_pressure`는 **정의 후보**로 등록한다. 아직 실행 온톨로지에 존재하지 않는다. 현재 6건의 정답이나 코드가 이미 새 ID를 지원한다고 해석하지 않는다.

## 공통 표현 정책

값은 단순한 숫자뿐 아니라 **값·단위·조건/기준·대상 범위·근거 위치**를 함께 가진다. 같은 속성의 관찰은 목록으로 유지하고, 조건과 범위가 같은 관찰끼리만 불일치를 판정한다.

제품군 범위와 특정 모델의 정격값을 구별한다. 예를 들어 `Up to`는 최대 성능 표기이며 임의의 정격점으로 치환하지 않는다. 제품군 표의 서로 다른 모델은 별도 제품 후보로 분리한다. 미지의 조건·단위 기준·부분 치수는 원문을 보존하고 자동 유추로 채우지 않는다.

원문 속성명은 조건이 붙은 매핑 규칙으로 연결한다. Weight를 무조건 dry_weight로, Power consumption을 무조건 motor_power로, nominal working pressure를 무조건 max_pressure로 연결하지 않는다. 정확한 동의어 목록과 열거값은 실행 스키마 전에 별도로 확정한다.

## 합성 평가 후보셋과의 관계

기존 55개 대표 속성은 6개 정의표의 공통/고유 후보로 모두 연결했다. SEP의 추가 처리량 1개는 같은 속성의 다른 조건으로 표현한다. 후보셋의 56개 채점 단위와 상태 필드는 변경하지 않았다.

현재 6건은 설계 과정에서 이미 참고했으므로 완전한 독립 테스트 자료로 주장하지 않는다. 새 속성이 실행 스키마에 채택되면 개발 자료와 원본 근거를 기준으로 정의하고, 평가 전에 정답·채점 정책의 버전 변경 필요성을 판단한다. 예를 들어 TC 로터 회전수는 이번 정의에서 확장 보류이며 기존 정답 분모에 몰래 추가하지 않는다.

## 작업 완료 확인

- [X] 공통 속성 및 관계의 의미·자료형·필수 이유 작성
- [X] 6개 클래스의 경계와 고유 속성 정의표 작성
- [X] 조건·기준·단품/모듈 범위의 차이 기록
- [X] 원본 12건의 판본·페이지 근거 연결 및 짧은 표기 존재 재대조
- [X] 기존 합성 정답 속성 55개와 정의 후보의 연결 확인
- [X] 미해결 항목과 다음 작업 기록
- [ ] 사용자 의미 검증 및 필수/열거값 정책 확정
- [X] 데이터 작성용 온톨로지 YAML 및 기존 후보 표현 대조 — DATA-CONTRACT
- [ ] 로더·생성 스키마 구현 — 후속 기능 세션
- [ ] W1 전체 DoD 및 CP-S1 검토

검사 결과는 [범위 정의 점검 결과](../../data/eval/reviews/ontology-scope-definition-checks.json)와 [원본 표기 점검 결과](../../data/eval/reviews/ontology-scope-source-checks.json)에 기록한다. 자동 검사는 문서 구성·근거 위치·기존 속성의 누락 여부를 확인하며 도메인 의미의 사용자 승인을 대신하지 않는다.
