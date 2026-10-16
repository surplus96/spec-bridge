# W4 검증·중복·출력과 문맥 설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (교육 모드 — 헬퍼가 스크래치 사본에서 검증한 **전체 코드**를 단계마다 제공하고 사용자가 타이핑·실행한다, 메모리 `education-mode-full-code`. 사용자가 직접 수정을 요청한 단계만 헬퍼가 구현). W3 계획과 같은 형식으로, 이 문서는 작업 단위의 인터페이스·테스트·DoD를 고정한다. 코드는 실행 시점에 스크래치 검증 후 제공한다. 서브에이전트 실행은 사용자가 요청할 때만. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사양서 1건을 업로드하면 클래스·정규화 속성(원문 위치 포함)·검증 결과(E1~E5)·중복/유사 판정이 담긴 표준 JSON이 나온다(MVP 종료선). 그 전에 CP-S3가 지목한 병목(비고 → 기준·조건·범위)을 설계 실험으로 다룬다.

**Architecture:** W3 파이프라인(파서 → 분류 → 추출 C → 결정론 정규화) 뒤에 결정론 검증기(`validate/`)와 중복 판정기(`dedup/`)를 붙이고, 결과를 표준 JSON(`registry/output.py`, 온톨로지 파생 JSON Schema로 검증)으로 낸다. 구성 D는 검증 결과로 실패 속성만 1회 재추출한다. FastAPI는 이 파이프라인 함수 하나를 감싼다. LangGraph·HITL·UI는 W5다.

**Tech Stack:** 기존(Python 3.12, uv, Pydantic v2, pint, Ollama `exaone3.5:7.8b`) + **rapidfuzz**(이름 유사도), **FastAPI + python-multipart**(업로드 API). 임베딩(bge-m3)은 쓰지 않는다(YAGNI, 필요가 수치로 드러나면 재검토).

**Spec:** [계획서 W4·FR-09~11·5-1·5-3·6-1·6-2·G3·G4](../../spec-bridge-project-plan.md), [정답 계약](../../../data/synth/answer-contract.yaml)(`issue`·`scoring.issue_match`·`comparison`), `data/synth/comparison-candidates.yaml`(분할 내 완전 라벨), [CP-S3 검토 결과](../../reviews/cp-s3-review-result.md)(W4 반영 항목), decisions.md D-028~D-037, [W3 보고서](../../reports/w3-first-comparison.md) §7·§8.

## Global Constraints

- **개발 분할 24건만** 실행·튜닝·보고한다. 테스트 16건은 W6 전까지 실행하지 않고 클라우드로도 보내지 않는다(D-020, D-034).
- 채점기는 `scorer_id f8355d4a3361`이 기준이다. 채점 모듈을 바꾸거나 추가하면 새 ID를 decisions.md에 기록하고, 기존 실행을 같은 ID로 재채점해 나란히 보고한다(D-036). 원 `metrics.json`은 덮지 않는다.
- 검증·중복·정규화는 결정론 코드만 한다. LLM은 분류 후보 선택과 원문 값 추출까지다(계획서 5-1).
- 장비 파라미터 범위·형식명 해석·제조사 별칭·규제 수치는 기억으로 넣지 않는다(H3). E4는 온톨로지 `allowed_values`(합성 목록)만 쓰고 범위 검사는 하지 않는다. 중복 판정의 별칭은 `manufacturers.json`(등록 데이터)만 쓴다.
- 문맥 어휘 설명은 **온톨로지 정의문에서만** 쓴다. 개발 문서의 비고 문구를 프롬프트 예시로 옮기지 않는다(CP-S3 L6). 설명은 `origin: synthetic`, `verified_by`는 사용자만 채운다.
- 개발셋 조정 횟수·변경 내용·해시를 실행마다 기록한다. W3의 1회(D-031)에 이어 W4-1이 2회째다.
- 모델 입력은 파싱 블록과 클래스·속성·어휘 정의뿐이다(CP-S2 W3 입력 계약). 정답·비교 정답·등록 목록은 모델에 넣지 않는다(등록 목록은 결정론 정규화·중복 판정만 쓴다).
- 완료 판정은 `uv run pytest -q`, `uv run ruff check .`, `uv run mypy spec_bridge tests`로만 한다. 커밋·푸시는 사용자 요청 시에만.

