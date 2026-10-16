# 공통 관찰값과 실행 스키마 설계안 v0

작성: 2026-10-06 · 작업 ID: W1-SCHEMA-DESIGN · origin: synthetic

현재 세션 범위: [D-006](../decisions.md)에 따라 데이터셋 완성에 집중한다. [데이터 작성 명세](../../data/ontology/README.md)는 합성 작성·정답 판정에 사용하며 아래 실행 구현 순서는 후속 기능 세션에서 진행한다.

후속 진행: [공통 자료형 최소 참고 구현](examples/README.md)을 작성하고 구조 테스트·Ruff·mypy를 실행했다(W1-COMMON-MODEL). 클래스별 온톨로지와 등록 필수 검증은 아직 미구현이다.

완료 기준은 공통 값 구조, 클래스별 등록 필수 정책, 조건부 검증, 기존 정답의 변환 규칙, 구현 시 확인할 사례를 문서화하는 것이다. 이 문서는 구현 가능한 구조를 정리한 **프로젝트 설계안**이며, 실행 온톨로지·생성 스키마 또는 검증된 업계 규칙은 아니다. 사용자 의미 검증과 W1 전체 CP-S1은 별도로 남는다.

## 1. 처리 단계와 데이터 계약

| 단계 | 데이터 | 역할 |
|---|---|---|
| 파싱 | 원문 블록과 위치 | 원문 값·라벨·단위·문맥을 보존 |
| 추출 | 속성 후보와 관찰 | 미해석 단위·불확실한 조건도 보존 |
| 정규화 | 클래스별 ProductCandidate | 단위·자료형·조건·대상 범위를 공통 구조로 변환 |
| 검증 | ValidationResult | 구조 오류, 누락, 불확실성, 불일치를 구별 |
| 검토·등록 | RegisteredProduct | 담당자가 선택·수정한 값과 근거·검증 이력 저장 |

각 명칭은 앞으로 구현할 자료형의 설계 이름이다. 추출 단계부터 최종 등록 필수 스키마를 강제하면 누락된 문서를 표현할 수 없으므로, 후보 스키마와 등록 승인 정책을 분리한다. 구조적으로 유효한 후보가 반드시 등록 준비 완료인 것은 아니다.

## 2. 공통 관찰값 구조 — U-02

`attributes`는 속성 ID를 키로 하고 **정규화된 사실 목록**을 값으로 가진다. 같은 값·조건·범위의 반복 문구는 하나의 사실에 근거 출현 목록으로 묶고, 다른 조건이나 서로 다른 값은 다른 사실로 유지한다.

| 필드 | 자료형·필수성 | 의미 |
|---|---|---|
| `value` | 속성별 자료형, 사실에 필수 | number/integer/string/boolean/list/range/dimensions |
| `unit` | 수치 물리량에 필수; 무단위 값은 null | 정규 단위; 단위 해석 실패는 확정 사실 대신 미해결 관찰로 보존 |
| `basis` | object, 해당 속성의 의미 기준 | capacity/pressure/rating/weight 등; 명시하지 않은 기준은 unknown |
| `condition` | object, 명시된 조건의 정규 표현 | 온도·기압·연료 기준 점도·주파수·정격점·엔진 사이클 등 |
| `scope` | string 또는 unknown | 주 제품·구성품, 단품·모듈 등 대상 범위 |
| `occurrences` | 위치·원문 근거 목록, 사실에 최소 1개 | raw_text, label_text, unit_text, source_document_id, location |

기준과 조건의 이름은 실행 YAML의 별도 정의에서 열거한다. 임의 키를 무제한 허용하지 않으며 신규 조건은 정의·버전과 함께 추가한다. 제조사별 원문을 자유롭게 보존하는 필드는 구조화 조건과 구별한다.

조건이 미기재되었을 때 관찰을 버리지 않는다. `unknown`은 명시적 상태이고 원문에 조건이 없다는 이유만으로 두 값이 같은 조건이라고 판단하지 않는다. 등록에 중요한 기준은 review 대상으로 남긴다. 성능에 적용되지 않는 조건은 해당 속성의 계약에 따라 not_applicable로 구별한다.

범위는 `{min, max}`로 보존하며 단일 수치를 임의 범위로 확장하지 않는다. 치수는 `{length, width, height}`이며 원문에서 알 수 없는 축은 null로 보존한다. 완전한 치수를 요구하는 출력에서는 세 축이 모두 있어야 한다. nullable 부분 관찰과 완전한 평가 객체의 계약을 구별한다.

### 합성 SEP의 표현 예시

다음은 현재 합성값을 사용한 일부 구조 예시다. 근거 위치는 본문 절/표 행 기준으로 붙이며 실제 PDF 페이지는 생성 전이라 null이다.

