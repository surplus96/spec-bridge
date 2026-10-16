# AirCompressor 범위 정의

상태: 정의표 작성 완료 · 경로: Equipment → FluidMachinery → AirCompressor · origin: synthetic

선박 시동 공기 및 작업/제어 공기용 압축기를 대상 후보로 삼는다. 압축기 제품 사양이 주 대상인지 확인하고, 공급 모터나 냉각 팬 사양으로 클래스를 정하지 않는다. 세부 압축 방식과 냉각 방식은 클래스 추가 없이 표현 후보로 다룬다.

공통 정의를 상속한다. C1/C2는 REF-COMP-01/02, S는 HW-COMP-001이다. 원본 관찰은 사용자 의미 검증 대기다.

| ID | 의미·대상 | 자료형 / 정규 단위·차원 | 필수 여부·이유 | 조건·기준 | 근거 |
|---|---|---|---|---|---|
| `capacity` | 압축기의 공기 공급/충전 능력 | number의 조건별 관찰 목록 / m3/h·체적유량 | 필수(안): 공급 능력을 제품별로 비교 | capacity_basis 필수; FAD와 charging_capacity를 별도 관찰로 유지; 기준 온도·절대압·주파수 보존 | C1 p.10/14, C2 p.5/7; S 표2/3.2 |
| `max_pressure` | 최대 작동 압력이라고 명시된 값 | number / bar·압력 | 선택: 최대라는 의미가 있는 경우만 | gauge/absolute/unknown 보존; nominal/final의 이름만으로 최대압 확정 금지 | S 표3; C1 p.10/C2 p.5는 작동/최종 압력 표기이므로 max 동등성 미검증 |
| `working_pressure` | 명시된 작동/최종 압력 | number의 기준별 관찰 목록 / bar·압력 | 조건부(안)·추가 후보: 압력 사양을 표현 | working 또는 max_pressure 중 명시된 작동 범위 정보 최소 1개 요구 후보; nominal/final 기준 구별 | C1 p.10, C2 p.5 |
| `cooling_type` | 압축기 자체의 냉각 방식 | enum 후보 / 없음 | 선택: 냉각 요구·설치 조건 해석 | air/water 후보; No cooling water만으로 임의 타입 추론하지 않음 | C1 p.8/10/15; S 1.3/표1/표4/3.2 |
| `medium` | 압축/공급하는 작동 매체 | enum/string / 없음 | 선택: 처리 매체 근거 보존 | 본문에서 air를 확인; 명칭만으로 기본값을 조용히 채우지 않음 | C1 p.8, C2 p.5의 압축기 문맥; S 1.3/1.4/표5/3.2 |
| `motor_power` | 구동 전동기의 명시된 정격 출력 | number / kW·동력 | 선택: 설치 구성과 출력 기준이 다를 수 있음 | Shaft power/Installed power/Power consumption을 그대로 motor_power로 합치지 않음 | S 표6/3.1; C1 p.10/11/14, C2 p.5의 출력 용어는 추가 의미 검증 필요 |

등록 필수 후보는 maker/model_designation/capacity 및 명시된 작동 압력 정보다. FAD의 기준 절대압은 capacity의 조건이며 max_pressure의 두 번째 관찰이 아니다. charging_capacity를 FAD로 환산하는 일반 공식은 정의하지 않는다.

## 합성 후보셋 연결

현재 9개 대표 속성을 모두 연결했다. S는 FAD·gauge max_pressure·air cooling·dry 유닛 범위를 본문에 명시하므로 해당 조건으로 비교한다. working_pressure 후보를 채택해도 같은 30 barg 근거를 불필요하게 두 속성의 별도 값으로 복제하지 않는다. 현재 주입 목록의 별칭은 실제 원본 전체에 대한 동등성 규칙이 아니다.

## 미해결 사항

- U-02: FAD/충전 용량과 조건의 목록 표현, working/max의 저장·상호 필수 계약.
- U-04: 전동기 정격·축출력·소비 동력의 분리 또는 확장 보류.
- U-05: bare bar 기준 미상 시 환산·검토 처리.

검증 사례 후보: FAD+charging 두 값 보존, 조건 절대압의 오매핑 방지, 최대·최종 압력 의미 차이 보존.
