# 수기 사양서 골격 & 정답 레코드 형식

작성일: 2026-10-06 · 작업 ID: **W0-SPEC** · 근거: [데이터셋 준비 계획](dataset-plan.md) 3-2·4-3·4-4, [계획서](spec-bridge-project-plan.md) 4-2·4-4

이 문서는 사용자가 직접 쓰는 수기 사양서의 **형식**을 정한다. W0에서는 Pump 1건만 작성하고, 나머지 5개 클래스 골격은 W2의 독립 수기 사양서(4~6건)를 위해 미리 정해 둔다.

**전제와 한계**
- 섹션 구성과 속성 목록은 프로젝트가 정한 형식(`origin: synthetic`)이다. 업계 표준 사양서 양식을 따른다고 주장하지 않는다.
- 속성은 [dataset-plan.md 3-2](dataset-plan.md)의 **후보**다. W1에서 참고 문서와 대조해 확정하면 이 골격도 함께 고친다.
- 이 문서에는 수치를 넣지 않았다. 값은 작성자가 정한다. 그럴듯한 크기를 잡을 때는 참고 문서에서 **값의 자릿수 정도만** 감을 잡고, 원문 수치를 그대로 옮기지 않는다(dataset-plan 6-2).
- 제조사·형식명은 가상으로 만든다. 실제 회사와 겹치지 않는지 검색으로 확인한다.

---

## 1. 작성 규칙 (전 클래스 공통)

| 항목 | 규칙 |
|---|---|
| 언어 | 영문 |
| 분량 | 1~2쪽 |
| 작성 도구 | Word(DOCX)로 쓰고 PDF로도 내보낸다. 정답 레코드의 `pdf_page`는 PDF 기준 |
| 파일 위치 | `data/eval/handwritten/HW-<CLASS>-<NNN>.docx` / `.pdf` / `.answer.yaml` |
| 레이아웃 | 표 1개 이상 + 서술 문단 1개 이상 |
| 반복 기재 | 핵심 속성 1개를 **두 곳**(표 + 서술)에 적는다 → `occurrences` 2개 |
| 표기 변형(V1) | 속성명 별칭 1개 이상 (예: capacity 대신 "Flow rate") |
| 정상 문서 | W0 첫 문서는 **오류를 넣지 않는다**(V1만). 오류 주입(E1~E5)은 W2 문서부터 |
| 금지 | 파일명·주석·본문에 정답이나 주입 유형을 드러내지 않는다 (예: "this is a duplicate" 금지) |

## 2. 공통 문서 골격

모든 클래스가 같은 뼈대를 쓰고, **3장만 클래스별로 다르다.**

```
[Header]   TECHNICAL SPECIFICATION
           Doc. No. / Revision / Date / Issued by (가상 제조사)

1. General
   1.1 Maker
   1.2 Model designation
   1.3 Product description            ← 한 문장. 클래스를 추론하는 단서
   1.4 Application                    ← 용도 (선박 내 어디에 쓰이는가)

2. Main Technical Data                ← 표. 핵심 속성 대부분
   | Item | Value | Unit | Remark |

3. <클래스별 섹션>                     ← 아래 3장 참고

4. Dimensions and Weight
   4.1 Overall dimensions (L × W × H)
   4.2 Dry weight

5. Scope of Supply                    ← 서술 문단. 핵심 속성 1개를 여기서 한 번 더 언급
6. Remarks                            ← 선택. 비고·조건 서술
```

공통 속성(Equipment)의 위치:

| 속성 후보 | 위치 |
|---|---|
| `maker` | 1.1 (+ Header의 Issued by) |
| `model_designation` | 1.2 |
| `dimensions` | 4.1 |
| `dry_weight` | 4.2 |

## 3. 클래스별 골격

표의 "필수(안)"은 W1 확정 전의 제안이다. 정답 레코드의 `required` 판정은 W1 온톨로지를 따른다.

### 3-1. Pump (W0 작성 대상)

