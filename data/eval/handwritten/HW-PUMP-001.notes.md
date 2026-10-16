# HW-PUMP-001 작성 전 관찰 메모

작성: 2026-10-06 (Claude, pdfplumber 텍스트·표 추출 기반) · W0 관찰 기록(모델 입력에서 제외) · 절차: [spec-sheet-skeletons.md 5-2](../../../docs/spec-sheet-skeletons.md)
대상: **REF-PUMP-01** — Alfa Laval ALP three-screw pump leaflet (200008926-2-EN-GB, 6쪽)
REF-PUMP-02 (DESMI) 관찰은 [reference-observations.md](reference-observations.md) Pump 절에 있다.

**규칙** (dataset-plan 6-2): 표기 형식과 위치만 기록한다. 원문 수치는 옮기지 않고 `n`, `n,nnn` 같은 패턴으로 표시한다. 형식명도 패턴으로만 적는다.

---

## 1. 문서 구성

| pdf_page | 내용 | 레이아웃 |
|---|---|---|
| 1 | 제품 소개, Applications, Design, Benefits | **2단 서술 + 글머리표** |
| 2 | Design features (그림 2개 + 설명 글상자) | 그림 + 주변 설명 글상자 |
| 3 | Type code, Operating data, Technical data, Materials, Motors, Port connections | 키–값 줄 나열 + 작은 표 여러 개 |
| 4 | Capacity tables (50 Hz / 60 Hz) | **다단 머리글 대형 행렬 표** |
| 5 | Dimensions | **병합 셀 표** + 각주 |
| 6 | 저작권 고지, 문서 코드 | 바닥글 |

사양 수치는 3~5쪽에만 있다. 1~2쪽은 서술이다.

## 2. 속성별 표기 관찰

| 우리 속성(후보) | 문서에서 쓰인 이름 | 단위 표기 | 위치 | 관찰 |
|---|---|---|---|---|
| capacity | "capacity" (서술), "Capacity tables" (제목), "Q" (표 머리글), "nominal flow rate" (형식 코드 설명) | `[l/hour]`, `l/min` | p.1, p.3, p.4 | **한 문서 안에 유량 이름 4가지, 단위 2가지.** 우리 정규 단위(m³/h)는 쓰이지 않음 |
| head | **없음** | — | — | 스크루 펌프 문서에는 양정 대신 압력이 쓰임: "Max. discharge pressure", "Max. differential pressure", "Δp". 흡입 쪽만 "manometric suction head … `mWG`" |
| (압력) | "Max. inlet pressure", "Max. discharge pressure", "Max. differential pressure (bar)", "Δp" | `bar`, `(bar)`, `± n%` | p.3, p.4 | 단위가 값 뒤에 붙거나 이름 뒤 괄호에 들어감 |
| (회전수) | "RPM" (표 머리글), "rpm" (본문), "Max rotation speed [min –1] (min-1)" | `RPM`, `rpm`, `min-1`, `[min –1]` | p.3, p.4 | **같은 단위를 4가지로 표기.** 같은 줄에 두 표기를 병기한 곳도 있음 |
| motor_power | **없음** | — | — | 모터는 출력(kW)이 아니라 "Motor size"(IEC 프레임), 극수, 효율 등급, 보호 등급으로만 표기 |
| medium | "mineral oil", "fuel oil", "lubricating oil", "pumped liquid" | — | p.1, p.2 | 표 항목이 아니라 서술 안에만 나옴 |
| pump_type | "Three-screw pump" | — | p.1 제목 | 제목에만 나옴 |
| model_designation | 형식 코드, "ALP nnnn"(공백), 형식 코드 예시(하이픈), "nnnn"(크기 번호만) | — | p.3, p.4, p.5 | **한 문서 안에 형식명 표기 3가지.** 형식 코드는 위치(Pos.)별 의미를 정한 구조형 코드 |
| dimensions | "Dimensions", 문자 기호 열(LG, L5, L4, LP, LL …) | `[mm]` (머리글) | p.5 | 전체 L×W×H가 아니라 도면 기호별 치수. 도면 없이는 의미를 알 수 없음 |
| dry_weight | **없음** | — | — | |
| (점도) | "viscosity" | `cSt`, `[mm²/s]` | p.3, p.4 | **같은 물리량을 두 단위 이름으로 표기** (두 단위는 크기가 같은 단위) |
| (온도) | "Temperature range °C" | `°C` | p.3 | 단위가 항목 이름에 붙어 있음 |

## 3. 형식·기호 관찰