## Review Focus

1. **문맥만 다른 같은 속성의 복수 값**: 같은 속성이 다른 기준·조건·범위로 여러 번 나오면 E5가 아니다. E5는 같은 사실 키 안의 서로 다른 값만이다 → Task 3 테스트.
2. **조건부 필수의 분기 값을 모를 때**: 예를 들어 펌프 형식이 허용 목록 밖이거나 없으면 조건부 필수 속성을 E1로 단정하지 않고 `undetermined`(검토 필요)로 둔다 → Task 3 테스트.
3. **클래스가 `unknown`이거나 문서 파싱에 실패할 때**: 검증·중복·출력이 예외 없이 `needs_review` 결과를 내고, API는 500이 아니라 결과 JSON(또는 4xx)을 돌려준다 → Task 6·7 테스트.
4. **제조사 별칭·모델명 표기 변형으로 들어온 기존 제품**: 등록 별칭과 `model_key`로 같은 제품이면 `duplicate`, 이름이 비슷해도 식별이 다르면 `duplicate`로 올리지 않는다 → Task 5 테스트.
5. **D의 재추출이 원래 맞던 값을 덮어쓸 때**: 재추출은 실패 속성만 다루고, 그 밖의 사실은 바꾸지 않는다 → Task 8 테스트.

---

## 작업 목록

| ID | 작업 | 주체 | 승인 필요 |
|---|---|---|---|
| W4-0 | C 동일 해시 재실행(잡음 하한) | 사용자 터미널 | — |
| W4-1 | 문맥 어휘 설명과 문맥 질문 방식 실험 | 교육 모드 + 사용자 실행 | **결정 1·2** |
| W4-2 | 검증 결과 모델과 미해결 사유 매핑 | 교육 모드 | **결정 3** |
| W4-3 | 결정론 검증기 E1~E5 (FR-09) | 교육 모드 | — |
| W4-4 | 검증 채점기 G3와 채점기 ID 갱신 | 교육 모드 | **결정 4** |
| W4-5 | 중복·유사 판정기와 채점기 G4 (FR-10) | 교육 모드 | **결정 5·6** |
| W4-6 | 표준 JSON 출력 (FR-11) | 교육 모드 | — |
| W4-7 | 처리 함수와 FastAPI 업로드 엔드포인트 (MVP) | 교육 모드 | 결정 6(의존성) |
| W4-8 | 구성 D(검증 피드백 재추출 1회)와 비교표 갱신 | 교육 모드 + 사용자 실행 | — |
| W4-9 | W4 보고서와 MVP 판정 자료 | 헬퍼 | — |

## 파일 구조

| 경로 | 책임 |
|---|---|
| `ontology/ontology.yaml` (수정) | `vocabularies`의 각 기준·조건 토큰과 범위 항목에 `description`(origin synthetic) 추가 — W4-1 |
| `spec_bridge/ontology/definitions.py` (수정) | 어휘 설명 필드 |
| `spec_bridge/extract/schemas.py`·`extractor.py` (수정) | 스키마 `description`에 어휘 설명 노출, 문맥 질문 방식 옵션 |
| `spec_bridge/validate/findings.py` | `Finding`, `Code`, 미해결 사유 → 코드 매핑 |
| `spec_bridge/validate/validator.py` | `validate(onto, class_id, facts, unresolved) -> Validation` (E1~E5, 등록 준비 상태) |
| `spec_bridge/dedup/matcher.py` | `match(onto, class_id, facts, registry) -> list[Match]` (블로킹 → 식별 일치 → 이름·속성 유사) |
| `spec_bridge/eval/validation_scoring.py` | G3: 정답 `issues`·`missing_required` 대비 코드별 P/R, 정상 문서당 오탐 수 |
| `spec_bridge/eval/dedup_scoring.py` | G4: 비교 정답 대비 duplicate/similar/new 혼동 행렬 |
| `spec_bridge/registry/output.py` | `RegistrationResult` 표준 JSON + JSON Schema 검증 |
| `spec_bridge/pipeline.py` | `process_document(path, provider) -> RegistrationResult` |
| `spec_bridge/api/app.py` | FastAPI `POST /documents` |
| `spec_bridge/eval/experiment.py` (수정) | 구성 D, 검증·중복 채점 출력 |
| `docs/reports/w4-validation-dedup.md` | W4 결과 보고 |

