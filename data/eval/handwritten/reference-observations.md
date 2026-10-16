# 참고 문서 표기 관찰 (전 클래스)

작성: 2026-10-06 (Claude, pypdf/pdfplumber 텍스트 추출 + 검색) · 대상: manifest의 REF 12건
페이지 보정: 2026-10-06 (Codex, 원본 재대조). 아래 위치는 PDF 페이지이며 인쇄 쪽 번호와 구별한다. 합성 본문·정답의 최신 정책은 [SCORING-POLICY.md](SCORING-POLICY.md)를 따른다.

Pump(REF-PUMP-01)의 상세 관찰은 [HW-PUMP-001.notes.md](HW-PUMP-001.notes.md)에 있다.

**규칙** (dataset-plan 6-2): 표기 형식과 위치만 남긴다. 원문 수치는 옮기지 않고 패턴(`n,nnn`)으로 적는다. 아래 "자릿수 감"은 합성값의 크기를 정하기 위한 대략적 범위이며, 특정 모델의 값이 아니다.

---

## Pump — REF-PUMP-01 (스크루), REF-PUMP-02 (원심, DESMI)

| 관찰 | 위치 |
|---|---|
| 원심 펌프 문서는 "Flow rate - 50 Hz", "Flow rate - 60 Hz"처럼 **주파수별로 값을 나눠** 적고, "Head"를 쓴다 | REF-PUMP-02 PDF p.3~6 |
| 유량 단위 `m3/h`, `m³/h`, `M3/H`, `m³ /H` 혼재. 미국 단위 `US gpm`을 괄호로 병기 | REF-PUMP-02 p.1~6 |
| 양정 단위 `m`, `mWC`(서술), `ft`(괄호 병기), 머리글 "TOTAL HEAD" | REF-PUMP-02 p.1, p.6~ |
| 값 앞에 "Up to"(최대값 표기) | REF-PUMP-02 전반 |
| 이 스크루 펌프 문서는 원심식의 토출 양정 대신 압력(Δp, discharge pressure)을 쓴다. 흡입 head 표기는 별도로 있음 | REF-PUMP-01 p.3~4 |

자릿수 감: 원심식 선박 펌프는 유량 수십~수천 m³/h, 양정 수십~백수십 m 범위의 제품군이 소개됨.

## AirCompressor — REF-COMP-01 (Atlas Copco), REF-COMP-02 (Sauer)

| 관찰 | 위치 |
|---|---|
| 용량이 **두 가지 개념**으로 나뉨: "FAD*"(free air delivery)와 "Charging capacity**" | REF-COMP-01 PDF p.10~11, p.14~15 |
| 압력 표기 `bar`, `barg`(게이지), `mbara`(절대, 기준 조건) | REF-COMP-02 p.2~ |
| "Nominal working pressure", "final pressure" — 문서별 압력 항목 이름. 정격·상한·압력 기준의 동등성은 별도 확인 필요 | REF-COMP-01, -02 |
| 출력 `kW`와 `hp` 병기 (예: "n-n kW / n-n hp") | REF-COMP-01 목차 |
| 치수 머리글 `L (mm) W (mm) H (mm)`, 중량 `kg`, 일부 `lbs` | REF-COMP-01 PDF p.10~11, p.14~15 |
| 성능값에 기준 조건 각주: 공차(%), 기준 온도, 기준 기압 | REF-COMP-02 각 표 아래 |

자릿수 감: 선박 시동 공기 압축기는 30 bar급, 용량 수십~수백 m³/h, 모터 수십 kW급.

## Separator — REF-SEP-01 (Alfa Laval), REF-SEP-02 (GEA)

| 관찰 | 위치 |
|---|---|
| 처리량이 **유종·점도 조건별**로 다름: "Max. capacity for IF 380 l/h", "… IF 700 l/h" | REF-SEP-02 p.7 |
| "Max. recommended capacity, l/h on lubricating oils for trunk piston engines" — 조건이 이름 안에 들어감 | REF-SEP-01 p.4 |
| 치수 순서 `Size (H1 x W1 x W2)` — **높이가 먼저** | REF-SEP-01 p.5 |
| 중량 이름 "Net weight (kg)" | REF-SEP-01 p.5 |
| 바닥 면적 "Footprint (length x wide) cm" — 단위 `cm`, 원문 오타 "wide" | REF-SEP-02 p.7 |
| 전압·주파수 범위 `nnn - nnn`, `50 - 60` | REF-SEP-02 p.7 |
| 점도 기준 "cSt at 50°C" | REF-SEP-01 p.1 |

자릿수 감: 선박 연료유 청정기 처리량은 수백~수만 l/h 범위의 제품군.

## TwoStrokeMainEngine — REF-2S-01 (Everllence G80), REF-2S-02 (WinGD X62DF)

