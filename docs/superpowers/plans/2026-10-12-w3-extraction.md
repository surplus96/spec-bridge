# W3 매핑·추출·정규화와 첫 비교 실험 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (교육 모드 — 헬퍼가 스크래치 사본에서 검증한 **전체 코드**를 제공하고 사용자가 타이핑·실행한다, 메모리 `education-mode-full-code`). 서브에이전트 실행은 사용자가 요청할 때만. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파싱 블록을 받아 클래스를 고르고(G2), 클래스별 속성을 원문 위치와 함께 추출·정규화하며(G1), 같은 개발셋 입력으로 R·A·B·C 구성을 비교한 첫 결과를 파일로 남긴다.

**Architecture:** 파서 출력(`var/parsed/<split>/`, `parsed_ids`만) → 프롬프트 입력(블록 ID가 붙은 원문 줄) → 분류기(키워드 후보 + LLM 선택, `unknown` 허용) → 추출기(LLM은 값·단위·라벨 문자열과 **근거 블록 ID**만 낸다. 위치는 코드가 블록에서 붙이고, 원문이 그 블록에 없으면 버린다) → 정규화기(결정론: 단위·수치·범위·치수·열거 표시형) → W1 후보 모델 검증 → 평가기(정답 계약 채널별 점수). LLM 호출은 제공자 어댑터 하나로만 나가며 감사 기록과 오프라인 가드를 거친다.

**Tech Stack:** Ollama + **EXAONE 3.5 7.8B**(`exaone3.5:7.8b`, Q4_K_M, 기본 — D-025) / 대안 `qwen3:8b`·`exaone3.5:2.4b`·`qwen3:4b`, `ollama` Python 클라이언트 0.6.x(구조화 출력 `format=<JSON Schema>`), pint, Pydantic v2, pytest

**Spec:** [계획서 W3·FR-06~08·FR-13·6-1·6-2·G1·G2·NFR-01/03/04/05](../../spec-bridge-project-plan.md), [정답 계약](../../../data/synth/answer-contract.yaml)(채점 채널·키·허용차), decisions.md D-020~D-024·`CP-S1`·`CP-S2`(이월 항목·W3 입력 계약), [착수 리서치 §로컬 실행 가설](../../spec-bridge-kickoff-research.md)

## Global Constraints

- **개발 분할 24건만** 실행·튜닝·보고한다. 테스트 16건은 W3에서 실행하지 않는다(W6 최종 평가, D-020). 프롬프트·사전·임계값은 개발 결과로만 정하고 고정 시점을 기록한다.
- 모델 입력은 **파싱 블록과 클래스·속성 정의(온톨로지)뿐**이다. case-plan·정답·비교 정답·작성 규칙·등록 목록(W3에서는 불필요)은 넣지 않는다(CP-S2 W3 입력 계약).
- 파싱 실패 문서는 unknown으로 남기고 점수 분모에서 빼지 않는다(실패 = FN, 정답 계약 `generation_failures`).
- LLM이 위치를 만들지 않는다. 모든 출현은 실제 블록 ID에 연결되고, 원문 문자열이 그 블록에 토큰 단위로 있어야 한다(CP-S2 P2 재추적 계약).
- 정규화는 결정론 코드만 한다. 기억에 의존한 환산·별칭을 넣지 않는다(H3). `ton`·`bhp`는 문서 정의 없이는 환산하지 않는다(정답 계약 unit_policy).
- 모든 LLM 호출은 `temperature=0`, 고정 seed, 모델 digest·프롬프트 해시·옵션·지연·토큰 수를 감사 기록에 남긴다(NFR-03/04). 클라우드 행은 "미실행"으로 표시한다(계획서 6-2).
- `OFFLINE=1`이면 루프백 외 주소로 나가는 제공자를 거부한다(NFR-01). 커밋·푸시는 사용자 요청 시에만. 완료 판정은 `uv run pytest`, `uv run ruff check .`, `uv run mypy spec_bridge tests`로만.

## Review Focus