| 항목 | 관찰 (패턴) | 위치 |
|---|---|---|
| 천 단위 구분 | 쉼표: `n,nnn`, `nn,nnn` | p.3~5 |
| 소수점 | 마침표: `n.n` | p.3, p.5 |
| 범위 | `n ÷ n,nnn`, `- nn °C to nnn °C`, `ALP nnnn – ALP nnnn` (en dash) | p.3 |
| 두 조건 병기 | `n,nnn / n,nnn rpm @ 50 / 60 Hz` (슬래시 + @) | p.3 |
| 해당 없음 | `–` (en dash) | p.5 |
| 값 미정 | `*` + 각주 "Depends on specific motor model." | p.5 |
| 예외 | `**` + 각주 | p.5 |
| 여러 값 한 셀 | 병합 셀 안에 줄바꿈으로 여러 행 값이 들어감 | p.5 |
| 원문 오타 | "Alfa Lalaval", "pumpsare", "liquis" | p.2 |

## 4. 파서 관점 관찰 (W1~W2 참고)

1. **2단 레이아웃은 텍스트가 섞인다.** p.1을 추출하면 왼쪽과 오른쪽 단의 줄이 번갈아 나온다. 문장 단위 추출에서 오류의 원인이 된다.
2. **p.3의 키–값 영역이 하나의 큰 표로 잡힌다.** 첫 셀에 여러 항목이 줄바꿈으로 뭉쳐 들어가고, 나머지 셀은 비어 있다. 표 구조를 믿고 행 단위로 읽으면 틀린다.
3. **p.4는 머리글이 3단이다.** (주파수·Δp) → (기계식·자석식 그룹) → (점도별 열). 셀 하나의 의미를 알려면 머리글 3단과 행 머리(크기, RPM)를 모두 붙여야 한다.
4. **p.5는 병합 셀에 여러 행이 줄바꿈으로 들어간다.** 행 단위로 다시 쪼개야 한다.
5. 같은 그림 설명 문구가 p.2에 두 번 반복된다(그림 1, 그림 2). 중복 추출로 같은 값이 두 번 잡힐 수 있다.

## 5. HW-PUMP-001 설계에 준 영향

| # | 관찰 | 반영 (HW-PUMP-001.spec.md) |
|---|---|---|
| 1 | 스크루(용적식) 펌프 문서에는 head가 없고 압력이 쓰인다 | pump_type을 원심식으로 정해 head를 쓰는 문서로 만들었다. 형식별 필수 속성 문제는 W1 이슈 |
| 2 | 유량 단위로 `l/hour`, `l/min`이 쓰임 | 정규 단위 m³/h 유지. `l/h`, `l/min`은 W2 V1 단위 변형 후보 |
| 3 | 회전수 표기 4가지 | 펌프 속성에 회전수가 없어 넣지 않음. 엔진 클래스 V1 후보(HW-2S-001에 `r/min` 반영) |
| 4 | motor_power, dry_weight가 문서에 없음 | 둘 다 골격상 비필수 후보로 둠; 실제 필수 여부는 W1 온톨로지 확정 전 |
| 5 | 형식명이 한 문서 안에 3가지로 표기됨 | 1.2절 `BMH-150/30` ↔ 5장 `BMH 150/30` 변형 반영. 형식 코드 구조는 가상으로 새로 설계 |
| 6 | 치수가 도면 기호로 나옴 | 4.1 L × W × H 유지. 도면 기호 치수의 추출 대상 여부는 W1 결정 |
| 7 | 단위 위치가 다양함 | "Unit 열 분리" 한 가지만 사용. 나머지는 W2 레이아웃 변형 후보 |

## 6. W1로 넘길 온톨로지 이슈

1. **Pump 속성이 펌프 형식에 따라 달라진다.** 원심식은 head, 용적식(스크루 등)은 차압·토출 압력. 선택지:
   - Pump를 하위 클래스로 나누기 (클래스 수 증가, D-002 범위 재검토 필요)
   - head와 differential_pressure를 모두 두고 pump_type에 따른 조건부 필수로 하기
   - head를 비필수로 내리기
   - 이 구분은 참고 문서 2건(REF-PUMP-01 스크루, REF-PUMP-02 원심)의 관찰에서 나온 것이다. 일반 규칙으로 쓰려면 원문 근거를 더 확인해야 한다 **[미검증]**.
2. **같은 크기의 단위 별칭:** `cSt` ↔ `mm²/s`, `rpm` ↔ `min-1`. pint가 이 표기들을 인식하는지 W1에서 확인한다.
3. **형식명 정규화:** 공백·하이픈·접두어 생략(크기 번호만) 변형. 자연키(maker + 정규화 형식명)를 설계할 때 반영한다.
4. **모터 사양 표현:** 출력(kW) 대신 프레임 크기·극수로 표기하는 문서가 있다. `motor_power`만으로 충분한지 W1에서 정한다.
