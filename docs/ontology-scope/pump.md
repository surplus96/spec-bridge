# Pump 범위 정의

상태: 정의표 작성 완료 · 경로: Equipment → FluidMachinery → Pump · origin: synthetic

지원 후보는 원본에서 확인한 원심식과 three-screw 형식이다. 같은 Pump 클래스로 유지하며 형식별 속성을 조건으로 구별한다. 원본의 특정 형식을 모든 펌프에 대한 보편 분류로 확장하지 않는다. 주 제품이 펌프인지 본문·모델 사양의 대상을 확인하고, 분리기 모듈 안의 feed pump 언급만으로 Pump로 매핑하지 않는다.

공통 속성·관계는 [공통 정의](common-attributes.md)를 상속한다. 아래 원본 약칭 P1/P2는 REF-PUMP-01/02, S는 HW-PUMP-001의 기술 본문이다. 모든 원본 관찰은 사용자 의미 검증 대기다.

| ID | 의미·대상 | 자료형 / 정규 단위·차원 | 필수 여부·이유 | 조건·기준 | 근거 |
|---|---|---|---|---|---|
| `pump_type` | 주 펌프의 작동 형식 | enum 후보 / 없음 | 필수(안): 형식에 맞는 사양 검증을 선택 | centrifugal/three_screw 등은 관찰 기반 후보; horizontal·single-stage를 형식 하나로 뭉개지 않음 | P1 p.1, P2 p.2~3; S 1.3/표1 |
| `capacity` | 펌프가 전달하는 유체의 유량 | number의 조건별 관찰 목록 / m3/h·체적유량 | 필수(안): 펌프의 처리 능력을 식별 | rated/nominal/maximum 구별; 주파수·회전수·점도·압력 등 명시된 조건 보존 | P1 p.3~4, P2 p.3; S 표2/5장 |
| `head` | 주 펌프의 토출 성능으로 명시된 양정 | number의 조건별 관찰 목록 / m·길이 | 조건부(안): 원심식 성능점의 비교 정보 | centrifugal로 확인된 경우 요구 후보; 유량과 같은 성능점인지 확인; suction head와 구별 | P2 p.3; S 표3 |
| `medium` | 펌프가 이송하는 유체 | enum/string 후보 / 없음 | 선택: 용도·성능 조건 해석 | oil/seawater 등 원문 또는 조건을 보존; 냉각 매체와 이송 매체 구별 | P1 p.1, P2 p.2~3; S 1.3/1.4/표4 |
| `motor_power` | 펌프 구동 전동기의 명시된 정격 출력 | number / kW·동력 | 선택: 전동기 미포함 공급과 미기재 원본을 허용 | Motor size/프레임 번호를 출력으로 해석하지 않음 | S 표5/3.1; P1 p.5는 Motor size여서 동등 매핑 근거가 아님 |
| `differential_pressure` | 입출구 사이 차압으로 명시된 값 | number의 조건별 관찰 목록 / bar·압력 | 조건부(안)·추가 후보: 스크루식 압력 성능 표현 | 원문이 differential/Δp를 명시해야 함; 밸브 설정과 성능 조건 구별 | P1 p.3~4 |
| `discharge_pressure` | 토출 압력으로 명시된 값 | number의 조건별 관찰 목록 / bar·압력 | 조건부(안)·추가 후보: 차압만 없는 문서도 보존 | pressure_basis gauge/absolute/unknown; 차압과 자동 동등화 금지 | P1 p.3 |

형식별 필수 정책은 **프로젝트 제안**이다. centrifugal은 capacity+head, three_screw는 capacity와 명시된 압력 사양(differential_pressure 또는 discharge_pressure)의 확보를 요구하는 안으로 정리한다. 단품 정격 정보가 없는 제품군 브로슈어는 등록 준비 부족으로 표시하고 실제 장비가 잘못되었다고 단정하지 않는다. 다른 형식·불명 형식의 필수 조건은 자동 추론하지 않는다.

## 합성 후보셋 연결

현재 대표 속성 9개는 공통 maker/model_designation/dimensions/dry_weight와 고유 pump_type/capacity/head/medium/motor_power에 연결된다. 두 신규 압력 후보는 현재 원심식 문서에서 누락 오류가 아니다. 공급 유닛 치수와 중량에 전동기/베이스가 포함되는지 추후 합성 다양화 시 명시한다.

## 미해결 사항

- U-01: 원심식/스크루식 조건부 필수 정책과 다른 형식의 처리.
- U-02: nominal·rated·maximum, 주파수·점도·압력 조건의 공통 자료형.
- U-03: 도면 치수와 건조/일반 중량의 정규 표현.

검증 사례 후보: suction head를 head로 오매핑하지 않기, 주파수가 다른 두 유량을 E5로 오판하지 않기, Motor size를 kW로 읽지 않기. 별도 함정 정답 목록은 만들지 않는다.
