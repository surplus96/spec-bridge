# 온톨로지 정의서

자동 생성 문서 — 원본 `ontology/ontology.yaml` (version 0, origin synthetic). 직접 수정하지 말고 YAML을 고친 뒤 `uv run python -m spec_bridge.ontology.docs`로 다시 만든다.

클래스 구조와 필수 정책은 프로젝트가 정한 합성 등록 정책이며 업계 표준 분류나 실제 법적·기술적 필수 요건이 아니다.

## 클래스

상위 클래스: Equipment, FluidMachinery, Engine, EngineComponent

### Pump

상속: Pump → FluidMachinery → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| medium | string | — | dimensionless | — |
| motor_power | number | kW | power | — |
| pump_type | string | — | dimensionless | 필수 |
| capacity | number | m3/h | volume_flow | 필수 |
| head | number | m | length | 조건부 |
| differential_pressure | number | bar | pressure | 조건부 |
| discharge_pressure | number | bar | pressure | 조건부 |

- 조건부: pump_type = centrifugal이면 head
- 조건부: pump_type = three_screw이면 differential_pressure 또는 discharge_pressure

### AirCompressor

상속: AirCompressor → FluidMachinery → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| medium | string | — | dimensionless | — |
| motor_power | number | kW | power | — |
| capacity | number | m3/h | volume_flow | 필수 |
| max_pressure | number | bar | pressure | 그룹 필수 |
| working_pressure | number | bar | pressure | 그룹 필수 |
| cooling_type | string | — | dimensionless | — |

- 하나 이상 필수: max_pressure 또는 working_pressure

### Separator

상속: Separator → FluidMachinery → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| medium | string | — | dimensionless | — |
| motor_power | number | kW | power | — |
| application | string | — | dimensionless | 필수 |
| rated_throughput | number | l/h | volume_flow | 필수 |
| self_cleaning | boolean | — | dimensionless | — |

- application 허용값(합성 닫힌 목록): fuel_oil, lube_oil

### TwoStrokeMainEngine

상속: TwoStrokeMainEngine → Engine → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| rated_power | number | kW | power | 필수 |
| rated_speed | number | rpm | rotational_frequency | 필수 |
| number_of_cylinders | integer | — | dimensionless | 필수 |
| fuel_types | string_set | — | dimensionless | — |
| bore | number | mm | length | — |
| stroke | number | mm | length | — |


### FourStrokeEngine

상속: FourStrokeEngine → Engine → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| rated_power | number | kW | power | 필수 |
| rated_speed | number | rpm | rotational_frequency | 필수 |
| number_of_cylinders | integer | — | dimensionless | 필수 |
| fuel_types | string_set | — | dimensionless | — |
| application | string | — | dimensionless | 필수 |
| bore | number | mm | length | — |
| stroke | number | mm | length | — |

- application 허용값(합성 닫힌 목록): propulsion, genset

### Turbocharger

상속: Turbocharger → EngineComponent → Equipment

| 속성 | 자료형 | 정규 단위 | 차원 | 필수 |
| --- | --- | --- | --- | --- |
| maker | string | — | dimensionless | 필수 |
| model_designation | string | — | dimensionless | 필수 |
| dimensions | dimensions | mm | length | — |
| dry_weight | number | kg | mass | — |
| reported_weight | number | kg | mass | — |
| turbocharger_type | string | — | dimensionless | 필수 |
| applicable_engine_power | number / range | kW | power | 필수 |
| bearing_type | string | — | dimensionless | — |


## 라벨 별칭

| 라벨 | 속성 | 구분 | 출처 | 위치 | 검증자 |
| --- | --- | --- | --- | --- | --- |
| nominal flow rate | capacity | 합성 | REF-PUMP-01 | pdf_page 3 | 미검증 |
| Head | head | 합성 | REF-PUMP-02 | pdf_page 3 | 미검증 |
| Dimensions | dimensions | 합성 | REF-PUMP-01 | pdf_page 5 | 미검증 |
| FAD* | capacity | 합성 | REF-COMP-01 | pdf_page 10 | 미검증 |
| Charging capacity | capacity | 합성 | REF-COMP-02 | pdf_page 5 | 미검증 |
| Nominal working pressure | working_pressure | 합성 | REF-COMP-01 | pdf_page 10 | 미검증 |
| Final pressure | working_pressure | 합성 | REF-COMP-02 | pdf_page 5 | 미검증 |
| Max. recommended capacity | rated_throughput | 합성 | REF-SEP-01 | pdf_page 4 | 미검증 |
| Bore: | bore | 합성 | REF-2S-02 | pdf_page 26 | 미검증 |
| Stroke: | stroke | 합성 | REF-2S-02 | pdf_page 26 | 미검증 |
| Number of cylinders: | number_of_cylinders | 합성 | REF-2S-02 | pdf_page 26 | 미검증 |
| Power [kW] | rated_power | 합성 | REF-2S-02 | pdf_page 29 | 미검증 |
| Speed [rpm] | rated_speed | 합성 | REF-2S-02 | pdf_page 29 | 미검증 |
| Number of cylinder | number_of_cylinders | 합성 | REF-4S-02 | pdf_page 10 | 미검증 |
| Cylinder bore mm | bore | 합성 | REF-4S-02 | pdf_page 10 | 미검증 |
| Piston stroke mm | stroke | 합성 | REF-4S-02 | pdf_page 10 | 미검증 |
| Engine (kWm) | rated_power | 합성 | REF-4S-02 | pdf_page 18 | 미검증 |
| Engine Output Range per Turbocharger | applicable_engine_power | 합성 | REF-TC-02 | pdf_page 8 | 미검증 |
| Two-stroke (kW) | applicable_engine_power | 합성 | REF-TC-01 | pdf_page 2 | 미검증 |
| Four-stroke (kW) | applicable_engine_power | 합성 | REF-TC-01 | pdf_page 2 | 미검증 |
| Weight (kg) | reported_weight | 합성 | REF-TC-01 | pdf_page 2 | 미검증 |

## 조건·기준 어휘

- basis.capacity: free_air_delivery, charging_capacity, unknown
- basis.rating: nominal, motor_rated, maximum_capacity, continuous_engine_shaft, MCR, maximum, working, unknown
- basis.pressure: gauge, absolute, not_applicable, unknown
- basis.weight: dry, unknown
- condition.medium: HFO, lubricating_oil
- condition.viscosity_basis: fuel_reference, fluid_reference
- condition.rating_point: R1, R2
- condition.engine_type: two-stroke, four-stroke
- condition.basis: per_turbocharger
- condition.frequency: quantity (frequency)
- condition.temperature: quantity (temperature)
- condition.absolute_pressure: quantity (pressure)
- condition.viscosity: reference_quantity (kinematic_viscosity)

## 단위

| 표기 | pint |
| --- | --- |
| mm | millimeter |
| m | meter |
| kg | kilogram |
| kW | kilowatt |
| bar | bar |
| m3/h | meter**3/hour |
| rpm | revolutions_per_minute |
| l/h | liter/hour |
| Hz | hertz |
| degC | degree_Celsius |
| mbar | millibar |
| cSt | centistokes |