---

### Task 0 (W4-0): C 동일 해시 재실행 — 잡음 하한 (CP-S3 L5)

**목적:** W4 비교의 최소 효과 크기를 정한다. 코드 변경은 없다.

- [ ] 사용자 터미널: `OFFLINE=1 uv run python -m spec_bridge.eval.experiment --config C` (2차와 같은 해시, 약 15분)
- [ ] 헬퍼: 2차 C(`C-20261012T052149Z`)와 문서별 예측을 비교한다(같은 문서의 응답 원문 일치 수, 사실 키 차이, F1 차이). 두 실행을 `scorer_id f8355d4a3361`로 채점한다.
- [ ] decisions.md 기록: 같으면 "잡음 하한 0(이 설정)", 다르면 그 차이(사실 F1·문맥 키 TP)를 W4 비교의 최소 효과 크기로 둔다.

**DoD:** 재실행 `run.json`의 프롬프트 해시가 2차와 같고, 비교 수치가 decisions.md에 기록된다.

### Task 1 (W4-1): 문맥 어휘 설명과 문맥 질문 방식 실험 (CP-S3 R2·R3·L6)

**Interfaces:**
- 온톨로지: `vocabularies.basis.<axis>`를 `{values: [...], descriptions: {token: str}}` 형태로 확장(구 형식 호환 로더). 조건 정의 `ConditionDef.description: str`, 범위 설명은 `vocabularies.scope_description: str`. 모든 설명은 `origin: synthetic`.
- `extraction_schema(onto, class_id, mode, *, context: Literal["optional", "required_none"]) -> dict`: `optional` = W3 1차 형식(필수 아님), `required_none` = 필수이되 `"none"`을 명시적 선택지로 둔다(R3 대조). 토큰 enum 항목에 설명을 붙인다.

**결정 1(승인 필요) — 설명 작성 규칙:** 헬퍼가 각 토큰의 **의미**를 온톨로지 용어로 한 문장씩 초안한다(예시 문구·개발 문서 표현 금지). 사용자가 검토·승인한다. 도메인 정의가 불확실한 토큰은 `[미검증]`으로 표시하고 설명을 비운다(H3).

**결정 2(승인 필요) — 실험 행렬(개발셋 조정 2회째):**

| 실행 | 어휘 설명 | 문맥 질문 | 비교 대상 |
|---|---|---|---|
| C-desc-opt | 있음 | 필수 아님 | C 1차(설명 없음, 필수 아님) |
| C-desc-none | 있음 | 필수 + `none` 선택지 | C 2차(설명 없음, 필수) |

B는 실행하지 않는다(정규화 비교는 W3로 충분). 각 실행 전 해시를 고정하고, 두 실행 모두 보고한다.

- [ ] 테스트 먼저: (1) 로더가 구·신 어휘 형식을 모두 읽고 설명 없는 토큰을 허용한다. (2) 스키마의 각 토큰 enum에 설명이 실린다. (3) `required_none`에서 문맥 필드가 필수이고 `"none"`이 enum에 있으며, 추출기가 `"none"`을 빈 문맥으로 바꾼다. (4) 프롬프트에 개발 정답의 비고 문구가 들어가지 않는다(개발 정답 `raw_text`·비고 열 문자열이 프롬프트에 부분 문자열로 없음).
- [ ] 사용자 실행: 두 구성을 개발 24건에 실행(각 약 15~20분).
- [ ] 헬퍼 분석: 문맥 키 TP(/97), 문맥 없는 키 TP(/117), 문맥이 붙은 FP 키, 문맥 속성 값 일치(/98), 출현 정밀도. 목표 산술(FP 0일 때 26, P = R일 때 55)과 W4-0 잡음 하한을 함께 표시한다.

**DoD:** 테스트·ruff·mypy 통과, 두 실행의 수치가 보고서 초안과 decisions.md에 기록된다. 이후 W4 기본 추출 설정(문맥 방식)을 결과로 정해 기록한다. 결과가 좋지 않아도 그대로 쓴다.

### Task 2 (W4-2): 검증 결과 모델과 미해결 사유 매핑