1. **근거 없는 값(환각)**: LLM이 문서에 없는 값이나 존재하지 않는 블록 ID를 내면 사실로 만들지 않고 "검증 실패 출현"으로 세어 보고한다 → Task 4 테스트.
2. **적용 대상·구성품 언급에 끌린 분류**: 과급기 문서의 `two-stroke engines`, 엔진 문서의 구성품 줄, 분리기의 `feed pump` 때문에 다른 클래스로 가지 않는다(CP-S1 질문 1) → Task 3 혼합 문맥 테스트.
3. **같은 조건의 상충 값(E5)과 다른 조건의 복수 값**: 하나로 합치거나 고르지 않고 모두 출현으로 남긴다 → Task 4·6 테스트.
4. **LLM 출력 깨짐·시간 초과**: JSON 파싱 실패·스키마 위반·타임아웃은 재시도 1회 후 문서 단위 실패로 기록하고 실행을 계속한다(분모 유지) → Task 1·7 테스트.
5. **조건 수량의 단위**(CP-S1 L5): 조건 `Quantity.unit`이 자유 문자열이므로 정규화기가 조건별 허용 차원(주파수=Hz, 온도=degC, 절대압=mbar, 점도=cSt)으로 확인하고 어긋나면 사실을 만들지 않는다 → Task 5 테스트.

---

## 구성 정의 (6-2 비교 실험, 입력 정책은 모두 동일)

| 구성 | 분류 | 추출 출력 | 정규화 | 비고 |
|---|---|---|---|---|
| **R. 규칙 기준선** | 키워드 점수 1위 | 개발셋 라벨 사전으로 라벨 칸·줄을 속성에 대응, 옆 칸/같은 줄의 값·단위 | C와 같은 결정론 정규화 | LLM 없음. CP-S2 리뷰 요구(라벨 사전 기준선과 함께 보고) |
| **A. LLM 단독** | LLM이 자유 JSON에 class 포함 | `{"class":…, "attributes": {이름: 값}}` 자유 형식, 근거 블록 ID 요청 | 없음. 키는 온톨로지 속성 ID와 casefold 정확 일치만 인정 | 계획서 "자유 형식" |
| **B. + 온톨로지 스키마** | 분류기(키워드 후보 + LLM 선택) | 클래스별 JSON Schema 구조화 출력. **LLM이 직접** 정규 단위·자료형 값을 낸다 | 없음 | 스키마가 구조를 강제 |
| **C. + 결정론 정규화** | B와 같음 | 클래스별 스키마이되 값·단위는 **원문 문자열**(value_text, unit_text) | 결정론 정규화기 | 가설: 표기 변형의 F1 손실 감소 |
| D. + 검증 피드백 | — | — | — | W4(검증기 이후) |

기준·조건(basis/condition) 토큰은 B·C 모두 온톨로지 어휘 enum으로 LLM이 고른다(C의 차이는 값·단위·열거 표시형 정규화에 한정).

---

## 파일 구조

| 경로 | 책임 |
|---|---|
| `spec_bridge/llm/provider.py` | `JsonProvider` 프로토콜, `OllamaProvider`, 재시도·타임아웃, 오프라인 가드 |
| `spec_bridge/llm/audit.py` | 호출 감사 기록(JSONL): 모델·digest·프롬프트 해시·옵션·지연·토큰·결과 |
| `spec_bridge/extract/prompt_input.py` | 블록 → `[B12] (table r3c2 · Technical data) text` 줄, 블록 색인 |
| `spec_bridge/extract/classifier.py` | 키워드 후보 점수 + LLM 선택 → `ClassPrediction` |
| `spec_bridge/extract/schemas.py` | 구성 B/C용 LLM 출력 스키마(온톨로지에서 생성) |
| `spec_bridge/extract/extractor.py` | LLM 응답 → 출현(블록 위치 부착·원문 검증) → 후보 사실 |
| `spec_bridge/normalize/values.py` | 단위(pint)·수치·범위·치수·불리언·열거 표시형 정규화 |
| `spec_bridge/normalize/dictionary.py` | 개발셋 정답에서 열거 표시형·라벨 사전 생성(고정 파일로 저장) |
| `spec_bridge/eval/locations.py` | `tests/parse/goldmatch.py`의 위치·토큰 대조를 평가기로 이동 |
| `spec_bridge/eval/scoring.py` | 정답 계약 채널별 점수: 클래스(top-1/3, unknown), 정규 사실 P/R/F1(속성·클래스·micro/macro), 출현 회수 |
| `spec_bridge/eval/experiment.py` | 구성 R/A/B/C 실행, 실행 메타데이터, `var/eval/<run_id>/` 저장 |
| `ontology/dev-dictionary.yaml` | 개발셋에서 만든 정규화 사전(생성물, 고정 시점·해시 기록) |
| `docs/reports/w3-first-comparison.md` | 첫 비교표(G1·G2, 기준선, 실패·지연) |

---

### Task 0 (W3-0): LLM 실행 환경 관문