```
2. Main Technical Data
   Pump type / Capacity / Head / Medium / Motor power
3. Drive and Construction
   3.1 Driver (motor type, motor power 반복 가능)
   3.2 Construction (서술: 형식, 설치 방향 등)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) | 비고 |
|---|---|---|---|---|
| maker | Equipment | ✅ | — | |
| model_designation | Equipment | ✅ | — | |
| pump_type | Pump | ✅ | 열거형 | 허용값은 W1에서 정함 |
| capacity | Pump | ✅ | m³/h | 별칭 예: "Flow rate" |
| head | Pump | ✅ | m | |
| medium | FluidMachinery | | 문자열 | |
| motor_power | FluidMachinery | | kW | |
| dimensions | Equipment | | mm | |
| dry_weight | Equipment | | kg | |

### 3-2. AirCompressor

```
2. Main Technical Data
   Capacity / Max. pressure / Cooling / Medium / Motor power
3. Drive and Cooling
   3.1 Driver
   3.2 Cooling arrangement (서술)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) |
|---|---|---|---|
| maker, model_designation | Equipment | ✅ | — |
| capacity | AirCompressor | ✅ | m³/h |
| max_pressure | AirCompressor | ✅ | bar |
| cooling_type | AirCompressor | | 열거형 |
| medium | FluidMachinery | | 문자열 |
| motor_power | FluidMachinery | | kW |
| dimensions, dry_weight | Equipment | | mm, kg |

압력은 게이지압(bar g)과 절대압(bar a)이 섞일 수 있다. 정답 레코드에 어느 쪽인지 적는다. 같은 차원이지만 기준이 다른 값을 구분하는 시험이 된다.

### 3-3. Separator

```
2. Main Technical Data
   Application (fuel oil / lube oil) / Rated throughput / Self-cleaning / Motor power
3. Process and Operation
   3.1 Process medium (서술)
   3.2 Sludge discharge / cleaning (서술)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) |
|---|---|---|---|
| maker, model_designation | Equipment | ✅ | — |
| application | Separator | ✅ | 열거형 |
| rated_throughput | Separator | ✅ | l/h |
| self_cleaning | Separator | | bool |
| medium | FluidMachinery | | 문자열 |
| motor_power | FluidMachinery | | kW |
| dimensions, dry_weight | Equipment | | mm, kg |

Pump(m³/h)와 Separator(l/h)는 같은 차원(유량)이다. 단위만 보고 클래스를 판단할 수 없어 매핑 시험이 된다.

### 3-4. TwoStrokeMainEngine

```
2. Main Technical Data
   Number of cylinders / Bore / Stroke / Rated power / Rated speed / Fuel
3. Engine Configuration
   3.1 Fuel operation modes (서술)
   3.2 Turbocharger(s) (형식명만, 관계 has_component 후보)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) |
|---|---|---|---|
| maker, model_designation | Equipment | ✅ | — |
| rated_power | Engine | ✅ | kW |
| rated_speed | Engine | ✅ | rpm |
| number_of_cylinders | Engine | ✅ | 정수 |
| fuel_types | Engine | | 열거형 목록 |
| bore, stroke | TwoStrokeMainEngine | | mm |
| dimensions, dry_weight | Equipment | | mm, kg |

출력은 kW와 bhp를 병기하는 표기가 흔하다. 병기하면 `occurrences` 두 개로 적고 둘 다 같은 정규값이 되는지 확인한다.

### 3-5. FourStrokeEngine

```
2. Main Technical Data
   Application (propulsion / genset) / Number of cylinders / Bore / Stroke / Rated power / Rated speed / Fuel
3. Engine Configuration
   3.1 Application details (서술: 추진용이면 감속기, 발전용이면 발전기 연결)
   3.2 Turbocharger(s)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) |
|---|---|---|---|
| maker, model_designation | Equipment | ✅ | — |
| application | FourStrokeEngine | ✅ | 열거형 |
| rated_power | Engine | ✅ | kW |
| rated_speed | Engine | ✅ | rpm |
| number_of_cylinders | Engine | ✅ | 정수 |
| fuel_types | Engine | | 열거형 목록 |
| bore, stroke | FourStrokeEngine | | mm |
| dimensions, dry_weight | Equipment | | mm, kg |

2행정 주기관과 구별되는 단서는 본문에 자연스럽게 둔다. "four-stroke" 같은 단어를 일부러 빼거나 반복하지 않는다.

### 3-6. Turbocharger

```
2. Main Technical Data
   Turbocharger type / Applicable engine power / Bearing type