**Interfaces:**
- `Code = Literal["E1", "E2", "E3", "E4", "E5", "REVIEW"]`
- `class Finding(StrictModel)`: `code`, `attribute_ids: list[str]`, `occurrences: list[dict]`(원문 위치), `rule_ref: str`(`ontology/ontology.yaml#…`), `reason: str`
- `code_for_unresolved(reason: values.Reason) -> Code`

**결정 3(승인 필요) — 미해결 사유 → 코드:**

| 정규화기 사유 | 코드 | 근거 |
|---|---|---|
| `dimension` | E2 | 계약 E2 "wrong unit dimension" |
| `not_a_number`·`not_integer`·`reversed_range`·`bad_dimensions`·`not_boolean` | E3 | 계약 E3 "malformed typed value or reversed range" |
| `unknown_unit`·`missing_unit`·`condition` | REVIEW | 계약에 코드가 없다. 단위를 추측하지 않으므로 사람 확인 대상으로만 둔다(등록 차단) |

- [ ] 테스트: 사유 9개가 모두 하나의 코드로 대응되고(누락 시 실패), 개발 정답의 E2/E3 관찰을 W3-5 정규화기에 넣으면 정답 코드가 나온다.

**DoD:** 테스트·ruff·mypy 통과.

### Task 3 (W4-3): 결정론 검증기 E1~E5 (FR-09)

**Interfaces:** `validate(onto, class_id, facts, unresolved) -> Validation`, `Validation(StrictModel)`: `findings: list[Finding]`, `missing_required: list[str]`, `presence: Presence`, `status: Literal["ready", "needs_review"]`.

규칙(계약 `issue`):
- **E1**: `policy.missing_required`의 속성 중, 같은 속성에 E2/E3 출현이 **없는** 것만 E1이다. E2/E3만 있는 필수 속성은 `missing_required`에는 넣고 코드는 E2/E3 하나만 쓴다(D-015). 조건부 필수의 분기 값을 모르면 `presence="undetermined"`이고 E1을 내지 않는다(Review Focus 2).
- **E2/E3/REVIEW**: 미해결 출현마다(Task 2 매핑). 같은 속성·코드의 출현은 한 Finding으로 묶는다.
- **E4**: 클래스 `allowed_values`가 있는 속성의 사실 값이 목록 밖일 때. 사실은 남기고(`admissibility`) Finding만 낸다.
- **E5**: 같은 사실 키(`scoring.fact_key`와 같은 정의) 안에 서로 다른 값이 둘 이상일 때. 모든 출현을 Finding에 싣는다. 다른 키(문맥이 다른 값)는 E5가 아니다(Review Focus 1).
- `status`는 Finding이 없고 `presence == "present"`일 때만 `ready`다.

- [ ] 테스트 먼저:
  - (1) 개발 정답 왕복: 각 개발 문서의 정답 사실 + E2/E3 관찰(정규화기로 미해결)을 넣으면, Finding의 (코드, 속성 집합)이 정답 `issues`와 같고 `missing_required`도 정답과 같다. 24건 전부, 정상 문서 12건은 Finding 0이다.
  - (2) 문맥만 다른 두 값은 E5가 아니다.
  - (3) 조건부 분기 값이 없으면 `undetermined`이고 E1이 없다.
  - (4) E2만 있는 필수 속성은 E1이 아니라 E2다.
  - (5) 클래스 `unknown`이면 예외 없이 `needs_review`다.

**DoD:** 테스트·ruff·mypy 통과. 왕복 테스트가 24/24 통과한다(정답 계약을 코드가 재현).

### Task 4 (W4-4): 검증 채점기 G3와 채점기 ID 갱신

**Interfaces:** `score_validation(answer, validation) -> ValidationScore`, `aggregate_validation(scores) -> ValidationMetrics`(코드별 TP/FP/FN·P/R, 정상 문서당 오탐 수, 분모 공개).

**결정 4(승인 필요) — 이슈 일치 규칙:** 계약 `issue_match`(코드 + 속성 ID + 규칙 참조 + 관련 출현 포함)를 다음과 같이 적용한다.
- 코드와 속성 ID 집합은 정확히 일치해야 한다.
- 규칙 참조는 정답이 `data/ontology/dataset-contract.yaml`을, 시스템이 `ontology/ontology.yaml`을 가리키므로 경로 대신 **규칙 종류**(`required_all`·`required_any_groups`·`dimension`·`value_types`·`allowed_values`·`E5`)로 비교한다.
- 출현 포함은 정답 `observation_ids`의 위치를 Finding 출현이 모두 덮을 때(`same_place`)다. E1은 출현 대신 검사 범위로 본다.
- REVIEW Finding은 정답 코드가 없으므로 G3 분모·FP에 넣지 않고 수를 따로 공개한다.