```yaml
attributes:
  rated_throughput:
    - value: 3600
      unit: l/h
      basis: {rating: maximum_capacity}
      condition:
        medium: HFO
        viscosity: {value: 380, unit: cSt, reference_temperature: {value: 50, unit: degC}}
        viscosity_basis: fuel_reference
      scope: separator
      occurrences: # 실제 제품 객체에서는 최소 1개 필요
        - raw_text: "3,600"
          label_text: "Max. capacity, HFO 380 cSt at 50 °C"
          source_document_id: DOC-003
          location: {section: "2", table: 1, row: 2, pdf_page: null}
    - value: 2100
      unit: l/h
      basis: {rating: maximum_capacity}
      condition:
        medium: HFO
        viscosity: {value: 700, unit: cSt, reference_temperature: {value: 50, unit: degC}}
        viscosity_basis: fuel_reference
      scope: separator
      occurrences:
        - raw_text: "2,100"
          label_text: "Max. capacity, HFO 700 cSt at 50 °C"
          source_document_id: DOC-003
          location: {section: "2", table: 1, row: 3, pdf_page: null}
```

기존 대표값/conditional_values의 저장 구분은 평가용 표시 정보로 남길 수 있다. 제품 사실 목록에서는 두 조건을 동등하게 유지하고, 첫 번째 사실을 자동으로 정격이라고 해석하지 않는다.

## 3. 중량·치수의 처리 — U-03

설계안에서는 기존 `dry_weight`와 추가 후보 `reported_weight`를 유지한다. 일반 중량의 건조 상태를 추측하지 않는다.

- dry가 명시된 관찰은 dry_weight에 연결한다. Weight/Net weight만 있으면 reported_weight로 두고 basis.weight를 명시값 또는 unknown으로 보존한다.
- 같은 원문 근거를 두 속성에 이중 등록하지 않는다. 이후 dry 근거가 확인되면 속성 분류 변경과 근거 추가를 이력으로 남긴다.
- 주 제품과 공급 모듈의 중량·치수는 scope로 구별한다. 다른 scope의 값을 E5 불일치로 비교하지 않는다.
- 도면 W1/W2/A/B를 근거 없이 length/width로 치환하지 않는다. 미해석 도면 치수는 원문 관찰로 보류한다.

이는 구현 설계안의 선택이다. 중량을 단일 속성으로 통합하는 안으로 변경한다면 이력과 버전을 함께 관리한다. 현재 합성 정답은 변경하지 않는다.

## 4. 압력의 처리 — U-05

`max_pressure`는 명시된 최대 작동 압력, `working_pressure`는 작동/최종 압력 후보로 구별한다. basis.pressure는 gauge/absolute/unknown, basis.rating은 maximum/nominal/final/unknown 등의 후보를 정의한다. bar 단위만으로 gauge라고 추정하지 않는다.

같은 원문값을 필수 조건을 만족시키기 위해 두 속성에 복제하지 않는다. 최대압과 작동압이 별도로 명시되면 독립적인 사실로 보존한다. FAD 기준 절대압은 capacity.condition의 일부이며 압축기 작동압에 넣지 않는다.

현재 COMP는 본문에 Max. working pressure와 gauge를 명시하고, 3.2의 반복값도 정답에서 같은 max_pressure에 연결한다. 이 합성 문서 안의 대응을 제조사 원본 전체의 final=max 동의어 규칙으로 확장하지 않는다.

## 5. 클래스별 등록 필수 정책안

maker/model_designation은 6개 클래스 공통 필수 후보다. 아래 추가 요건은 **프로젝트의 등록 준비 정책**이며 실제 제조사 제품의 법적·기술적 필수 요건이 아니다.

| 클래스 | 추가 필수 후보 | 조건/중요 기준 | 누락·불확실할 때 |
|---|---|---|---|
| Pump | pump_type, capacity | centrifugal: head. three_screw: differential_pressure/discharge_pressure 중 최소 1개 | 형식 미상이면 조건 분기를 추측하지 않고 review; 형식이 확정됐는데 필요한 값이 없으면 missing |
| AirCompressor | capacity, max_pressure/working_pressure 중 최소 1개 | capacity_basis와 압력 기준, 작동/최대 의미 보존 | 미상 기준은 review; 정보 자체가 없으면 missing |
| Separator | application, rated_throughput | 처리량 조건과 정격/최대/권장 기준 | 서로 다른 점도 조건은 정상 복수 값; 중요한 조건 부족은 review |
| TwoStrokeMainEngine | rated_power, rated_speed, number_of_cylinders | 엔진 전체 출력과 대응 정격점·회전수 | 대응 정격점 불명은 review; 전체 출력 부재는 missing |
| FourStrokeEngine | application, rated_power, rated_speed, number_of_cylinders | 엔진/발전기, 축/전기 출력, 정격·주파수 구별 | 다른 출력 대상을 합산하지 않음; 대상 불명은 review |
| Turbocharger | turbocharger_type, applicable_engine_power | 형식의 대상 부위, 엔진 사이클·per-unit 기준 | 단일값/범위를 보존; 중요한 적용 기준 불명은 review |