3. Application
   3.1 Applicable engines (서술: 2행정·4행정 등)
   3.2 Lubrication / maintenance (서술)
```

| 속성 후보 | 상속 | 필수(안) | 정규 단위(안) |
|---|---|---|---|
| maker, model_designation | Equipment | ✅ | — |
| turbocharger_type | Turbocharger | ✅ | 열거형 |
| applicable_engine_power | Turbocharger | | kW (범위: min/max) |
| bearing_type | Turbocharger | | 열거형 |
| dimensions, dry_weight | Equipment | | mm, kg |

`applicable_engine_power`는 단일 값이 아니라 **범위**다. 정답 레코드에서 `value: {min: , max: }`로 적는다. 엔진 출력(`rated_power`)과 혼동되기 쉬워 매핑·추출 시험이 된다.

---

## 4. 정답 레코드 형식 (`*.answer.yaml`)

사양서 1건당 1개. 평가기만 읽는 파일이다(추출기·프롬프트에 넣지 않는다).

```yaml
schema_version: 1
doc_id: HW-PUMP-001
origin: synthetic                 # 수기 합성 문서
author: <이름>
created_at: 2026-10-xx
files:
  docx: data/eval/handwritten/HW-PUMP-001.docx
  pdf:  data/eval/handwritten/HW-PUMP-001.pdf

expected_class: Pump
class_path: [Equipment, FluidMachinery, Pump]

attributes:
  capacity:
    value: <정규화 값>            # 숫자
    unit: m3/h                    # 정규 단위 (pint 표기)
    expected_status: pass         # pass / fail / unknown
    occurrences:                  # 문서에 나온 모든 위치. 순서 무관
      - raw_text: "<문서에 적힌 그대로, 예: 120 m³/h>"
        label_text: "Flow rate"   # 문서에 적힌 속성명 그대로 (V1 별칭이면 여기 드러남)
        location:
          section: "2"
          table: 1                # 표 안이면 표 번호
          row: 2                  # 표 안이면 행 번호 (머리글 제외, 1부터)
          pdf_page: 1
          printed_page: 1         # 쪽 번호를 인쇄하지 않았으면 null
      - raw_text: "<...>"
        label_text: "rated capacity"  # 서술 안이면 값 바로 앞의 표현
        location:
          section: "5"
          paragraph: 1            # 서술이면 문단 번호
          pdf_page: 2
          printed_page: 2

  head:
    value: <...>
    unit: m
    expected_status: pass
    occurrences: [ ... ]

  pump_type:
    value: <열거값>               # 허용값은 W1 온톨로지 확정 후 맞춤
    unit: null
    expected_status: pass
    occurrences: [ ... ]

  # 문서에 없는 비필수 속성은 적지 않는다.
  # 문서에 없는 필수 속성은 아래 missing_required에 적는다.

missing_required: []              # W0 정상 문서는 빈 목록

relations:
  manufactured_by: "<가상 제조사명>"
  has_component: []               # 엔진 문서에서 과급기를 언급하면 형식명 기입
  variant_of: null

injections:                       # 문서에 의도적으로 넣은 것. W0는 V1만
  - type: V1
    attribute: capacity
    detail: "속성명 별칭 'Flow rate'"