- [ ] 테스트: 정답 이슈를 그대로 Finding으로 만들면 모든 코드 P/R 1.0, 하나 빼면 해당 코드 R만 하락, 정상 문서의 Finding 1개는 오탐 1.
- [ ] `rescore.evaluation_hashes()`에 새 모듈을 넣고 **새 scorer_id**를 decisions.md에 기록한다. W3 실행 8개와 W4-0·W4-1 실행을 새 ID로 재채점해 사실 지표가 그대로인지 확인한다.

**DoD:** 테스트·ruff·mypy 통과, 새 scorer_id 기록, 재채점에서 사실 F1 불변 확인.

### Task 5 (W4-5): 중복·유사 판정기와 채점기 G4 (FR-10)

**Interfaces:** `match(onto, class_id, facts, registry: list[dict]) -> list[Match]`, `Match(StrictModel)`: `registry_id`, `relation: Literal["duplicate", "similar"]`, `evidence: dict`(식별 비교·이름 점수·속성 차이 목록). `score_dedup(query_id, matches, candidates) -> DedupScore`, 3분류 혼동 행렬.

절차(계획서 FR-10):
1. 클래스 블로킹: 같은 클래스의 등록 제품만 본다.
2. 자연키: 제조사(등록명·별칭, `MakerIndex`)와 `model_key`가 같으면 `duplicate`.
3. 그 밖에서 이름 유사도(rapidfuzz)와 핵심 속성 거리로 `similar`.
4. 판정마다 근거를 붙인다.

**결정 5(승인 필요) — similar 기준과 기준선:** similar 임계값은 개발 분할에서만 정하고 고정 시점을 기록한다. 결과는 D-018의 "모델명 시리즈 접두사 규칙 P/R 1.0" 기준선과 나란히 보고한다. 합성 데이터에서 similar는 "같은 합성 계열"로 정의돼 접두사가 그대로 드러나므로(D-016), 이름 유사도가 높게 나와도 일반화 주장을 하지 않는다.

**결정 6(승인 필요) — 의존성 추가:** `uv add rapidfuzz fastapi python-multipart`(사용자 터미널, 네트워크 필요). 버전은 설치 시점 값을 decisions.md에 기록한다.

- [ ] 테스트 먼저:
  - (1) 개발 비교 정답(`comparison-candidates.yaml`, `split: dev`)에 대해 정답 사실로 만든 조회의 duplicate 판정이 정답과 같다.
  - (2) 제조사 별칭·모델명 공백/하이픈 변형도 duplicate다(Review Focus 4).
  - (3) 다른 클래스의 같은 이름은 후보가 아니다.
  - (4) 판정마다 근거가 있다.
  - (5) 채점기는 목록에 없는 등록 제품을 new로 센다(계약 `complete_comparison_labels`).

**DoD:** 테스트·ruff·mypy 통과. 개발 G4 혼동 행렬과 접두사 기준선이 기록된다.

### Task 6 (W4-6): 표준 JSON 출력 (FR-11)

**Interfaces:** `RegistrationResult(StrictModel)`: `document_id`, `class_id`, `class_candidates`, `facts`(W1 후보 사실 형식 + 출현), `unresolved`, `validation: Validation`, `matches: list[Match]`, `status`, `provenance`(파서·모델·프롬프트·사전·온톨로지 해시). `to_json(result) -> dict`, `validate_output(onto, data)`는 클래스 사실 부분을 W1 `build_candidate_model`로 검증하고, 전체를 `RegistrationResult` JSON Schema로 검증한다(`spec_bridge/ontology/schema.py` export와 같은 경로에 스키마 파일을 쓴다).

- [ ] 테스트: 개발 문서 1건의 정답으로 만든 결과가 스키마 검증을 통과하고, 사실 값의 자료형을 깨면 실패하며, `unknown` 클래스 결과도 유효한 JSON이다(Review Focus 3).

