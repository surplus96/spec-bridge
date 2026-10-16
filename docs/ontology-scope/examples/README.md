# 공통 모델 최소 참고 구현

2026-10-06 · W1-COMMON-MODEL · 구조 정책 origin: synthetic

[common_models.py](common_models.py)는 교육 모드에서 읽고 실행할 수 있는 작은 참고 구현이다. 전체 애플리케이션 패키지나 클래스별 온톨로지 구현은 아직 만들지 않았다. [실행 스키마 설계안](../schema-design.md)의 공통 부분만 구현한다.

## 읽는 순서

1. `Location`과 `Occurrence`: 값이 나온 문서·위치를 보존한다. 실제 PDF가 없으면 pdf_page는 null이고 절/표 행으로 위치를 나타낼 수 있다. 페이지 0이나 테이블 없는 row는 거부한다. 이번 모델은 PDF/절/표 위치를 다루며 Excel sheet/cell 위치는 파서 단계에서 확장한다.
2. `Quantity`와 `Conditions`: 기준 온도·기압·점도 등을 값의 조건으로 담는다. 정의하지 않은 조건 키는 거부한다. 값의 도메인 토큰과 단위의 의미는 아직 검증하지 않는다.
3. `Basis`: 압력 기준 미기재는 unknown이다. bar만으로 gauge를 채우지 않는다.
4. `NumericRange`와 `Dimensions`: 범위 순서를 검사하고 미상 치수 축은 null로 보존한다. 모든 축이 null이면 치수 사실을 만들지 않는다. 실제 장비의 수치 허용 범위는 여기서 검사하지 않는다.
5. `Fact`: 값 하나와 조건·기준·범위, 여러 출현 근거를 담는다. 근거는 최소 하나 필요하다. 문자열/boolean/정수 등의 실제 타입을 보존한다.

핵심 구조는 다음과 같다.

```text
Fact
├── value + unit
├── basis + condition + scope
└── occurrences[1..]
    ├── source_document_id + raw_text
    └── location
```

SEP의 조건별 두 처리량은 Fact 두 개로 유지한다. 같은 값·조건의 반복 문구는 한 Fact의 occurrences 여러 개로 표현할 수 있다. **자동 병합·불일치 판정은 구현하지 않았다.** 조건이 미상인 사실을 자동 병합하지 않는 정책은 이후 정규화·검증기에서 구현한다.

## 실행 확인

현재 로컬 Python 환경의 Pydantic v2, pytest, PyYAML을 사용했다. Ruff와 mypy는 별도 검사 도구다. 실행 위치는 저장소 루트다.

```bash
python -m pytest docs/ontology-scope/examples/test_common_models.py -q -p no:cacheprovider
ruff check docs/ontology-scope/examples
mypy docs/ontology-scope/examples/common_models.py --follow-imports=silent
```

테스트는 [schema-design.md](../schema-design.md)의 합성 예시에서 값을 읽는다. 실제 장비 허용 범위를 테스트 코드에 넣지 않는다. 조건·반복 출현의 JSON 왕복 보존, unknown/false/0의 구별, 잘못된 위치·조건·값 구조, 원문 공백 보존을 검사한다.

## 구현 범위와 다음 단계

- 제품 class/attribute ID의 온톨로지 존재 여부, 속성별 값 타입, 단위 차원·환산, 필수 조건, 등록 승인은 미구현이다.
- 따라서 일반 Fact의 value가 문자열이면 그대로 보존한다. capacity가 문자열이어도 속성별 수치 계약 위반인지 판단하는 것은 클래스별 스키마의 역할이다.
- 누락·미해석 입력을 정규 사실로 만들지 않고 별도 원문 관찰로 보관하는 모델, ProductCandidate 전체 구조, 등록 준비 검증기도 다음 단계다.
- 현재 정답 v2를 자동 변환하거나 expected_status를 pass로 채우지 않는다. 본문·정답·사용자 서명은 유지한다.

다음 작업은 클래스 계층·속성 자료형·단위 차원·조건 정의의 **최소 온톨로지 YAML 구성**이다. 그 정의를 읽는 로더와 클래스별 후보 스키마에 이 참고 자료형을 연결한다. 현재 공통 모델의 검증 성공은 W1 전체 DoD 또는 CP-S1 통과가 아니다.