duplicate_of: null                # 기존 등록 목록의 ID (E6/E7일 때만)
notes: null
```

**작성 요령**
- `raw_text`는 공백·기호까지 문서와 똑같이 복사한다. 단위 기호(m³ 대 m3)의 차이도 정규화 시험 대상이다.
- `value`는 정규 단위로 환산한 값이다. 문서가 다른 단위로 적었다면 직접 환산해 적고, 그 사실을 `injections`에 V1으로 남긴다.
- 같은 속성이 두 곳에 **같은 값**으로 나오면 `expected_status: pass`다. **다른 값**이면 E5(문서 내 불일치)이며, W2 문서부터 쓴다.
- 위치는 PDF로 내보낸 뒤 실제 쪽을 확인하고 적는다.

## 5. 단계별 작성 절차 (Pump 예시)

전체 흐름: **참고 문서 관찰 → 값 설계표 작성 → Word 작성 → PDF 내보내기 → 정답 레코드 작성 → 자체 점검.** 예상 소요 시간은 2~3시간이다.

핵심 원칙: **정답(값)을 먼저 정하고, 문서는 그다음에 쓴다.** 문서를 먼저 쓰고 나중에 정답을 거꾸로 뽑으면, 같은 값을 두 곳에 다르게 적는 실수가 정답 레코드에 그대로 들어간다.

### 5-1. 준비 (10분)

1. 폴더를 만든다: `data/eval/handwritten/`
2. 파일 이름을 정한다: `HW-PUMP-001.docx`, `HW-PUMP-001.pdf`, `HW-PUMP-001.answer.yaml`
3. 가상 제조사명과 형식명을 정하고 웹에서 검색한다. 같은 이름의 실제 펌프·선박 기자재 회사가 나오면 바꾼다.
   - 형식명은 영문·숫자·하이픈 조합으로 한다(예: `XX-150` 형태). 실제 제조사의 명명 규칙을 흉내 내지 않는다.

### 5-2. 참고 문서 관찰 (20~30분)

REF-PUMP-01(Alfa Laval ALP), REF-PUMP-02(DESMI)를 열고 **표기 방식만** 메모한다. 수치는 적지 않는다.

| 관찰할 것 | 메모 예시 (형식만) |
|---|---|
| 유량을 무엇이라 부르는가 | "Capacity", "Flow" 등 실제로 쓰인 단어 |
| 유량·양정 단위 표기 | "m³/h"인지 "m3/h"인지, 양정은 "m"인지 "mWC"인지 |
| 사양이 표에 있는가, 문장에 있는가 | 표 / 서술 / 둘 다 |
| 같은 값이 여러 번 나오는가 | 예: 표지 요약 + 상세 표 |

- 메모는 `data/eval/handwritten/HW-PUMP-001.notes.md`에 문서 ID와 `pdf_page`를 붙여 남긴다. W1 동의어 사전과 `variant_catalog`의 재료가 된다.
- 값의 크기는 "이 제품군은 대략 몇 자릿수인가" 정도만 본다. 특정 모델의 수치를 그대로 쓰지 않는다(dataset-plan 6-2).

### 5-3. 값 설계표 작성 (20분)

Word를 열기 전에 아래 표를 먼저 채운다. 이 표가 정답 레코드의 원본이 된다.

| 속성 | 정규값 | 정규 단위 | 문서 표기 1 (위치) | 문서 표기 2 (위치) |
|---|---|---|---|---|
| maker | `<MAKER>` | — | Header "Issued by" | 1.1 |
| model_designation | `<MODEL>` | — | 1.2 | — |
| pump_type | `<TYPE>` | — | 표 1 "Pump type" | 1.3 서술 |
| capacity | `{Q}` | m³/h | 표 1 "Flow rate" `{Q} m³/h` | 5장 서술 "rated capacity of `{Q}` m3/h" |
| head | `{H}` | m | 표 1 "Total head" | — |
| medium | `<MEDIUM>` | — | 표 1 "Medium" | — |
| motor_power | `{P}` | kW | 표 1 "Motor power" | 3.1 서술 |
| dimensions | `{L}×{W}×{Hd}` | mm | 4.1 | — |
| dry_weight | `{M}` | kg | 4.2 | — |

이 설계에는 표기 변형(V1)이 세 개 들어 있다:
- 속성명 별칭: capacity를 "Flow rate"로, head를 "Total head"로 표기
- 단위 기호 차이: 표는 `m³/h`, 서술은 `m3/h`

**값끼리 물리적으로 모순되지 않게 정한다.** 유량·양정·모터 출력은 서로 관련이 있다. 펌프가 유체에 주는 동력은 다음과 같다.

```
P_hyd [kW] = ρ [kg/m³] × g [m/s²] × Q [m³/h] × H [m] / 3 600 000
```

모터 출력 `{P}`는 `P_hyd`보다 커야 한다(효율 손실과 여유분). 가정한 밀도와 효율은 정답 레코드의 `notes`에 적는다. 이 관계를 검증 규칙으로 쓸지는 W1에서 정하고, 지금은 모순만 피한다.

### 5-4. Word 작성 (40~60분)

**Word 사용 규칙** — 파서가 내용을 빠뜨리지 않게 하기 위한 규칙이다.

| 규칙 | 이유 |
|---|---|
| 섹션 번호(1, 1.1 …)는 **직접 타이핑**한다. 자동 번호 매기기를 쓰지 않는다 | 자동 번호는 python-docx의 문단 텍스트에 포함되지 않는다 |
| 표는 Word의 **표 삽입** 기능으로 만든다. 탭·공백으로 열을 맞추지 않는다 | 파서가 표 구조(행·열)를 인식해야 `table`·`row` 위치가 의미를 가진다 |
| 사양 값을 **머리글·바닥글·텍스트 상자·그림**에 넣지 않는다 | 파서가 본문과 따로 처리하거나 아예 읽지 않을 수 있다 |
| Doc. No.와 Issued by는 머리글이 아니라 **본문 첫 줄**에 쓴다 | 위와 같음 |
| 쪽 번호는 바닥글에 넣어도 된다 | `printed_page`의 근거가 된다. 넣지 않으면 `printed_page: null` |
| 수식 편집기를 쓰지 않는다. `m³`는 일반 텍스트(위첨자 또는 ³ 문자)로 쓴다 | 수식 객체는 텍스트로 추출되지 않을 수 있다 |

**본문 예시** — 꺾쇠·중괄호 부분을 5-3의 값으로 바꾼다. 문장은 자유롭게 바꿔도 되지만, 5-3에서 정한 표기는 그대로 지킨다.

```
TECHNICAL SPECIFICATION
Doc. No.: <DOCNO>    Revision: A    Date: 2026-10-xx
Issued by: <MAKER>

