# spec-bridge 데이터셋 준비 계획

작성일: 2026-10-05 · 근거: [계획서 v2](spec-bridge-project-plan.md) 4장, [결정 D-002](decisions.md)

작업 ID: **W0-DATA** — 공개 자료로 얻을 수 있는 것과 합성해야 하는 것을 나누고, 온톨로지 범위(D-002)를 확정한다.

이 문서는 **준비 계획**이다. 자료 다운로드, 데이터 생성, 온톨로지 작성은 하지 않았다. 아래 출처는 2026-10-05 웹 검색으로 **접근 경로만 확인**한 것이며, 내용·판본 대조와 `verified_by` 작성은 W1에서 사용자가 한다(H3).

---

## 1. 원칙

1. **과제 입력은 가상 데이터다.** 과제 정의서의 입력 데이터는 "가상 제품 사양서 30~50건"이다. 합성 데이터는 의도된 입력이고, 공개 자료는 합성 데이터를 사실적으로 만드는 **참고 재료**다.
2. **공개 문서는 커밋하지 않는다.** 출처 URL·취득일·해시만 manifest로 남긴다.
3. **실제 제조사명에 합성 수치를 붙이지 않는다.** 합성 사양서와 기존 등록 목록은 가상 제조사·가상 형식명을 쓴다. 실제 제조사 문서에서 얻은 것은 속성 구성과 표기 방식이다.
4. **공개 문서가 확인된 클래스만 온톨로지에 넣는다.** 클래스당 제조사 2곳 이상을 기준으로 한다(표기 다양성 확보).

---

## 2. 사전 확인 결과 (2026-10-05)

### 2-1. 6번째 클래스 후보

