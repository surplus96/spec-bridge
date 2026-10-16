# Separator 범위 정의

상태: 정의표 작성 완료 · 경로: Equipment → FluidMachinery → Separator · origin: synthetic

지원 범위는 참고 원본의 선박용 연료유/윤활유 청정 원심 분리기다. 다른 산업의 모든 분리 장비를 포괄하지 않는다. 공급 펌프·히터가 언급되더라도 주 제품의 기술 사양과 제품 소개를 기준으로 클래스를 정한다.

공통 정의를 상속한다. S1/S2는 REF-SEP-01/02, S는 HW-SEP-001이다. 원본 관찰은 사용자 의미 검증 대기다.

| ID | 의미·대상 | 자료형 / 정규 단위·차원 | 필수 여부·이유 | 조건·기준 | 근거 |
|---|---|---|---|---|---|
| `application` | 연료유/윤활유 등 처리 용도 | enum 후보 / 없음 | 필수(안): 용도별 처리량 해석과 제품 비교 | fuel_oil/lube_oil 후보; 모듈 설치 위치와 유종은 구별 | S1 p.1, S2 p.7; S 1.3/1.4/표1 |
| `rated_throughput` | 원문이 제시한 처리량 | number의 조건별 관찰 목록 / l/h·체적유량 | 필수(안): 해당 유체 조건의 처리 능력 | 이름은 기존 ID 유지; rating_basis가 maximum/recommended/rated인지 보존, 모든 값을 정격으로 재해석하지 않음 | S1 p.4, S2 p.7; S 표2~3/3.1 |
| `self_cleaning` | 자체/자동 배출 기능이 명시된 여부 | boolean 또는 unknown / 없음 | 선택: 운전·보수 특징 | 미언급은 false가 아님; bowl 구조만으로 boolean 추측 금지 | S1 p.3의 배출 설명; S 1.3/표4/3.2 |
| `medium` | 처리하는 유체 | enum/string / 없음 | 선택: 용도 및 처리량 조건 보존 | heavy_fuel_oil 등은 조건과 연결; 포괄적 oil만으로 특정 등급을 추정하지 않음 | S1 p.1, S2 p.7; S 1.3/1.4/표1~3/3.1 |
| `motor_power` | 주 분리기 구동 전동기의 명시된 정격 | number / kW·동력 | 선택: 공급 펌프/히터와 구별 | 모듈 내 다른 부품 전력을 분리기의 모터 출력으로 합산하지 않음 | S 표5. 원본 S1/S2의 해당 kW 정격 직접 근거는 이번 범위 정의에서 미확인 |

등록 필수 후보는 maker/model_designation/application/rated_throughput이다. 처리량의 condition은 값의 의미를 정하는 데 필수다. 원본의 IF 등급과 별도 문서의 50 °C 점도를 조합해 모든 제품의 실제 투입 점도라고 일반화하지 않는다. 대표 조건은 표시·저장 정책이며 다른 정상 조건을 버리는 기준이 아니다.

## 합성 후보셋 연결

현재 9개 대표 속성 및 추가 조건 처리량 1개를 연결했다. S의 연료 기준 점도 두 조건은 모두 정상 관찰이다. dry_weight와 dimensions는 전체 separator module 범위다. S1의 Net weight와 도면 H1/W1/W2를 확인했다고 해서 다른 문서의 건조 상태나 L/W 변환을 확정하지 않는다. feed pump/heater 형식이 없으므로 확정 제품 관계는 비워 둔다.

## 미해결 사항

- U-02: 조건별 처리량과 IF 등급/기준 점도의 구조, 대표값 선택 정책.
- U-03: 모듈/단품 중량·도면 치수 범위.
- U-06: self_cleaning boolean을 유지하고 bowl_type을 확장할지 여부. 현재는 bowl_type 신규 채택 보류.

검증 사례 후보: 조건이 다른 처리량을 E5로 오판하지 않기, Net weight 건조 기준 확인, 구성품 언급으로 클래스 혼동하지 않기.