1. General
1.1 Maker: <MAKER>
1.2 Model designation: <MODEL>
1.3 Product description: <TYPE> pump for <MEDIUM> service on board ships.
1.4 Application: <선박 내 용도 한 줄, 예: cooling water system>

2. Main Technical Data
Table 1 – Main technical data
| Item        | Value    | Unit  | Remark           |
|-------------|----------|-------|------------------|
| Pump type   | <TYPE>   | –     |                  |
| Flow rate   | {Q}      | m³/h  | at rated point   |
| Total head  | {H}      | m     | at rated point   |
| Medium      | <MEDIUM> | –     |                  |
| Motor power | {P}      | kW    |                  |

3. Drive and Construction
3.1 Driver: The pump is driven by a flange-mounted electric motor rated at {P} kW.
3.2 Construction: <형식·설치 방향 등 서술 1~2문장>

4. Dimensions and Weight
4.1 Overall dimensions (L × W × H): {L} × {W} × {Hd} mm
4.2 Dry weight: {M} kg

5. Scope of Supply
The scope of supply comprises one pump unit with a rated capacity of {Q} m3/h,
complete with electric motor, coupling and base frame.

6. Remarks
<선택. 없으면 섹션 생략>
```

주의할 점:
- 1.3 Product description에 클래스 이름("Pump")이 드러나는 것은 자연스러우니 괜찮다. 다만 "This document is a Pump specification for testing" 같은 메타 문장은 쓰지 않는다.
- 한 셀에 값과 단위를 합쳐 쓰지 않는다(예: "120 m³/h"를 한 칸에). 이 문서에서는 값·단위 열을 분리한다. 합쳐 쓰는 변형은 W2 합성 문서에서 다룬다.

### 5-5. PDF 내보내기와 확인 (10분)

1. Word에서 **파일 → 다른 이름으로 저장 → PDF**를 선택한다. "인쇄 → PDF로 저장"은 텍스트가 깨질 수 있어 피한다.
2. PDF를 열어 확인한다.
   - 본문 글자가 드래그로 **선택되는가**(이미지가 아닌가)
   - 표가 쪽 경계에서 잘리지 않았는가. 잘렸다면 Word에서 줄을 조정하고 다시 내보낸다
   - 몇 쪽인가. 2쪽을 넘으면 문장을 줄인다
3. 이후 Word 파일을 고치면 **반드시 PDF를 다시 내보낸다.** 두 파일이 다르면 정답 레코드의 위치가 틀어진다.

### 5-6. 정답 레코드 작성 (30~40분)

5-3 설계표와 PDF를 나란히 두고 4장의 형식대로 `HW-PUMP-001.answer.yaml`을 채운다.

1. **`value`, `unit`**: 설계표의 정규값과 정규 단위를 적는다.
2. **`raw_text`**: Word가 아니라 **PDF 뷰어에서 복사해 붙인다.** 추출기가 보는 것은 PDF의 텍스트다. Word의 `m³`가 PDF에서 다른 문자로 바뀌는 경우가 있는데, PDF에서 복사해야 그 차이가 정답에 반영된다.
3. **`label_text`**: 그 값 옆에 적힌 속성명(표의 Item 열, 또는 문장 속 표현)을 그대로 적는다. 서술 안이면 값 바로 앞의 표현을 적는다(예: "rated capacity").
4. **`location`**:
   - 표 안: `section`, `table`(Table 1이면 1), `row`(머리글 제외, 1부터), `pdf_page`, `printed_page`
   - 서술: `section`(예: "3.1"), `paragraph`(그 섹션 안에서 1부터), `pdf_page`, `printed_page`
5. **`dimensions`**: 값이 세 개이므로 이렇게 적는다.
   ```yaml
   dimensions:
     value: {length: <L>, width: <W>, height: <Hd>}
     unit: mm
     expected_status: pass
     occurrences:
       - raw_text: "<PDF에서 복사>"
         label_text: "Overall dimensions (L × W × H)"
         location: {section: "4.1", paragraph: 1, pdf_page: <n>, printed_page: <n>}
   ```
6. **`injections`**: 5-3에서 넣은 V1 세 개를 모두 적는다.
   ```yaml
   injections:
     - {type: V1, attribute: capacity, detail: "속성명 별칭 'Flow rate'"}
     - {type: V1, attribute: head, detail: "속성명 별칭 'Total head'"}
     - {type: V1, attribute: capacity, detail: "단위 기호 차이: 표 'm³/h', 5장 'm3/h'"}
   ```
7. **`notes`**: 5-3에서 가정한 밀도·효율과, 참고 문서에서 표기 방식만 참고했다는 사실을 적는다.

### 5-7. 자체 점검 (10분)

- [ ] 설계표의 모든 속성이 정답 레코드에 있다 (문서에 없는 비필수 속성 제외)
- [ ] capacity와 motor_power의 `occurrences`가 각각 2개이고, 두 위치의 값이 같다
- [ ] 모든 `raw_text`를 PDF 뷰어 검색(`Cmd+F`)으로 찾을 수 있다
- [ ] Word와 PDF의 내용이 같다 (마지막 수정 후 다시 내보냄)
- [ ] 문서 본문 어디에도 "test", "injection", "V1" 같은 메타 표현이 없다

점검이 끝나면 알려준다. Claude가 YAML 문법 검사와 `raw_text`·`pdf_page` 자동 대조를 실행한다.

## 6. W0 완료 기준

- [ ] `HW-PUMP-001.docx` / `.pdf` 작성 (1~2쪽, 표 1개 이상, 서술 1개 이상)
- [ ] 핵심 속성 1개 이상이 두 곳에 같은 값으로 나옴
- [ ] 속성명 별칭 1개 이상
- [ ] `HW-PUMP-001.answer.yaml`의 모든 속성에 `occurrences`와 위치가 있음
- [ ] 가상 제조사명이 실제 회사와 겹치지 않음 (검색 확인)

작성 후 YAML 문법 검사와 "정답 레코드의 `raw_text`가 PDF 텍스트에 실제로 있는가"는 제가 자동으로 대조할 수 있다(W0-VERIFY와 같은 방식).
