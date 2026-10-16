# W1 온톨로지와 등록 저장소 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (교육 모드 — 사용자가 타이핑하고 헬퍼는 설명·조각·검증을 맡는다). 서브에이전트 실행은 사용자가 요청할 때만. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 확정된 합성 데이터셋 v1을 기준으로, 온톨로지 YAML을 진실원천으로 삼는 로더·무결성 검사·사실 모델·JSON Schema·정의서와 SQLite 등록 저장소를 만든다.

**Architecture:** `ontology/ontology.yaml`(사람이 편집) → `spec_bridge.ontology`(로더·무결성·스키마/정의서 생성) → `spec_bridge.registry`(SQLite 적재·식별 규칙). 추출 후보 스키마와 등록 준비 정책을 분리한다([schema-design.md](../../ontology-scope/schema-design.md) §1). 수치 허용 범위·제조사 규칙은 넣지 않는다(H3).

**Tech Stack:** Python 3.12(uv), Pydantic v2, PyYAML, pint, sqlite3(표준), pytest, ruff, mypy

**Spec:** [프로젝트 계획 W1·FR-01~03·4-1~4-2](../../spec-bridge-project-plan.md), [실행 스키마 설계안](../../ontology-scope/schema-design.md), [데이터셋 명세](../../../data/ontology/dataset-contract.yaml), [정답 계약](../../../data/synth/answer-contract.yaml)

## Global Constraints

- 데이터셋 v1 파일은 수정하지 않는다: `shasum -a 256 -c data/synth/SHA256SUMS`가 항상 0 실패.
- 테스트 분할 정답(`dataset-manifest.yaml`의 split=test)은 W1 코드·테스트·사전 작성에 쓰지 않는다. 개발 24건과 handwritten 6건만 사용한다.
- 장비 허용 범위·형식명 해석·실제 제조사 별칭을 기억으로 쓰지 않는다. 출처가 있는 표기는 `source/edition/location/verified_by`를 갖고 `verified_by`는 사용자만 채운다. 나머지는 `origin: synthetic`.
- 테스트의 도메인 값은 온톨로지·데이터 파일에서 읽는다(H3-4).
- 커밋·푸시는 사용자 요청 시에만.
- 완료 판정은 `uv run pytest`, `uv run ruff check .`, `uv run mypy spec_bridge` 결과로만.

## Review Focus

1. **형식 미상 펌프**: `pump_type`이 없거나 미지 값이면 조건부 필수(head/압력)를 적용하지 않고 review로 남겨야 한다 → Task 4 테스트.
2. **한 별칭이 두 속성에 걸림**: CP-S1 질문 3. 로더가 거부해야 한다 → Task 2 테스트.
3. **pint가 못 읽는 단위 표기**(`m3/h`, `l/h`): 온톨로지 `units`의 pint 표현으로만 해석하고 차원 불일치는 로드 단계에서 거부 → Task 2 테스트.
4. **0과 false, 빈 문자열**: 0·false는 값, 빈 문자열·빈 목록은 필수 미충족 → Task 3·4 테스트.
5. **모델명 표기 변형 식별**: `VX022 009`, `VX008021`, 합성 별칭 제조사가 등록 제품 하나로 식별되어야 하고, 접두사만 같은 다른 제품은 같은 제품이 아니어야 한다 → Task 7 테스트.

---

## 파일 구조

| 경로 | 책임 |
|---|---|
| `pyproject.toml` | 의존성·ruff·mypy·pytest 설정 |
| `ontology/ontology.yaml` | 클래스·속성·단위·조건/기준 어휘·관계·식별 규칙·라벨 별칭(출처 포함) |
| `spec_bridge/ontology/definitions.py` | 온톨로지 파일의 Pydantic 정의 모델 |
| `spec_bridge/ontology/loader.py` | `load_ontology()`와 무결성 검사 |
| `spec_bridge/ontology/facts.py` | 공통 사실 모델(참고 구현 이식·확장) |
| `spec_bridge/ontology/schema.py` | 클래스별 후보 모델·JSON Schema 생성 |
| `spec_bridge/ontology/policy.py` | 클래스별 등록 필수 속성 해석 |
| `spec_bridge/ontology/docs.py` | 정의서 Markdown 생성 |
| `spec_bridge/registry/identity.py` | 식별 규칙(모델명 정규화·제조사 별칭) |
| `spec_bridge/registry/store.py` | SQLite 스키마·적재·조회 |
| `tests/...` | 작업별 테스트 |
| `docs/ontology/definition.md` | 생성된 정의서(O2) |