**DoD:** 아래 시험이 개발 문서 1건에서 스키마에 맞는 JSON을 돌려주고, 모델 digest·지연·메모리를 기록한다.

- [ ] Ollama 서버 실행·모델 준비(사용자): `ollama serve`(또는 앱), `ollama pull exaone3.5:7.8b`, `ollama show exaone3.5:7.8b`로 양자화·컨텍스트 확인, `ollama list`로 digest 기록.
- [ ] 클라이언트: `uv add ollama`. 샌드박스 안 헬퍼 실행은 로컬호스트 접속이 막혀 있어 LLM 실행 확인은 사용자 터미널 결과로 한다.
- [ ] 시험(임시 `var/spike_llm.py`): 개발 문서 1건의 블록을 줄로 만들어 `format=<간단한 JSON Schema>`, `options={"temperature": 0, "seed": 7, "num_ctx": 8192}`로 1회 호출 → 응답 JSON 파싱, 근거 블록 확인 수, 토큰·지연, `ollama ps` 메모리·GPU 비율, 메모리 압박·스왑 기록.
- [ ] 관문: 구조화 출력 실패·메모리 압박(스왑)·문서 1건 5분 초과(NFR-04) 중 하나면 멈추고 보고 → 같은 입력으로 `qwen3:8b`·경량 대안 비교(D-025).

### Task 1 (W3-1): 제공자 어댑터·감사 기록·오프라인 가드

**Interfaces:**
- `class JsonProvider(Protocol)`: `def complete_json(self, *, system: str, user: str, schema: dict[str, Any] | None, task: str) -> dict[str, Any]`
- `OllamaProvider(model: str, host: str = "http://127.0.0.1:11434", timeout_s: float = 300, retries: int = 1, audit: AuditLog)`
- `class LlmError(Exception)`(속성 `task`, `reason`) — JSON 깨짐·스키마 위반·시간 초과가 재시도 후에도 남으면
- `AuditLog(path: Path).record(entry: dict)`; 항목: `task, model, model_digest, prompt_sha256, schema_sha256, options, started_at, latency_s, prompt_tokens, completion_tokens, status, error`
- 테스트용 `FakeProvider(replies: list[dict | Exception])`

**테스트(먼저):** 깨진 JSON → 1회 재시도 후 `LlmError`; 성공 시 감사 1행(프롬프트 원문 대신 해시); `OFFLINE=1`에서 `host="http://10.0.0.5:11434"` 생성자 거부; 루프백(`127.0.0.1`, `localhost`, `::1`)은 허용; 감사 기록에 temperature 0·seed 기록.

### Task 2 (W3-2): 프롬프트 입력 구성

**Interfaces(D-026 변경):** `render_lines(doc: ParsedDocument) -> tuple[str, list[list[Block]]]` — 시각적 줄(문단 1줄, 표 행 1줄: 형식별 행 정보 — PDF y 중심, DOCX table/row, XLSX 셀 행)마다 `L{n}` ID, 줄 형식 `[L9] Cylinders | 6 | — | —`. 모델은 줄만 지목하고 칸은 코드가 찾는다.

**테스트:** 같은 문서 → 같은 문자열(결정론); 모든 블록이 정확히 한 줄; 원문(`—`, `×`, 끝 공백 제외 정책 명시) 보존; 정답·사례 정보가 문자열에 없음(입력 계약).

### Task 3 (W3-3): 분류기 (G2)

**Interfaces:** `keyword_scores(onto, doc) -> list[tuple[str, float]]`; `classify(onto, doc, provider | None, k=3) -> ClassPrediction(top_k: list[tuple[str, float]], chosen: str | Literal["unknown"], method: Literal["keyword", "llm"], reason: str)`

- 키워드 점수: 온톨로지 `keywords`·`label`을 **제목·첫 절**에 가중, 본문 전체는 낮은 가중. 구성품 줄(`Included component`)·조건 문구는 감점하지 않고 낮은 가중으로만 센다.
- LLM은 top-k 후보와 `unknown` 중에서만 고른다(enum 스키마). 후보 밖 답은 `LlmError`.
- **알려진 지름길(기록)**: 모든 합성 문서에 `Product: Marine … turbocharger` 같은 제품 줄이 있어 키워드만으로 거의 맞힌다. 키워드 단독 정확도를 R행으로 함께 보고한다.