| 관찰 | 위치 |
|---|---|
| 정격 출력의 **정의가 문서마다 다름**: "MCR", "SMCR"(specified MCR), "NMCR", "CMCR"(contract MCR), 정격점 "L1~L4" / "R1~R4" | REF-2S-01 PDF p.23, p.51~52; REF-2S-02 PDF p.29, p.39 |
| 회전수 `rpm`, `r/min` | REF-2S-01 (r/min), REF-2S-02 (rpm) |
| "Bore x stroke: nnn x n,nnn [mm]" — **두 속성을 한 줄에** | REF-2S-02 PDF p.29 |
| 실린더당 출력 "kW/cyl" — 엔진 전체 출력과 구분 필요 | REF-2S-02 p.26 |
| 건조 중량 "Dry weight [t]" — 단위 톤 | REF-2S-02 PDF p.30 |
| 단위를 대괄호로: `[mm]`, `[kW]`, `[rpm]`, `[t]` | REF-2S-02 전반 |
| 실린더 수 "Number of cylinders: n to n" — 제품군 범위 | REF-2S-02 p.26 |

자릿수 감: 대형 2행정 주기관은 보어 수백 mm, 행정 수천 mm, 실린더당 수천 kW, 회전수 백 rpm 안팎.

## FourStrokeEngine — REF-4S-01 (Everllence V28/33D), REF-4S-02 (HiMSEN H17/28)

| 관찰 | 위치 |
|---|---|
| "Cylinder bore **in cm**" (형식명 해석 설명), 같은 문서의 데이터 표는 `mm` | REF-4S-02 PDF p.8(형식명 cm), p.10(사양표 mm) |
| "Rated output at n rpm / 60 Hz, n rpm / 50 Hz" — 발전용은 **회전수와 주파수가 짝** | REF-4S-02 PDF p.18 |
| "Rated power : nnn kW / cylinder at nnn rpm", "nnn kW/cyl." — 실린더당 출력 표기 | REF-4S-01, -02 |
| "Engine MCR", "Normal rating", "Higher rating", "ICN", "ICFN" — 정격 종류가 여러 개 | REF-4S-01 PDF p.33~37; REF-4S-02 PDF p.10, p.18~19 |
| "Dry weight (**ton**)" | REF-4S-02 PDF p.15 |
| 같은 문서에 MAN / Everllence 표기 혼재 (리브랜딩 안내) | REF-4S-01 p.1 |

자릿수 감: 중속 4행정 발전용 엔진은 보어 백~수백 mm, 실린더당 백~수백 kW, 900/1000 rpm(60/50 Hz) 등.

## Turbocharger — REF-TC-01 (Everllence TCA), REF-TC-02 (MHI MET)

| 관찰 | 위치 |
|---|---|
| 적용 엔진 출력을 **2행정·4행정 열로 나눠** 적음: "Supercharged Engine Output Two-stroke (kW) / Four-stroke (kW)" | REF-TC-01 p.2 |
| 적용 출력을 **범위**로: "Engine Output Range per Turbocharger kW n,nnn - n,nnn" | REF-TC-02 p.8 |
| "Max. permissible Speed (rpm)" — **과급기 회전수**. 엔진 회전수와 혼동 위험 | REF-TC-01 p.2 |
| 치수 `L (mm) B (mm) H (mm)`, "Length / **Breadth** / Height" — W 대신 B | REF-TC-01, -02 |
| 온도 단위 `℃`(전각 기호) | REF-TC-02 p.8 |
| 제조사 약칭 "MAN ES" (MAN Energy Solutions) | REF-TC-02 p.7~8 |
| 원문 오타 "Turbochaegers", 일본어 각주 혼재 | REF-TC-02 p.7~8 |
| "Max. Pressure Ratio" — 무차원 값, 단위 `-` | REF-TC-02 p.8 |

자릿수 감: 대형 과급기 1대당 적용 엔진 출력 수천~수만 kW, 중량 수 톤.

---

## 답안지 설계에 반영한 것

| 관찰 | 반영한 문서 | 방법 |
|---|---|---|
| 유량 `m³/h`·`m3/h` 혼재 | HW-PUMP-001 | 표와 서술에서 다른 기호 사용 |
| 형식명 공백·하이픈 변형 | HW-PUMP-001 | 1.2절과 5장에서 다르게 표기 |
| `barg` / `bar g` | HW-COMP-001 | 표와 서술에서 다른 표기 |
| 처리량의 조건부 값 | HW-SEP-001 | 점도 조건별 2행 |
| 치수 높이 우선 순서 | HW-SEP-001 | `H × L × W` |
| `kW`·`BHP` 병기, `rpm`·`r/min` | HW-2S-001 | 서술에서 다른 단위. 합성 본문은 기계식 마력을 명시하며, REF-2S-01 PDF p.23의 metric horsepower 정의와 구별 |
| 건조 중량 `t` / `ton` | HW-2S-001, HW-4S-001 | 톤 단위로 표기 |
| 보어 `cm` | HW-4S-001 | 원본 형식명 설명의 단위를 합성 사양 표에 적용; 원본 사양 표 자체는 mm |
| 실린더당 출력 | HW-4S-001 | 비고에 "kW/cyl."; 엔진 전체 출력과 구별할 정상 기술 정보 |
| 과급기 회전수 | HW-TC-001 | "Max. permissible speed"; 과급기 로터의 정상 기술 정보 |
| 치수 `L × B × H` | HW-TC-001 | B 표기 |