---

### Task 0 (W1-0): 저장소 골격

**DoD:** `uv run pytest -q` 통과(스모크 1건), `uv run ruff check .`, `uv run mypy spec_bridge` 0 오류.

- [ ] **Step 1:** git 저장소 초기화 여부를 사용자가 결정(권장: `git init`, 커밋은 요청 시).
- [ ] **Step 2:** `uv init --package --name spec-bridge`로 골격을 만들고 의존성 추가.

```bash
uv add pydantic pyyaml pint
uv add --dev pytest ruff mypy types-PyYAML
```

- [ ] **Step 3:** 스모크 테스트 작성 → 실패 확인 → `spec_bridge/__init__.py`에 `__version__` 추가 → 통과.

```python
# tests/test_smoke.py
import spec_bridge

def test_package_imports() -> None:
    assert spec_bridge.__version__
```

- [ ] **Step 4:** `pyproject.toml`에 `[tool.mypy] strict = true`, `[tool.pytest.ini_options] testpaths = ["tests"]`. DoD 명령 3개 실행.

### Task 1 (W1-1): 온톨로지 YAML v0

**Files:** Create `ontology/ontology.yaml`

**Interfaces:** Produces — 최상위 키 `version, origin, units, vocabularies, classes, attributes, relations, identity, label_aliases`.

`data/ontology/dataset-contract.yaml`(동결)을 복사하지 말고 계획서 4-1의 필드 구성으로 **다시 쓴다**. 옮길 내용과 새로 추가할 내용:

| 영역 | 출처 | 비고 |
|---|---|---|
| 클래스 계층·필수 정책 | dataset-contract `classes` | 말단 6·중간 3, `required_all/any/conditional` 그대로 |
| 속성 자료형·정규 단위·차원 | dataset-contract `attributes` | `dimension`은 pint 차원 문자열(`[length]`, `[mass]` 등) |
| 단위 | dataset-contract `units` + **pint 표현** | 예: `m3/h: {pint: "m**3/hour"}`, `l/h: {pint: "liter/hour"}` |
| 기준·조건 어휘 | dataset-contract `metadata_contract` + 정답 계약 | `viscosity_basis`에 `fluid_reference` 포함(참고 구현에는 빠져 있음) |
| 라벨 별칭 | `data/synth/variant-catalog.yaml` | 항목마다 `source`(REF ID), `location`(pdf_page), `verified_by: null` |
| 식별 규칙 | 정답 계약 `identity_policy` | `origin: synthetic` |
| 관계 | dataset-contract `relations` | `cardinality` 추가, `has_component` = 공급 범위 포함(D-014) |
| keywords | 신규 | 클래스 매핑 단서. 클래스 설명 문구(`Marine air compressor` 등)에서만 |

- [ ] **Step 1:** Pump 클래스 하나만 먼저 작성하고 Task 2의 로더 테스트로 검증한 뒤 나머지 5개로 확장한다(설계안 권장 순서).
- [ ] **Step 2:** 허용 범위(`range`)는 쓰지 않는다. `allowed_values`는 application 두 곳(합성 닫힌 목록)만.

### Task 2 (W1-2): 정의 모델·로더·무결성 검사 (FR-01)

**Files:** Create `spec_bridge/ontology/definitions.py`, `loader.py`; Test `tests/ontology/test_loader.py`, `tests/conftest.py`

`tests/conftest.py`의 공용 픽스처·보조 함수(이후 작업이 모두 사용):
- `onto` / `raw` 픽스처: `ontology/ontology.yaml` 로드 결과와 원본 dict
- `write_yaml(tmp_path, raw) -> Path`
- `dev_ids() -> list[str]`: `data/synth/dataset-manifest.yaml`에서 split=dev만
- `load_dev_answer(input_id) -> dict`: split=dev가 아니면 `ValueError`(테스트 분할 차단)
- `to_facts(gold_facts, observations) -> list[dict]`: 정답 사실에서 `fact_id/observation_ids/admissibility`를 빼고 관찰을 `occurrences`로 붙임
- `group_facts(gold) -> dict[str, list[dict]]`: 속성 ID별 `to_facts` 결과

**Interfaces:**
- Produces: `load_ontology(path: Path) -> Ontology`, `class OntologyError(ValueError)`, `Ontology.attributes_of(class_id: str) -> list[str]`(상속 포함), `Ontology.ancestors(class_id) -> list[str]`