**테스트:** 개발 24건 키워드 top-1 정확도 기록(기대값을 하드코딩하지 않고 보고); 과급기 개발 문서(`two-stroke engines` 포함)는 Turbocharger 유지; 키워드 근거가 없는 합성 문서(제목·제품 줄 제거) → LLM 없음이면 `unknown`; FakeProvider가 후보 밖 클래스를 내면 `LlmError`.

### Task 4 (W3-4): 출력 스키마와 추출기 (구성 A·B·C)

**Interfaces:**
- `extraction_schema(onto, class_id, mode: Literal["B", "C"]) -> dict` — 항목 `{attribute: enum, value…, unit…, basis: {키: enum}, condition: {…}, scope: str, evidence: [블록 ID] (min 1)}`. B는 값이 자료형·정규 단위 enum, C는 `value_text`·`unit_text` 문자열.
- `extract(onto, doc, class_id, provider, mode) -> Extraction(facts: list[dict], rejected: list[RejectedOccurrence], llm_failed: bool)`
- `RejectedOccurrence(attribute, value_text, evidence, reason: Literal["unknown_block", "text_not_in_block", "schema"])`

**규칙(D-026):** LLM은 근거로 줄 ID만 낸다. 코드가 그 줄에서 값 토큰(소수점 포함 숫자 경계)을 가진 블록이 정확히 하나일 때 그 블록의 `Block.location`을 출현 위치로 쓰고, 없거나 여럿이면 `RejectedOccurrence(reason="not_in_line" | "ambiguous_in_line")`. B·C 모두 원문 증거 검사를 한다(B는 값의 원문이 없으므로 LLM이 함께 낸 `raw_text`를 검사). 같은 속성·조건의 서로 다른 값은 각각 사실로 남긴다(E5).

**테스트(FakeProvider):** 정상 응답 → W1 후보 모델 검증 통과·위치 부착; 없는 블록 ID·블록에 없는 원문 → 사실 0·`rejected` 1(Review Focus 1); 같은 조건 두 값 → 사실 2; 스키마 위반 2회 → `llm_failed=True`(문서는 unknown). 실제 LLM 통합 시험(CP-S1 L7)은 `@pytest.mark.llm`로 1건, 사용자 터미널에서 실행.

### Task 5 (W3-5): 결정론 정규화기와 개발 사전

**Interfaces:** `normalize_fact(onto, attribute_id, value_text, unit_text, dictionary) -> NormalizedValue | Unresolved(reason)`; `build_dev_dictionary(dev answers) -> dict`(열거 표시형 → 정규 토큰, 라벨 → 속성)을 `ontology/dev-dictionary.yaml`로 저장하고 해시를 실행 메타데이터에 남긴다.

- 단위: 온톨로지 `units` 표기와 pint 표현으로 정규 단위 환산. 차원이 다르면 Unresolved(E2 후보로 W4 전달). `ton`/`bhp` 무정의 환산 금지.
- 수치·범위(`a to b`, 역전은 Unresolved)·치수(`L × W × H`)·불리언(`Yes/No`)·목록(`,`).
- 열거 표시형(`fuel oil treatment`, `sea water`, `generating-set` …): **개발 정답의 관찰 raw → 정답 값**에서만 만든 사전. 사전에 없는 표시형은 원문 그대로 두고 Unresolved가 아니라 "미해석 열거"로 표시(E4 판정은 W4).
- 조건 수량 단위(Review Focus 5): 조건별 허용 차원 확인.

**테스트:** 정답 계약의 예(`48 rpm`을 출력 속성 단위로 환산하지 않음), 역전 범위 Unresolved, 사전이 개발 정답만으로 만들어짐(테스트 분할 ID가 입력에 없음), `Final pressure` 같은 미검증 합성 별칭이 사전 근거로 쓰이지 않음(사전은 정답 관찰만).

### Task 6 (W3-6): 평가기 v1 (FR-13)

**Interfaces:**
- `spec_bridge/eval/locations.py`: `same_place`, `contains_token`(goldmatch에서 이동, 테스트 도우미는 이를 import)
- `score_document(answer, prediction) -> DocScore`; `aggregate(scores) -> Metrics`(채널: `class_mapping`, `normalized_facts`(P/R/F1, 속성별·클래스별·micro/macro), `observation_retrieval`(출현 회수)), 분모 공개.

**정답 계약 규칙 구현:** 사실 키 = (input_id, attribute, basis, condition, scope); 같은 키의 정답 값은 원자 집합(E5는 전부 맞아야 일치); 수치 허용차 abs 1e-6·rel 0; 목록은 순서 무시, 범위·치수는 원자 비교; E2/E3 잘못된 출현은 정규 사실 분모에서 제외(관찰 분모에는 포함); E4 값은 정규 사실 분모에 포함; 정답에 없는 대상 속성 사실은 FP; 파싱·LLM 실패 문서의 정답 사실은 전부 FN.