| 후보 | 확인 결과 | 판단 |
|---|---|---|
| **유청정기(원심 분리기)** | Alfa Laval 공식 리플릿([P 626/636/646](https://www.alfalaval.com/globalassets/documents/products/separation/centrifugal-separators/separators/s-and-p-flex/product_leaflet_p_626_636_646_separator_and_system_-product-leaflets_en.pdf)), GEA 공식 브로슈어([GEA marine Separator](https://www.gea.com/assets/322211/)) | **채택** — 공식 출처 2개 제조사. 처음 찾은 GEA OSE 문서는 발전소용이라 교체(4-2) |
| 열교환기 | Alfa Laval 공식 리플릿([T25](https://www.alfalaval.com/globalassets/documents/products/heat-transfer/plate-heat-exchangers/gasketed-plate-and-frame-heat-exchangers/industrial/t25_product-leaflet_en.pdf))만 확인, 두 번째 제조사 미확인 | 보류 (확장 후보) |
| 보일러 | 이번에 조사하지 않음 | 보류 |

### 2-2. 두 번째 제조사

| 클래스 | 기존 | 추가 확인 |
|---|---|---|
| 과급기 | Accelleron TPL (제3자 카탈로그 사이트) | **Everllence TCA 공식 브로슈어** ([everllence.com](https://www.everllence.com/docs/default-source/marine-documents/turbocharger/evr-000073en_l3_tca_preview.pdf?sfvrsn=ec468fb7_3)). 참고: Mitsubishi MET는 제3자 사이트에서만 확인 |
| 펌프 | Alfa Laval ALP (공식) | **DESMI 공식 카탈로그** ([Marine & Offshore Pump Solutions](https://www.desmi.com/media/5mwm24kq/desmi-marine-pump-solutions-web.pdf)). 참고: Shinko는 제3자 사이트에서만 확인 |

### 2-3. DNV Gmod 데이터 이용 조건

- [vista-sdk 저장소](https://github.com/dnv-opensource/vista-sdk)는 **MIT License, "Copyright (c) 2022 DNV"**. Gmod·Codebook 데이터 파일(`resources/gmod-vis-*.json.gz`, VIS 3-4a~3-11a)이 같은 저장소에 들어 있다.
- 데이터 파일에만 적용되는 별도 약관은 **찾지 못했다**(저장소 루트, resources 디렉터리, VIS 문서 페이지 확인).
- **사용 방침**: 우리 클래스에 Gmod 제품 유형 코드를 `external_ref`로 **참조만** 하고, 출처와 MIT 고지를 정의서에 표기한다. Gmod 데이터 파일 자체는 저장소에 재배포하지 않는다. 별도 약관 부재는 "찾지 못함"이지 "없음의 확인"이 아니다. 공개(W4) 전에 사용자가 재확인한다.

---

## 3. 확정 범위 (D-002)

### 3-1. 클래스 계층

```
Equipment
├── Engine
│   ├── TwoStrokeMainEngine      (2행정 주기관)
│   └── FourStrokeEngine         (4행정 엔진: 발전기·추진, application 속성으로 구분)
├── FluidMachinery
│   ├── Pump                     (펌프)
│   ├── AirCompressor            (공기압축기)
│   └── Separator                (유청정기·원심 분리기)
└── EngineComponent
    └── Turbocharger             (과급기)
```

- 말단 클래스 6개, 중간 클래스 3개, 계층 2단. 클래스 구조는 프로젝트가 정한 **간이 분류**(`origin: synthetic`)이며, 업계 표준 분류를 따른다고 주장하지 않는다.
- Gmod 코드 매핑은 W1에서 데이터 파일을 직접 조회해 채운다. 기억으로 코드를 적지 않는다.

**매핑 평가용으로 의도한 혼동 쌍**

| 쌍 | 혼동 이유 |
|---|---|
| TwoStrokeMainEngine ↔ FourStrokeEngine | 둘 다 엔진, 출력·회전수·실린더 속성 공유 |
| Pump ↔ Separator | 둘 다 유량(용량) 속성, 단위 체계가 다를 수 있음 |
| Turbocharger ↔ Engine 계열 | 과급기 문서에 적용 엔진 출력이 등장 |
| Pump ↔ AirCompressor | 둘 다 회전기계, 압력·모터 출력 속성 |

### 3-2. 속성·관계 규모

| 항목 | 범위 |
|---|---|
| 클래스당 속성 | 8~12개 (공통 4 + 중간 클래스 1~3 + 고유 3~6) |
| 고유 속성 정의 총수 | 약 45~55개 |
| 필수 속성 | 클래스당 4~6개 |
| 동의어 사전 | 150~250개 항목 (속성명 별칭 + 값 별칭) |
| 관계 | `has_component`, `manufactured_by`, `variant_of` 3종 + `external_ref`(Gmod) |

**속성 후보** — 일반 공학 개념 수준의 후보이며, W1에서 참고 문서에 실제로 등장하는지 확인한 뒤 확정한다. 허용 범위 값은 넣지 않는다.

| 위치 | 후보 |
|---|---|
| Equipment (공통) | maker, model_designation, dry_weight, dimensions |
| Engine | rated_power, rated_speed, number_of_cylinders, fuel_types |
| TwoStrokeMainEngine | bore, stroke, (그 외 참고 문서 확인 후) |
| FourStrokeEngine | application(propulsion / genset), bore, stroke |
| FluidMachinery | motor_power, medium |
| Pump | capacity, head, pump_type |
| AirCompressor | capacity, max_pressure, cooling_type |
| Separator | rated_throughput, application(fuel oil / lube oil), self_cleaning |
| Turbocharger | turbocharger_type, applicable_engine_power, bearing_type |

---

## 4. 데이터 구성

### 4-1. 층 ① 분류 참조

| 자료 | 용도 | 저장 |
|---|---|---|
| DNV Gmod (vista-sdk) | 클래스 이름·경계 참고, `external_ref` | 코드와 출처만 기록 |
| SFI 대분류 | 문서에서 배경 설명용 | 저장하지 않음 |

### 4-2. 층 ② 참고 문서 (커밋하지 않음)

**선박 용도 확인 (2026-10-05)**: 각 PDF를 내려받아 첫 페이지의 용도 문구를 직접 확인했다. 원본은 확인 후 삭제했다.

| ID | 클래스 | 문서 | 출처 | 선박 용도 확인 근거 |
|---|---|---|---|---|
| REF-2S-01 | TwoStrokeMainEngine | [Everllence G80ME-C10.5-GI Project Guide](https://www.everllence.com/applications/projectguides/2stroke/content/printed/G80ME-C10_5-GI.pdf) | 공식 | 착수 리서치 4.4에서 확인. 약 35MB로 이번에는 내려받다 시간 초과 |
| REF-2S-02 | TwoStrokeMainEngine | [WinGD X62DF Marine Installation Manual, Issue 2021-08](https://wingd.com/media/y4eijz3k/mim_wingd_x62df_20210830.pdf) | 공식 | 표지 "Marine Installation Manual X62DF". 기존 X62DF-S2.0 링크는 404라 교체 |
| REF-4S-01 | FourStrokeEngine | [Everllence V28/33D STC Project Guide](https://www.everllence.com/applications/projectguides/4stroke/Propulsion/PG_P-II_V2833D%20STC.pdf) | 공식 | 표지 "Project Guide – Marine Four-stroke diesel engine", Revision 06.2025 |
| REF-4S-02 | FourStrokeEngine | [HiMSEN H17/28 Project Guide for Marine](https://www.maritimeinformed.com/datasheets/hyundai-heavy-industries-5h17-28m-prime-mover/co-1623926422-ga/h1728-project-guide-for-marine-dec-2022.pdf) | 제3자 | **미확인**: 자동 요청이 403으로 거부됨. 파일명에 "for marine". 브라우저로 받아 확인 필요 |
| REF-PUMP-01 | Pump | [Alfa Laval ALP three-screw pump](https://www.alfalaval.com/globalassets/documents/products/fluid-handling/pumps/three-screw-pumps/product_leaflet_alp_three-screw_pumps.pdf) | 공식 | "specific focus on marine and industrial applications", 선상 연료유 이송 |
| REF-PUMP-02 | Pump | [DESMI Marine & Offshore Pump Solutions](https://www.desmi.com/media/5mwm24kq/desmi-marine-pump-solutions-web.pdf) | 공식 | 냉각·밸러스트·소화·빌지 펌프 |
| REF-COMP-01 | AirCompressor | [Atlas Copco Marine Air Solutions](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/industrial-air/documents/brochures/air-compressors/marine-compressors/Marine_solutions.pdf) | 공식 | 목차에 "Air-cooled Starting Air Compressors (30 bar)" |
| REF-COMP-02 | AirCompressor | [Sauer Compressors for Commercial Shipping (2025)](https://www.sauercompressors.com/assets/Downloads/Sauer_Commercial_shipping_global_en_2025.pdf) | 공식 | 상선용 시동·작업 공기 압축기. 기존 Naval Marine 브로슈어는 **잠수함·전투함용 고압(최대 500 bar) 장비**라 교체 |
| REF-SEP-01 | Separator | [Alfa Laval P separators 626/636/646](https://www.alfalaval.com/globalassets/documents/products/separation/centrifugal-separators/separators/s-and-p-flex/product_leaflet_p_626_636_646_separator_and_system_-product-leaflets_en.pdf) | 공식 | 크로스헤드·트렁크 피스톤 엔진의 윤활유, ISO 8217 연료 청정 |
| REF-SEP-02 | Separator | [GEA marine Separator brochure](https://www.gea.com/assets/322211/) | 공식 | 표지 "GEA MARINE SEPARATOR". 기존 OSE 문서는 **발전소용**("in power plants")이라 교체 |
| REF-TC-01 | Turbocharger | [Everllence TCA](https://www.everllence.com/docs/default-source/marine-documents/turbocharger/evr-000073en_l3_tca_preview.pdf?sfvrsn=ec468fb7_3) | 공식 | 적용 분야 "Marine propulsion, Power generation, Marine GenSets". 2쪽 분량 |
| REF-TC-02 | Turbocharger | [MHI Marine Machinery Company Profile & Product Information (MET Turbochargers, p.7~)](https://www.mhi.com/group/mhimme/company/lib/cp_catalogue_e.pdf) | 공식 | 표지 "MARINE MACHINERY … PRODUCT INFORMATION", p.7~8 MET 터보차저와 형식 표(MET33MBII~MET60MBII). 36쪽, 2024-04 수정. **처음 후보였던 Accelleron TPL-B는 사용자 확인 결과 다운로드 불가(2026-10-05)라 교체** |

- 선박 전용이 아니라 선박·육상 겸용인 문서도 있다(ALP, TCA). 선박용 사양이 들어 있으면 참고 자료로 쓰되, 속성을 수집할 때 육상 전용 항목은 제외한다.
- WinGD 문서는 표지에 복제 금지 고지가 있다. 커밋하지 않는 원칙을 엄격히 지킨다.
- 열교환기 후보로 확인했던 Alfa Laval T25 리플릿은 경로상 산업용(`industrial`)이다. 열교환기를 확장 클래스로 넣게 되면 선박용 문서를 다시 찾는다.

- 제3자 사이트 문서는 공식 출처를 찾으면 대체한다. Scribd 등 업로드 공유 사이트 문서는 쓰지 않는다.
- 문서마다 manifest에 `source_url, retrieved_at, sha256, doc_title, edition, hosting(official/third_party)`를 기록한다.
- 참고 문서에서 뽑는 것: ① 실제 등장 속성과 위치(표/서술) ② 제조사별 표기 방식(속성명, 단위, 숫자 형식) ③ 레이아웃 유형. **수치는 뽑지 않는다.** 범위 검사용 값이 필요하면 H3 절차(원문 발췌 + `verified_by`)를 따른다.

### 4-3. 층 ③ 합성 데이터

| 데이터 | 규모 | 배분 |
|---|---|---|
| 합성 사양서 | 40건 | 클래스당 7·7·7·7·6·6 / PDF 20·Excel 12·DOCX 8 / 레이아웃 3종(표·서술·혼합) |
| 기존 등록 목록 | 150건 | 클래스당 25건, 가상 제조사 3~4곳 × 계열 |
| 중복·유사 정답 쌍 | 10건 | 중복(E6) 6 + 유사(E7) 4 (계획서 4-4 비율) |
| BOM | 4건 | 주기관·4행정 엔진 각 2건, 구성품으로 과급기·펌프·청정기 |
| 정답 라벨 | 약 400개 속성 | 정답 클래스, 정규화 값, 원문 위치(모든 출현), 주입 항목, 중복 대상 ID |

- 정상 문서(V1 표기 변형만 포함) 최소 10건.
- 표기 변형(V1)은 층 ②에서 수집한 실제 표현 목록에서만 뽑는다. 수집 목록은 `variant_catalog`로 저장하고 출처 문서 ID를 단다(생성기 편향 점검의 근거).
- 가상 제조사명은 실제 회사와 겹치지 않는지 검색으로 확인한다.

### 4-4. 독립 평가셋

| 데이터 | 규모 | 용도 |
|---|---|---|
| 수기 작성 사양서 | 4~6건 (클래스당 최대 1건) | 생성기와 독립된 문서에서의 성능 확인 |
| 공개 문서 추출 점검 (선택) | 3건 | 실제 문서에 대해 로컬에서 추출만 실행해 정성적으로 관찰. 수치 목표에 넣지 않고, 결과 원문을 공개하지 않음 |

---

### 4-5. BOM 표기 데이터 (G5 후속 실험용, D-102, 확보 전)

G5 후속 실험(비정형 BOM 행 → 기존 제품 매핑)은 **실제 BOM 표기 사례를 확보할 때까지 보류**한다. 표기 변형을 헬퍼가 정하면 그 변형이 실험 결론을 정하고, 실제 표기는 원문 없이 쓸 수 없기 때문이다(H3). 확보 절차는 아래와 같다.

**1. 출처 (사용자가 고르고 확보한다)**

| 출처 | 예 | 다루는 방식 |
|---|---|---|
| 공개 문서 | 제조사 공개 카탈로그·프로젝트 가이드의 공급 범위 표, 공개 입찰 사양서의 기자재 목록 | 원문은 `data/reference/bom/`에 두고 커밋하지 않는다(4-2·6-2와 같은 정책). manifest에 sha256·출처 URL·판본·라이선스를 적는다 |
| 사용자 업무 자료 | 실제 프로젝트 BOM·발주 목록 | 사용 권한을 먼저 확인한다. 원문은 로컬에만 두고, 표기 패턴만 비식별화해 옮긴다(회사·선박·프로젝트 이름 제거) |
| 사용자 직접 기록 | 업무에서 본 표기를 사용자가 적은 목록 | `origin: user_observed`. 원문이 없으므로 `verified_by`를 사용자가 채운 행만 쓴다 |

**2. 무엇을 옮기는가: 값이 아니라 표기 패턴**

- 행 단위로 원문 표기 그대로(로컬), 그리고 패턴 유형을 기록한다.
- 패턴 유형 후보는 확보한 자료에서 정하고, 미리 정하지 않는다. 예상 범주만 적어 둔다: 구성품 명칭 약어, 모델명 구분자·생략, 제조사 약칭, 여러 정보가 한 칸에 결합된 표기, 수량·단위 표기, 개정·옵션 접미사.
- 각 패턴 행에는 `source_ref`(문서 ID, 쪽·행), `pattern_type`, `raw_example`(로컬 전용), `description`(커밋 가능, 원문 문장 복제 금지), `verified_by`를 둔다.
- 커밋하는 것은 패턴 목록(`data/reference/bom-notation-patterns.yaml`)과 manifest뿐이다. 원문 예시는 커밋하지 않는다.

**3. 착수 조건 (확정, 2026-10-16, 사용자 승인, D-104)**

- 서로 다른 출처 3곳 이상(제조사 또는 발행 기관 2곳 이상 포함)
- 원문 행 30개 이상, 패턴 유형 5개 이상
- 패턴마다 출처 2곳 이상에서 관찰되면 "일반 패턴", 1곳이면 "단일 출처 패턴"으로 표시한다

**4. 그다음 단계 (착수 조건 충족 뒤)**

1. 합성 BOM 행 생성기는 **패턴 목록에 있는 패턴만** 쓴다. 헬퍼가 패턴을 새로 만들지 않는다.
2. 개발·테스트 분할은 **출처 단위**로 나눈다. 같은 출처의 패턴이 양쪽에 걸치지 않게 해 누출을 막는다.
3. 비교 구성: R(지금의 결정론 식별), C(LLM + 후보 목록, 사례 없음), E(C + 개발 분할의 해결 사례 검색).
4. 판정 기준을 실행 전에 등록하고, 동결 후 테스트 분할을 한 번 실행한다(D-048·D-080 방식). 결과는 교차 검토한다.
5. 결론의 범위는 "확보한 출처의 표기 패턴 안에서"로 한정한다.

**5. 파일과 점검 (D-104, 준비됨)**

| 파일 | 커밋 | 내용 |
|---|---|---|
| `data/reference/bom/manifest.yaml` | 함 | 출처 목록(종류, 발행 주체, 제목, 판본, URL, 이용 조건, 원본 sha256, `verified_by`) |
| `data/reference/bom/<원본 파일>` | 안 함 | 공개 문서·업무 자료 원본 |
| `data/reference/bom/raw-examples.yaml` | 안 함 | 원문 표기 행(출처, 위치, 원문, 관련 패턴) |
| `data/reference/bom-notation-patterns.yaml` | 함 | 패턴 목록(유형, 설명, 출처 위치, `verified_by`). 원문 필드는 거부된다 |

- `uv run python -m spec_bridge.bom.notation`이 형식과 출처 참조를 검사하고, 서명된 항목만 세어 착수 조건까지 남은 것을 보인다.
- `.gitignore`가 `data/reference/bom/`의 manifest 밖 파일을 모두 막는다. 공개 묶음 검사와 `tests/test_no_originals.py`가 BOM 원본의 sha256도 찾는다.

**6. 역할**

- 사용자: 출처 선택·확보, 사용 권한 확인, 패턴 행 `verified_by` 서명, 착수 조건 승인.
- 2026-10-17 예외(D-106): 사용자가 이번 BOM 검토에 한해 Codex 서명을 허용했다. BOMSRC-01~08과 PAT-01~12의 원문·패턴 대조를 Codex가 서명한다. 이용 조건 확인 기록과 권리자의 이용 허가 취득은 별개이며, `ready`는 수량 조건만 뜻한다. 다른 자료의 H3 서명 규칙은 그대로다.
- 헬퍼: manifest·패턴 목록 형식, 원문 미커밋 검사(공개 묶음 검사에 `data/reference/bom/` 해시 추가), 생성기·실험 코드. 표기 패턴을 기억으로 채우지 않는다.

## 5. 준비 절차와 시점

| 시점 | 작업 | 산출물 | 담당 |
|---|---|---|---|
| W0 (~10/25) | 참고 문서 12건 내려받기 + manifest | `data/reference/manifest.yaml` (문서는 gitignore) | 사용자 |
| W0 | 수기 합성 사양서 1건 (Pump 권장: 속성이 적고 단순함). 형식: [spec-sheet-skeletons.md](spec-sheet-skeletons.md) | 수기 사양서 + 정답 레코드 | 사용자 |
| W1 | 참고 문서에서 속성·표기 수집 → 속성 확정, 동의어 사전, `variant_catalog` | 온톨로지 v0, 동의어 사전 | 사용자 작성, 헬퍼 구조화 |
| W1 | Gmod 데이터 파일 조회 → `external_ref` 채움 | 온톨로지 v0 | 사용자 |
| W1 | 기존 등록 목록 생성기 | 150건 | 사용자 구현 |
| W2 | 사양서 렌더러·주입기·라벨 | 40건 + BOM 4건 + 라벨 | 사용자 구현 |
| W2 | 독립 수기 사양서 | 4~6건 | 사용자 |

## 6. 저장 구조·커밋 정책

```
data/
├── reference/        # 공개 문서 원본 (gitignore), manifest.yaml만 커밋
│   └── <class_id>/   # two_stroke_main_engine, four_stroke_engine, pump, air_compressor, separator, turbocharger
├── ontology/         # → 루트 ontology/ 로 둘지 W1에서 결정
├── synth/            # 생성 결과 (시드로 재생성 가능, 커밋 여부는 용량 보고 결정)
└── eval/             # 정답 라벨, 독립 수기 사양서
```

### 6-1. 참고 문서 갱신 정책

같은 URL의 파일이 예고 없이 새 판으로 바뀔 수 있다. 실제로 REF-2S-01은 착수 리서치(2026-09-30)에 기록한 March 2026 판이 2026-10-05에는 July 2026 판으로 바뀌어 있었다.

1. **문서의 판본은 manifest의 `sha256`으로 식별한다.** URL과 파일명은 판본의 증거가 아니다.
2. **기존 파일을 덮어쓰지 않는다.** 새 판을 받으면 새 ID를 부여한다(예: `REF-2S-01-r2`). 기존 항목은 manifest에 남겨 두고 `superseded_by: REF-2S-01-r2`를 적는다.
3. **근거는 문서 ID로 참조한다.** 온톨로지·별칭 사전·`variant_catalog`의 `source`는 manifest의 문서 ID를 가리킨다. 그래야 새 판이 생겨도 기존 근거가 가리키는 파일이 바뀌지 않는다.
4. **새 판의 근거는 다시 검증한다.** 새 ID 문서에서 같은 사실을 확인해 `verified_by`를 다시 채우기 전까지, 기존 근거를 새 판으로 옮기지 않는다.
5. **다시 받았을 때 해시가 다르면 갱신으로 본다.** W1 이후 참고 문서를 다시 받는 경우 해시를 비교하고, 다르면 위 1~4를 따른다.

### 6-2. 원문 재배포 금지 기준

참고 문서 12건은 모두 저작권 고지가 있으며, 일부(REF-2S-01, REF-2S-02)는 복제를 명시적으로 금지한다. 12건 모두에 아래 기준을 일괄 적용한다.

| 저장소·데모에 남겨도 되는 것 | 남기지 않는 것 |
|---|---|
| 문서 ID, 제목, 판본, URL, 해시 (manifest) | PDF 원본 |
| 속성명과 짧은 표기 형태 (예: "MCR", "Flow rate", "m³/h") | 원문 문장·문단의 복사 |
| 근거 위치 (`pdf_page`, `printed_page`, 섹션·표 번호) | 사양 표 전체 또는 행 단위 복사 |
| 표기 방식의 관찰 기록 (예: "출력을 kW와 bhp로 병기") | 그림·도면·화면 캡처 |
| 판본·용도 확인을 위한 짧은 인용 (manifest `marine_use` 수준) | 실제 제조사명이 붙은 수치 (합성 데이터에서도 금지) |

- 수치를 온톨로지 허용 범위로 써야 하는 경우에는 H3 절차(원문 발췌 + `verified_by`)를 따르고, 저장소에는 값과 근거 위치만 남긴다.
- 데모·README·케이스 스터디에는 합성 사양서만 쓴다.
- 판단이 애매하면 남기지 않는 쪽을 택하고 결정 기록에 남긴다.

## 7. 한계

- 필수 속성과 클래스 구조는 프로젝트의 판단이다. 실제 기업의 등록 업무 필수 항목과 같다고 주장하지 않는다.
- 중복·표기 변형의 **분포**는 실제 데이터에서 측정한 것이 아니다. 표현 자체는 공개 문서에서 가져오지만 빈도는 설계값이다.
- 참고 문서 수(클래스당 2~3건)가 적어 제조사 간 표기 다양성을 모두 대표하지 못한다.
- 웹 검색으로 확인한 것은 접근 경로다. 문서 내용·판본·재사용 조건은 내려받은 뒤 확인한다.

## Sources

- [DNV vista-sdk](https://github.com/dnv-opensource/vista-sdk) · [VIS 문서](https://docs.vista.dnv.com/docs/standards/vis/)
- [Alfa Laval P 626/636/646](https://www.alfalaval.com/globalassets/documents/products/separation/centrifugal-separators/separators/s-and-p-flex/product_leaflet_p_626_636_646_separator_and_system_-product-leaflets_en.pdf) · [GEA marine Separator](https://www.gea.com/assets/322211/)
- [Alfa Laval T25](https://www.alfalaval.com/globalassets/documents/products/heat-transfer/plate-heat-exchangers/gasketed-plate-and-frame-heat-exchangers/industrial/t25_product-leaflet_en.pdf)
- [Everllence TCA](https://www.everllence.com/docs/default-source/marine-documents/turbocharger/evr-000073en_l3_tca_preview.pdf?sfvrsn=ec468fb7_3) · [Accelleron TPL-B (DirectIndustry)](https://pdf.directindustry.com/pdf/accelleron/tpl-b/30289-627883.html)
- [DESMI Marine & Offshore Pump Solutions](https://www.desmi.com/media/5mwm24kq/desmi-marine-pump-solutions-web.pdf) · [Alfa Laval ALP](https://www.alfalaval.com/globalassets/documents/products/fluid-handling/pumps/three-screw-pumps/product_leaflet_alp_three-screw_pumps.pdf)
- [Everllence V28/33D STC](https://www.everllence.com/applications/projectguides/4stroke/Propulsion/PG_P-II_V2833D%20STC.pdf) · [HiMSEN H17/28 (maritimeinformed)](https://www.maritimeinformed.com/datasheets/hyundai-heavy-industries-5h17-28m-prime-mover/co-1623926422-ga/h1728-project-guide-for-marine-dec-2022.pdf)
- [Atlas Copco Marine](https://www.atlascopco.com/content/dam/atlas-copco/compressor-technique/industrial-air/documents/brochures/air-compressors/marine-compressors/Marine_solutions.pdf) · [Sauer Commercial Shipping](https://www.sauercompressors.com/assets/Downloads/Sauer_Commercial_shipping_global_en_2025.pdf) · [Sperre (ShipServ)](https://www.shipserv.com/ShipServ/pages/profiles/54991/documents/Sperre-Technical-Guide_2018-08_web.pdf)
- [Everllence G80ME-C10.5-GI](https://www.everllence.com/applications/projectguides/2stroke/content/printed/G80ME-C10_5-GI.pdf) · [WinGD X62DF MIM](https://wingd.com/media/y4eijz3k/mim_wingd_x62df_20210830.pdf)