- [ ] **Step 1: 실패 테스트 작성** — 정상 로드 1건과 위반 사례별 1건. 위반 픽스처는 정상 YAML을 테스트 안에서 조금씩 바꿔 만든다.

```python
def test_loads_six_leaf_classes(ontology: Ontology) -> None:
    leaves = {c for c, d in ontology.classes.items() if not d.abstract}
    assert len(leaves) == 6

def test_rejects_alias_on_two_attributes(tmp_path: Path, raw: dict) -> None:
    raw["label_aliases"].append({**raw["label_aliases"][0], "attribute": "head"})
    with pytest.raises(OntologyError, match="alias"):
        load_ontology(write_yaml(tmp_path, raw))
```

검사할 위반: 중복 ID, 없는 부모, 순환 상속, 필수 목록의 미정의 속성, 조건부 분기의 미정의 속성/값, 정의되지 않은 단위, **pint 차원과 선언 차원 불일치**, 한 별칭이 두 속성에, 출처 항목에 `source` 누락, `verified_by`가 비어 있지 않은데 사용자 검증 기록이 없음(경고 대상 목록으로 반환).

- [ ] **Step 2:** `uv run pytest tests/ontology/test_loader.py -q` → 실패 확인.
- [ ] **Step 3:** 구현 힌트 — YAML을 `definitions.py`의 모델로 `model_validate`하고, 교차 참조 검사는 `loader.py`의 함수 하나씩으로 나눈다.

```python
def check_dimensions(units: dict[str, UnitDef], attrs: dict[str, AttributeDef]) -> None:
    ureg = pint.UnitRegistry()
    for attr_id, attr in attrs.items():
        if attr.canonical_unit is None:
            continue
        actual = ureg.parse_units(units[attr.canonical_unit].pint).dimensionality
        if str(actual) != attr.dimension:
            raise OntologyError(f"{attr_id}: {attr.canonical_unit} is {actual}")
```

- [ ] **Step 4:** 통과 확인 + ruff/mypy.

### Task 3 (W1-3): 사실 모델과 클래스별 후보 스키마 (FR-02)

**Files:** Create `spec_bridge/ontology/facts.py`, `schema.py`; Test `tests/ontology/test_facts.py`, `test_schema.py`

**Interfaces:**
- Consumes: `Ontology`
- Produces: `Fact`, `Occurrence`, `Location`(PDF page+bbox / sheet+cell / docx paragraph·table·row·cell / source_line), `build_candidate_model(onto, class_id) -> type[BaseModel]`, `export_json_schemas(onto, out_dir: Path) -> list[Path]`

[examples/common_models.py](../../ontology-scope/examples/common_models.py)를 출발점으로 이식한다. 조건·기준 키와 값은 온톨로지 `vocabularies`에서 만든다(하드코딩 금지).

- [ ] **Step 1: 실패 테스트** — 값은 개발 정답 파일에서 읽는다.

```python
def test_two_viscosity_conditions_are_two_valid_facts(onto: Ontology) -> None:
    gold = load_dev_answer("SYN-032")          # 개발 분할만
    model = build_candidate_model(onto, gold["expected_class"])
    facts = [f for f in gold["facts"] if f["attribute_id"] == "rated_throughput"]
    candidate = model.model_validate(
        {"attributes": {"rated_throughput": to_facts(facts, gold["observations"])}}
    )
    assert len(candidate.attributes.rated_throughput) == 2

def test_unknown_condition_key_rejected(onto: Ontology) -> None: ...
def test_reversed_range_rejected(onto: Ontology) -> None: ...
def test_zero_and_false_are_values(onto: Ontology) -> None: ...
```

- [ ] **Step 2:** 실패 확인. **Step 3:** `pydantic.create_model`로 클래스별 `attributes` 모델을 만들고, 속성마다 `list[Fact]`(빈 목록 금지 아님 — 후보 단계는 누락 허용). **Step 4:** 통과 + `export_json_schemas`로 `schemas/*.json` 6개 생성 확인.

### Task 4 (W1-4): 등록 필수 정책 해석

**Files:** Create `spec_bridge/ontology/policy.py`; Test `tests/ontology/test_policy.py`

**Interfaces:** Produces `missing_required(onto, class_id, facts: dict[str, list[Fact]]) -> list[str]`, `presence_status(...) -> Literal["present", "missing", "undetermined"]` (D-022에서 policy_status에서 변경)