**테스트:** 정답을 그대로 예측 → 모든 채널 1.0; 사실 하나 누락 → R만 하락; 조건이 다른 같은 값 → 불일치; E5 한 값만 → 그 키 불일치; 실패 문서 → FN 계산; 분모가 정답 파일 집계와 같다.

### Task 7 (W3-7): 실험 실행기와 첫 비교표

**Interfaces:** `run_experiment(config: Literal["R", "A", "B", "C"], split: Literal["dev"], provider) -> RunResult`; `python -m spec_bridge.eval.experiment --config B --split dev` → `var/eval/<run_id>/{predictions/*.json, metrics.json, run.json}`. `run.json`: 구성, 모델·digest, 프롬프트·스키마·사전 해시, 옵션, 재시도, 실패 문서, 문서당 지연(cold/warm), 토큰 합, 파싱 실행 환경(`_summary.json` environment), git 커밋.

- [ ] **테스트(먼저, FakeProvider):** 한 문서에서 `LlmError`가 나도 나머지 문서가 처리되고, 실패 문서는 `run.json`의 실패 목록에 남으며 그 정답 사실이 전부 FN으로 집계된다(Review Focus 4). 파싱 요약의 `parsed_ids`에 없는 문서도 같은 방식으로 FN.
- [ ] R·A·B·C를 개발 24건에 실행(사용자 터미널, LLM).
- [ ] `docs/reports/w3-first-comparison.md`: 구성별 G2(top-1/3·unknown), G1(정규 사실 micro/macro F1, 속성·클래스별), 출현 회수, 실패 수, 지연, 기준선(R, 그리고 D-018 기록: 라벨 사전 91.6%·similar 접두사 P/R 1.0은 W4 대상). 1차 목표 F1 ≥ 0.8 달성 여부와 미달 원인을 그대로 기록. 결과가 기준선보다 0.3 이상 급등하거나 1.0이면 누수부터 의심(H2 트리거).

**DoD(계획서 W3):** 개발셋 G1·G2 첫 수치가 파일로 저장된다.

### Task 8 (W3-8): NFR-01 네트워크 관측 (CP-S2 이월)

- 단위: 소켓 연결을 가로채 루프백 외 연결 시도를 실패시키는 픽스처로 R·C(FakeProvider)와 파서 전 과정을 돌려 외부 시도 0회 확인.
- 실제: 사용자 터미널에서 `OFFLINE=1` + 네트워크 차단 상태로 개발 2건을 C로 실행하고, OS 관측(`nettop` 등)으로 Ollama·Python의 비루프백 연결을 기록. "차단 성공"과 "시도 0회"를 구분해 보고(착수 체크리스트 E4).

### Task 9 (W3-9): 🔶 CP-S3 검토 패키지

계획서 H4 CP-S3 질문(매칭 정책 사전 고정, 실패를 분모에서 빼지 않음, 첫 비교 해석 과장 여부)에 근거·수치·확신 낮은 지점을 붙인다. 헬퍼는 통과 판정을 하지 않는다.

---

## 승인이 필요한 결정

1. **공유 모듈**: 원본 경로가 없으므로(D-020) 제공자 어댑터·감사 기록·오프라인 가드·평가 실행기를 이 저장소 안에 최소 구현으로 만든다.
2. **구성 R(규칙 기준선) 추가**: 계획서 6-2의 A~D에 기준선 행을 더한다(CP-S2 리뷰 요구). LLM 우수성 주장은 R 대비로만 한다.
3. **구성 A의 채점 방식**: 자유 형식 키를 온톨로지 속성 ID와 casefold 정확 일치로만 인정한다(동의어 매핑을 하면 A가 B·C와 섞인다).
4. **B·C의 기준·조건**: 둘 다 LLM이 어휘 enum으로 고르고, C의 차이는 값·단위·열거 표시형 정규화로 한정한다.
5. **개발 사전**: 열거 표시형·라벨 사전을 개발 정답 관찰에서만 생성해 고정한다(정답 계약 `variation_aliases`). 생성기 작성 규칙(보관본)은 쓰지 않는다.
6. **W3 결과 보고 위치**: 수치는 `var/eval/`(재생성 가능)와 커밋되는 `docs/reports/w3-first-comparison.md`(집계 수치만, 정답 내용 없음).