**DoD:** 테스트·ruff·mypy 통과, 스키마 파일 생성 명령이 문서화된다.

### Task 7 (W4-7): 처리 함수와 FastAPI 업로드 엔드포인트 (MVP)

**Interfaces:** `process_document(path: Path, document_id: str, provider: JsonProvider | None, *, split_registry: str = "dev") -> RegistrationResult`. 파싱 실패와 LLM 실패는 예외가 아니라 `status="needs_review"`와 실패 사유를 담은 결과다. `POST /documents`(multipart 파일)는 `RegistrationResult` JSON을 돌려준다. 지원하지 않는 형식은 415, 빈 파일은 400이다.

- [ ] 테스트(FakeProvider, `fastapi.testclient`): 개발 XLSX 1건 업로드 → 200과 스키마 유효 JSON, 깨진 파일 → 200 + `needs_review` + 파싱 실패 사유, `.txt` → 415, 빈 파일 → 400. 업로드 파일은 임시 디렉터리에만 쓰고 지운다.
- [ ] 사용자 실행: `uv run uvicorn spec_bridge.api.app:app`(루프백) 후 `curl -F file=@data/synth/inputs/<개발 문서>` → 실제 모델로 JSON 확인(MVP DoD).

**DoD:** 테스트·ruff·mypy 통과, 실제 모델 업로드 1건의 JSON이 스키마 검증을 통과한다(계획서 W4 MVP DoD).

### Task 8 (W4-8): 구성 D — 검증 피드백 재추출 1회

**Interfaces:** `experiment.predict(..., config="D")`: C를 실행한 뒤 검증기를 돌린다. E1·E2·E3·REVIEW Finding이 있는 속성만 모아, Finding 사유와 해당 줄을 붙여 **1회** 재추출한다. 재추출 결과는 그 속성의 사실·미해결만 교체한다(Review Focus 5). E4·E5는 문서 내용 문제라 재추출하지 않는다.

- [ ] 테스트(FakeProvider): 재추출 대상 속성만 프롬프트에 오르고, 다른 속성의 사실은 그대로이며, 재추출이 실패하면 C 결과를 유지하고 실패 사유를 기록한다. 재추출 호출은 문서당 최대 1회다.
- [ ] 사용자 실행: D를 개발 24건에 실행. 헬퍼가 A~D(+ R, 클라우드 진단) 비교표를 새 scorer_id로 갱신하고, D와 C의 차이를 W4-0 잡음 하한과 비교한다.

**DoD:** 테스트·ruff·mypy 통과, D 실행 수치가 기록된다.

### Task 9 (W4-9): W4 보고서와 MVP 판정 자료

- [ ] `docs/reports/w4-validation-dedup.md`: G1(문맥 실험 포함)·G3·G4 수치와 분모, 기준선(R, 접두사 규칙), 잡음 하한, 개발셋 조정 횟수와 해시, 실패·지연. 확인된 것과 가설을 구분한다(W3 보고서 형식).
- [ ] MVP DoD 점검표: 업로드 → 표준 JSON(클래스·정규화 속성·오류·중복). 헬퍼는 판정하지 않고 증거만 모은다.

**DoD:** 보고서가 커밋 가능한 상태다(집계 수치만, 정답 내용 없음).

---

## 승인이 필요한 결정 (요약)

1. **어휘 설명 작성 규칙**: 헬퍼가 온톨로지 용어로 의미만 초안하고 사용자가 승인한다. 불확실하면 `[미검증]`으로 비운다. 개발 문서 문구는 금지한다.
2. **문맥 실험 행렬**: C-desc-opt와 C-desc-none 두 실행(개발셋 조정 2회째). B는 제외한다.
3. **미해결 사유 → 코드**: dimension→E2, 형식 계열→E3, 단위 불명·조건 불일치→REVIEW(등록 차단, G3 분모 밖).
4. **G3 이슈 일치**: 코드·속성 집합은 정확히 일치시키고, 규칙 참조는 규칙 종류로, 출현은 위치 포함으로 본다. REVIEW는 별도 공개한다.
5. **similar 판정**: 개발셋에서 임계값을 고정하고 접두사 기준선과 나란히 보고한다. 일반화 주장은 하지 않는다.
6. **의존성 추가**: rapidfuzz, fastapi, python-multipart.