- [ ] **Step 1: 실패 테스트** — 개발 24건의 `missing_required`와 일치(정답 파일의 사실만 입력).

```python
@pytest.mark.parametrize("input_id", dev_ids())
def test_matches_gold_missing_required(onto: Ontology, input_id: str) -> None:
    gold = load_dev_answer(input_id)
    facts = {k: [Fact.model_validate(f) for f in v] for k, v in group_facts(gold).items()}
    assert missing_required(onto, gold["expected_class"], facts) == gold["missing_required"]

def test_unknown_pump_type_is_review_not_missing(onto: Ontology) -> None: ...
def test_empty_string_does_not_satisfy_required(onto: Ontology) -> None: ...
```

- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과. 이 함수는 W4 검증기의 일부로 재사용한다(검증 전체는 W4).

### Task 5 (W1-5): 정답 적합성 — W1 원래 DoD

**Files:** Create `tests/ontology/test_gold_conformance.py`, `spec_bridge/ontology/gold.py`(정답 → 후보 변환, 평가기 메타데이터 제거)

**DoD:** 생성한 스키마로 handwritten 1건 이상(원래 DoD)과 개발 24건의 사실이 검증된다. 표현 불가 항목은 테스트에서 명시적으로 `xfail(reason=...)`하고 CP-S1 패키지에 기록.

- [ ] **Step 1:** HW-PUMP-001(정답 v2)과 개발 v3 변환 테스트 작성 → 실패 → `gold_to_candidate()` 구현 → 통과.
- [ ] **Step 2:** handwritten 나머지 5건은 결과를 표로 기록(통과/표현 부족/정답 오류 구별).

### Task 6 (W1-6): 정의서 자동 생성 (O2)

**Files:** Create `spec_bridge/ontology/docs.py`; Output `docs/ontology/definition.md`; Test `tests/ontology/test_docs.py`

- [ ] **Step 1: 실패 테스트** — 모든 클래스·속성 ID가 문서에 있음, 두 번 생성 결과가 같음(결정론), 출처 항목에 `verified_by` 상태 표시.
- [ ] **Step 2~4:** 구현 → `uv run python -m spec_bridge.ontology.docs` 로 생성 → 통과.

### Task 7 (W1-7): 등록 저장소와 식별 규칙 (FR-03)

**Files:** Create `spec_bridge/registry/identity.py`, `store.py`; Test `tests/registry/test_identity.py`, `test_store.py`

**Interfaces:**
- Produces: `normalize_model(text: str) -> str`, `resolve_maker(text: str, makers) -> str | None`, `RegistryStore(path)`, `.load_jsonl(path, split) -> int`, `.find_by_identity(maker_id, model) -> str | None`

테이블: `manufacturers`, `manufacturer_aliases`, `products`(UNIQUE(maker_id, model_key)), `product_facts`(JSON), `relations`, `registration_events`(이력). 기존 목록은 **생성하지 않고** `data/synth/registry/*.jsonl`을 적재한다(계획 변경, 아래 승인 필요).

- [ ] **Step 1: 실패 테스트**

```python
def test_loads_split_counts(store: RegistryStore) -> None:
    assert store.load_jsonl(REG / "dev.jsonl", "dev") == 90

def test_reload_is_idempotent(store: RegistryStore) -> None: ...

@pytest.mark.parametrize("raw", ["VX022 009", "vx022-009", "VX022009"])
def test_model_variants_share_identity(raw: str) -> None:
    assert normalize_model(raw) == normalize_model("VX022-009")

def test_same_series_is_not_same_identity() -> None:
    assert normalize_model("VX022-109") != normalize_model("VX022-009")
```

- [ ] **Step 2~4:** 실패 확인 → 구현 → 통과. DB 스키마 확정은 H2 에스컬레이션 트리거(되돌리기 어려운 변경)이므로 구현 전에 테이블 설계를 사용자와 확인한다.

### Task 8 (W1-8): 공유 모듈 이식 — **차단**

제공자 어댑터·오프라인 가드·감사 로그·평가 실행기의 원본 위치·버전이 문서에 없다(착수 체크리스트 PRE-04 미완료). 사용자가 경로를 주면 별도 계획으로 진행하고, 없으면 W3(LLM 사용 시점) 직전으로 미룬다.

### Task 9 (W1-9): 🔶 CP-S1 검토 패키지