선택 속성인 중량·치수·연료·냉각 방식·베어링 등을 누락만으로 오류 처리하지 않는다. 빈 문자열, 빈 목록, 미해결 원문 관찰은 확정 등록값으로서 필수를 충족하지 않는다. 수치 0과 boolean false는 누락과 구별하고, 허용 범위는 근거 있는 별도 규칙으로 검사한다.

## 6. 판정 결과의 구별

| 판정 | 의미 | 기록할 근거 |
|---|---|---|
| structural_error | 자료형·단위 차원·대상 클래스 계약 위반 | 속성 ID, 기대형/차원, 원문 위치 |
| missing | 확정된 등록 필수 정책에 필요한 값이 없음 | 적용 규칙, 누락 속성, 문서 |
| review | 조건·범위·분류·기준이 불명확해 자동 결정 불가 | 불명 항목과 근거, 검토 이유 |
| conflict | 동일 조건·기준·scope의 값이 허용차를 초과해 불일치 | 두 값과 위치, 비교 키, 적용 허용차 |
| not_checked | 근거 있는 검증 규칙이 없음 | 미구현/미검증 규칙 구별 |

이는 내부 판정 상태의 설계안이다. 기존 E1~E7 라벨과의 대응은 구현 시 기존 계획과 대조한다. 하나의 pass/fail로 압축하지 않는다. 자동 등록 준비 상태와 담당자의 최종 등록 승인은 별도로 표현한다.

불일치 비교 키는 제품·속성·정규 단위·basis·condition·scope다. 중요한 키 요소가 unknown이면 동일하다고 가정하지 않고 review로 둔다. 현재 합성 rated_power의 허용차를 다른 제품에 무조건 적용하지 않는다.

## 7. 기존 정답 v2의 연결

| 정답 필드 | 후보 제품 구조로 연결 |
|---|---|
| attributes.*.value/unit | 해당 속성 사실 목록의 value/unit |
| occurrences | 대응 사실의 근거 목록; 조건이 같은 반복은 하나의 사실로 묶음 |
| conditional_values | 같은 속성의 별도 사실; 정상 조건으로 보존 |
| rating_basis/capacity_basis/pressure_basis/weight_basis | basis의 각 정의 키 |
| condition | 타입이 정의된 조건으로 변환; 원문 텍스트와 변환 근거도 보존 |
| reference_conditions | capacity.condition의 온도·기준 절대압 |
| scope | 대상 범위 유지; 미지정은 근거 확인 전까지 unknown |
| reviewed_by/injections/files/duplicate_of | 평가기 메타데이터; 모델의 제품 출력에 넣지 않음 |
| expected_status/missing_required/validation_status | 미확정 상태 유지; 자료형 검사만으로 pass로 변경하지 않음 |

현재 대표 속성 55개와 조건부 값 1개는 변환 후에도 평가 단위 56개로 추적한다. 표시용 대표값 선택은 실제 제품의 정격값이라는 주장과 구별한다. 신규 속성 채택이나 평가 계약 변경이 필요하면 실험 전에 정답·정책 버전을 갱신한다.

## 8. 구현 순서와 확인 사례

1. 관찰·근거·조건·값 자료형의 공통 모델을 작게 정의한다.
2. 6개 클래스의 후보 속성·상속과 등록 필수 규칙을 YAML로 표현한다.
3. 로더에서 ID·상속·참조 대상·조건 분기·단위 차원의 일관성을 확인한다.
4. 후보용 JSON Schema와 등록 준비 검증기를 구별해 작성한다.
5. 개발용 합성 사례로 동작을 검사하고 현재 6건은 정답 변환의 대조 자료로 사용한다.

| 확인 사례 | 기대 동작 |
|---|---|
| SEP의 점도 조건 두 개 | 정상 사실 두 개 보존, conflict 없음 |
| 같은 조건의 서로 다른 유량 | 두 근거 유지, conflict 후보 |
| 같은 값·조건의 표/본문 반복 | 하나의 사실·두 출현, TP를 늘리지 않음 |
| 원문에 Weight만 있음 | reported_weight/unknown, dry 추정 금지 |
| 최대압/최종압 의미가 불명확 | review, 동의어로 강제 병합하지 않음 |
| 압축기 FAD 기준 절대압 | capacity 조건에 연결, 작동압으로 오매핑하지 않음 |
| 미지의 pump_type | 조건부 head/압력 규칙을 강제 적용하지 않음 |
| 부분 치수·형식 미정 구성품 | 원문 관찰 유지·review, 값이나 제품 관계를 만들어내지 않음 |

이 순서는 기존 W1 계획을 세분화한 것이며 일정·대상 클래스를 바꾸지 않는다. 공통 모델 최소 참고 구현을 완료했으며, 데이터 작성용 온톨로지 YAML을 별도 정리했으며 다음은 합성 사례 배분·분할 계획이다. 로더와 실행 스키마는 후속 기능 세션에서 진행한다. 일반 도메인 규칙의 사용자 verified_by와 CP-S1은 아직 미완료다.