**DoD:** 전체 DoD 명령 3개 통과 + `shasum -c` 0 실패 후, 계획서 H2 형식의 패키지(배경 5줄, 파일·수치, CP-S1 질문 4개, 확신 낮은 지점, 전제)를 작성한다. `verified_by`가 빈 출처 항목 목록을 첨부한다. 헬퍼는 통과 판정을 하지 않는다.

---

## 승인이 필요한 계획 차이 (H1-6)

1. **기존 등록 목록 생성기 → 적재기**: 계획서 W1의 "기존 목록 100~200건 생성기"는 데이터셋 v1에서 이미 만들어졌으므로 적재로 대체.
2. **W1 DoD 확장**: handwritten 1건 대조에 개발 24건 대조를 추가. 테스트 16건은 W1에서 읽지 않음.
3. **온톨로지 위치**: 루트 `ontology/ontology.yaml`(계획서 5-4). `data/ontology/dataset-contract.yaml`은 데이터셋 명세로 동결 유지.
4. **공유 모듈 이식 보류**: 원본 위치 확인 전까지 W1 범위에서 제외.

승인되면 decisions.md에 D-020으로 기록한다.

---

## W1-10: CP-S1 보완 (2026-10-11 추가)

근거: [CP-S1 검토 결과](../../reviews/cp-s1-review-result.md), decisions.md `CP-S1`. 각 항목은 리뷰 재현 절차를 **실패 테스트로 먼저** 옮긴 뒤 수정한다. 공통 DoD: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy spec_bridge` 통과 + 데이터셋 해시 불일치 0.

| 순서 | ID | 수정 | 회귀 테스트(먼저 작성) | 파일 |
|---|---|---|---|---|
| 1 | R5 | `LabelAlias`에 항목별 `origin: sourced | synthetic` 추가. `sourced`는 `source`·`location` 필수, `synthetic`은 선택. 정의서에 상태 열 표시 | 항목 `origin: synthetic` 로드 성공, `sourced`인데 `source` 없으면 거부, 정의서에 합성 표시 | `definitions.py`, `loader.py`, `docs.py`, `test_loader.py`, `test_docs.py` |
| 2 | R4 | 새 DB에서만 버전 기록. 기존 DB는 `schema_version`·`ontology_version` 비교 후 다르면 `RegistryError`(재생성 안내) | 버전 0으로 적재→닫기→버전 1로 열기 = 오류, 같은 버전 재오픈 = 정상 | `store.py`, `test_store.py` |
| 3 | R1 | 제조사 적재 시 DB의 기존 이름/별칭과 입력을 합쳐 소유 제조사 충돌을 검사, 같은 `maker_id`의 내용 변경도 거부. 완전 동일 내용만 멱등 | **두 번의 적재 호출**: A 적재 → A의 이름을 별칭으로 가진 B 적재 = 전체 거부·DB 불변 | `store.py`, `test_store.py` |
| 4 | R2 | 최상위 `model_designation`과 `attributes.model_designation`을 `model_key`로, `maker_id`와 `attributes.maker`를 제조사 색인으로 대조. 불일치 거부, 허용 표기 변형은 통과 | 최상위 모델명만 변경 = 거부, 공백·대소문자 변형 = 통과 | `store.py`, `test_store.py` |
| 5 | R3 | 사용자 결정에 따름(아래) | 결정안에 맞춘 압축기 기준 제거 사례 | `policy.py`(+`ontology.yaml`) |
| 6 | L3 | — | HW-SEP-001 변환 결과 두 사실의 rating·condition·scope·occurrences 보존 직접 검사 | `test_gold_conformance.py` |
| 7 | 문서 | L2 별칭 선정 근거·고정 시점, NFR-07 시드 근거 적용 범위, 별칭 21개 사용자 처리 결과 | — | decisions.md, 계획서 NFR-07 주석 |

R3 선택지:
- **(A) 범위 제한**: W1 함수를 "필수 존재 검사"로 명명·문서화(`presence_status`: present/missing/undetermined)하고, 중요 기준 미상 review를 포함한 완전한 등록 준비 판정은 W4 검증기로 넘긴다.
- **(B) 온톨로지로 정책화**: 클래스별 "미상이면 review인 중요 기준"(schema-design §5 표: 압축기 capacity 기준·압력 기준, 분리기 처리량 기준·조건, 엔진 정격점·출력 기준, 과급기 엔진 사이클·per-unit 기준 등)을 YAML에 선언하고 `policy_status()`가 해석한다.
