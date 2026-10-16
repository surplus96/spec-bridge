# W4-R RAG 기반 의미 매핑 (구성 E) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. 교육 모드로 진행한다. 헬퍼가 스크래치에서 검증한 **전체 코드**를 단계마다 제공하고, 새 개념은 그 단계에서 구체적으로 설명한다. 사용자가 직접 수정을 요청한 단계만 헬퍼가 구현한다. W3·W4 계획과 같은 형식으로, 이 문서는 작업 단위의 인터페이스·테스트·DoD를 고정하고, 코드는 실행 시점에 제공한다. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 값 하나마다 그 줄의 원문과 **검색된 개발 정답 예시·온톨로지 정의**를 LLM에 주고 한정 정보(기준·조건·범위)를 받는다. 근거 구절은 코드가 확인한다(구성 E). 이렇게 해서 "코드 규칙으로 풀기 어려운 의미 매핑을 LLM + RAG가 해결하는가"(G5 핵심 가설, D-042)를 같은 하네스로 측정한다.

**Architecture:**

```
파싱 블록 ─▶ 분류 ─▶ C(optional) 값 추출 ─▶ 값마다:
                                           ├─ 질의 = 그 줄 원문 (+ 질의 재작성 변형)
                                           ├─ 검색기: BM25 ∥ 임베딩(Chroma/FAISS) ─▶ 하이브리드 결합
                                           │         (평가 시 같은 계열 제외)
                                           ├─ 부모 문맥: 표 머리글 · 절 제목 · 행 전체
                                           ├─ 프롬프트: 어휘 정의 + 검색 예시(동적 few-shot) + 부모 문맥
                                           ├─ LLM 구조화 출력: 기준·조건·범위 + 필드별 근거 구절
                                           └─ 코드 검증: 근거 구절 실재 · 어휘 · 조건 단위 차원
                                                 └ 실패 → 비움 + "확인 필요"(지어내지 않음)
                    ─▶ 결정론 정규화 ─▶ 사실(키에 한정 정보 포함) ─▶ 채점(scorer_id 고정)
```

LLM 호출은 기존 제공자 어댑터(`JsonProvider`)를 LCEL `Runnable`로 감싸서 쓴다. 감사 기록·오프라인 가드·결정성(잡음 0, D-038)을 유지하기 위해서다. 검색 부품(BM25, 벡터 저장소, 앙상블, Multi-Query)은 LangChain 구성요소를 쓴다.

**Tech Stack:** 기존 + LangChain(`langchain-core`, `langchain-ollama`, `langchain-community`, `langchain-chroma`), `chromadb`, `faiss-cpu`, `rank-bm25`, Ollama 로컬 임베딩 모델(후보: `bge-m3`, `nomic-embed-text`). 정확한 패키지·모듈 경로·버전·임베딩 차원은 R0에서 설치 후 실측해 decisions.md에 기록한다(기억으로 고정하지 않는다).

**Spec:** [계획서 5-1(개정)·6-2 구성 E·G5](../../spec-bridge-project-plan.md), decisions.md **D-041·D-042**(개편 결정, 사전 검증 수치, 누수 통제), D-038(잡음 0), D-039(어휘 설명·생성 규칙 겹침 한계), [W3 보고서 §8·§9](../../reports/w3-first-comparison.md), [CP-S3 검토](../../reviews/cp-s3-review-result.md) L6.

## 새로 도입하는 개념 (이 프로젝트에서의 뜻)

| 개념 | 일반적 뜻 | spec-bridge에서의 구체적 쓰임 |
|---|---|---|
| **RAG** (Retrieval-Augmented Generation) | 생성 전에 관련 자료를 검색해 프롬프트에 넣는 방식 | 값 하나를 해석할 때, 비슷한 줄을 정답과 함께 보여 주는 "참고 사례"를 검색해 넣는다 |
| **지식 베이스(KB)** | 검색 대상 문서 모음 | ① 개발 분할 정답 예시: 줄 원문 → 정답 한정 정보. ② 온톨로지 어휘 정의(D-039). 테스트 분할은 절대 넣지 않는다 |
| **청크 / 부모 문서** | 검색 단위 / 검색 뒤 실제로 넘길 더 큰 단위 | 청크 = 시각적 한 줄(`group_lines`가 이미 만든다). 부모 = 그 줄이 속한 표의 머리글 + 절 제목 + 행 전체. "이 칸이 비고 칸"이라는 구조 정보를 주기 위해서다 |
| **임베딩 모델 · 차원** | 문장을 고정 길이 벡터로 바꾸는 모델과 그 벡터 길이 | 줄 원문을 벡터로 바꿔 의미가 비슷한 줄을 찾는다. 로컬 Ollama 모델만 쓴다(NFR-01). 차원·검색 재현율·지연을 후보별로 비교한다 |
| **벡터 DB (Chroma · FAISS)** | 벡터 근접 검색 저장소 | KB 임베딩을 적재한다. Chroma는 메타데이터 필터(같은 계열 제외)와 영속 저장이 쉽다. FAISS는 메모리 내 고속 검색이다. 같은 임베딩으로 둘을 비교한다 |
| **BM25** | 단어 빈도 기반 어휘 검색 | "R1", "cSt", "dry", "per" 같은 **정확한 기호·약어**를 잘 잡는다. 사전 검증(어휘 겹침만으로 top-3 82%)이 근거다 |
| **하이브리드 검색** | 어휘 검색과 의미 검색 결과를 합침 | BM25 + 임베딩 결과를 순위 융합한다. 기호는 BM25가, 바꿔 쓴 표현("rated output" ↔ "motor rated")은 임베딩이 잡는 보완 관계를 기대한다 |
| **Multi-Query · Rewriting** | 질의를 여러 형태로 다시 써서 재현율을 높임 | 비고 한 줄을 축별 질의(기준·조건·범위)나 세미콜론 조각으로 나눠 검색한다. LLM 재작성 변형과 규칙 분할 변형을 비교한다 |
| **Parent Document Retriever** | 작은 청크로 찾고 큰 부모를 반환 | 줄로 찾고, 프롬프트에는 머리글·절 제목이 붙은 부모 문맥을 넣는다 |
| **Self-RAG** | 모델이 검색 필요성·관련성·근거 충실도를 스스로 판정 | ① 검색 예시가 이 줄에 맞는지 LLM이 고르고, ② 각 필드에 근거 구절을 인용하게 한다. ②는 코드가 강제 검증한다. 모델의 자기 판정만 믿지 않는다 |
| **동적 few-shot** | 질의마다 다른 예시를 프롬프트에 넣음 | 고정 예시(정적 few-shot)가 아니라 검색된 예시다. 같은 계열·같은 문서 예시는 평가에서 뺀다 |
| **LCEL** | LangChain의 `Runnable` 파이프 조합 문법 | `질의 \| 검색 \| 프롬프트 \| LLM(제공자 래핑) \| 파서 \| 검증`을 한 체인으로 쓴다. 단계 교체(검색기 변형)가 실험 변수가 된다 |
| **근거 구절 검증 (하네스)** | LLM 출력을 원문과 대조해 검증 | 한정 정보의 각 필드는 줄·라벨·비고에 실제로 있는 구절을 인용해야 한다. 없으면 버리고 "확인 필요"로 남긴다(W4-1의 범위 지어내기 차단) |
| **leave-family-out 평가** | 같은 그룹을 학습·검색에서 빼고 평가 | 개발 문서를 평가할 때 같은 제품 계열의 예시를 검색에서 제외한다. 자기 누수를 막고 W6 전에 일반화를 추정하기 위해서다 |
| **RAG 품질 평가** | 검색·생성 단계별 지표 | 검색: 정답과 같은 한정 정보 예시의 recall@k와 MRR. 생성: 근거 충실도(인용 구절 실재율). 최종: 문맥 키 TP(/97), 지어낸 문맥 수, 사실 F1 |

## Global Constraints

- 지식 베이스는 **개발 분할 정답 + 온톨로지 정의만**으로 만든다. 테스트 분할 ID·정답·입력은 KB 생성기가 거부한다(테스트로 강제).
- 개발 평가에서는 질의 문서와 **같은 계열(family_id)의 예시를 검색에서 제외**한다. 운영(실제 처리)에서는 개발 KB 전체를 쓴다. W6 테스트 평가에서도 개발 KB 전체를 쓴다.
- 모든 임베딩·LLM 호출은 로컬(Ollama)이다. 벡터 DB는 텔레메트리를 끄고, 네트워크 가드 테스트로 외부 시도 0회를 확인한다(NFR-01). 클라우드는 D-034 진단 경로로만 쓴다.
- LLM은 해석만 하고, 근거 구절 실재·어휘 소속·조건 단위 차원·수치 파싱은 코드가 검증한다. 검증에 실패한 한정 정보는 지어내지 않고 비우며 "확인 필요"로 남긴다(원칙 3·4).
- 채점기 `scorer_id f8355d4a3361`이 기준이다. 한정 정보 지표를 추가하면 새 ID를 기록하고 기존 실행을 재채점해 나란히 보고한다(D-036).
- 조정 예산은 다음과 같다(D-042 누수 통제).
  - 검색 설정은 생성 없이 검색 진단 지표(R3)로만 1회 고른다.
  - 생성 프롬프트는 1회 고정 후 변형 실험(ablation)만 한다.
  - 해시·조정 횟수를 실행마다 기록한다.
- 기준선은 R(코드 규칙), C(zero-shot, optional), 클라우드 진단(D-034)이다. LLM + RAG 우위는 같은 scorer_id·같은 분모에서만 주장한다.
- 완료 판정은 `uv run pytest -q`, `uv run ruff check .`, `uv run mypy spec_bridge tests`로만 한다. 커밋은 사용자 요청 시에만 한다.

## Review Focus

1. **자기 누수**: 질의 문서 자신이나 같은 계열의 예시가 검색되면 점수가 부풀려진다. 평가 모드에서는 반드시 제외된다 → R2 테스트.
2. **예시 값 복사**: 검색 예시의 수치·범위(예: 예시 줄의 기준 온도)를 현재 줄에 그대로 옮기는 환각. 근거 구절이 현재 줄에 없으면 버린다 → R4 테스트.
3. **KB에 테스트 분할 혼입**: 생성기·적재기 어느 쪽에서도 split ≠ dev인 항목을 거부한다 → R1 테스트.
4. **벡터 DB·임베딩의 외부 통신**: Chroma 텔레메트리, 임베딩 모델 다운로드 같은 숨은 네트워크 호출. 오프라인 가드에서 0회여야 한다 → R0 테스트.
5. **검색 결과가 없거나 관련 없을 때**: 빈 검색이나 낮은 관련도에서도 체인이 실패하지 않고, 지어내지 않으며, 비운다 → R4·R5 테스트.

---

## 작업 목록

| ID | 작업 | 주체 | 산출물 |
|---|---|---|---|
| R0 | 의존성·로컬 임베딩 준비, 오프라인 검증 | 사용자 설치 + 교육 모드 | 버전·차원 기록, 네트워크 가드 테스트 |
| R1 | 지식 베이스 구축 | 교육 모드 | `var/rag/kb-dev.jsonl` + 해시 |
| R2 | 검색기 (BM25 · 임베딩 × Chroma/FAISS · 하이브리드 · 부모 문맥) | 교육 모드 | 검색기 팩토리, 계열 제외 필터 |
| R3 | 검색 품질 진단과 검색 설정 선택 | 교육 모드 + 사용자 실행 | recall@k·MRR·지연 표, 선택 기록 |
| R4 | 한정 정보 RAG 체인 (LCEL) + 근거 구절 검증 | 교육 모드 | `qualify(...)` 체인 |
| R5 | Self-RAG 판정 단계 | 교육 모드 | 관련성 판정·지지 판정 변형 |
| R6 | 구성 E 실행기 통합과 한정 정보 지표 | 교육 모드 | `--config E`, 새 scorer_id |
| R7 | 실험 행렬 실행 (ablation) | 사용자 실행 + 헬퍼 분석 | 비교표 |
| R8 | 확장 판단: 표시형·라벨 매핑 RAG | 결정 후 | 개발 사전 대체 실험 계획 |
| R9 | W4-R 보고서 | 헬퍼 | `docs/reports/w4r-rag-semantic-mapping.md` |

## 파일 구조

| 경로 | 책임 |
|---|---|
| `spec_bridge/rag/__init__.py` | 패키지 |
| `spec_bridge/rag/knowledge.py` | KB 항목 모델(`KbExample`, `KbDefinition`), 개발 정답 → KB 생성, 분할 가드, JSONL 저장·해시 |
| `spec_bridge/rag/retrieval.py` | 검색기 팩토리: `bm25`, `dense(store, embedding)`, `hybrid`, 계열 제외 필터, 부모 문맥 |
| `spec_bridge/rag/diagnose.py` | 검색 품질 진단: recall@k, MRR, 지연, 임베딩 차원 |
| `spec_bridge/rag/qualifiers.py` | LCEL 체인: 질의 → 검색 → 프롬프트 → 제공자 → 파서 → 근거 검증 |
| `spec_bridge/rag/selfrag.py` | 관련성 판정·지지 판정 |
| `spec_bridge/llm/runnable.py` | `JsonProvider`를 LCEL `Runnable`로 감싸는 어댑터(감사·가드 유지) |
| `spec_bridge/eval/experiment.py` (수정) | 구성 E, 검색·체인 옵션, `run.json` 기록 |
| `spec_bridge/eval/qualifier_scoring.py` | 한정 정보 지표(문맥 키 TP, 지어낸 문맥, 근거 충실도, 검색 적중) |
| `tests/rag/` | 위 모듈 테스트 |

---

### Task R0: 의존성·로컬 임베딩 준비와 오프라인 검증

**설명:** RAG에는 임베딩 모델, 벡터 저장소, 검색 부품이 새로 들어온다. 이들 중 일부는 기본 설정으로 외부 통신을 할 수 있다. 예를 들어 벡터 DB의 사용 통계 전송이나 임베딩 모델의 자동 다운로드다. 그래서 설치 직후, 기존 NFR-01 가드로 "외부 시도 0회"를 먼저 확인한다.

- [ ] 사용자 터미널:
  - `uv add langchain-core langchain-ollama langchain-community langchain-chroma chromadb faiss-cpu rank-bm25`
  - `ollama pull bge-m3`, `ollama pull nomic-embed-text`
- [ ] 헬퍼: 설치된 버전과 실제 모듈 경로를 확인해 decisions.md에 기록한다. 앙상블·Multi-Query 검색기의 위치는 LangChain 버전에 따라 다르므로 실측한다.
- [ ] 테스트(`tests/rag/test_offline.py`, 기존 `outbound` 가드 재사용, `RUN_LLM=1`일 때만):
  - 두 임베딩 모델로 문장 2개를 임베딩해 차원을 기록한다.
  - Chroma(텔레메트리 끔)와 FAISS에 적재·검색한다.
  - 이 과정에서 외부 시도가 0회여야 한다.

**DoD:** 테스트·ruff·mypy 통과, 버전·차원·텔레메트리 설정이 decisions.md에 기록된다.

### Task R1: 지식 베이스 구축

**설명:** KB 항목은 "이런 줄이면 한정 정보는 이렇다"는 **해결된 사례**다. 모델이 따라 할 출력 형식과 같은 모양으로 저장해야 few-shot 예시로 바로 쓸 수 있다. 그래서 수량 조건은 문서에 쓰인 형태(`"20 degC"`)로, 범위는 문서 구절(`"engine without generator"`)로 저장한다. 정규 토큰 변환은 코드(정규화기)가 한다.

**Interfaces:**
- `class KbExample(StrictModel)`: `example_id`, `doc_id`, `family_id`, `split: Literal["dev"]`, `attribute`, `line_text`(청크), `parent_text`(머리글·절 제목·행), `label_text`, `qualifiers`(모델 출력 형식: `basis`·`condition`·`scope`), `evidence`(필드별 근거 구절)
- `class KbDefinition(StrictModel)`: 어휘 축·토큰 정의(D-039의 `vocabularies.descriptions`)
- `build_kb(answers, parsed_dir) -> list[KbExample]`, `save_kb(path) -> sha256`, `load_kb(path)`

**근거 구절(evidence)의 출처:** 정답 파일에는 "어느 구절이 어느 축의 근거인가"가 없다. 그래서 예시의 `evidence`는 정답 한정 정보와 줄 원문으로 결정론 코드가 찾을 수 있는 경우만 채우고(예: 범위 구절이 줄에 그대로 있음), 못 찾으면 비운다. 이 항목은 W4-R 설계에서 확신이 가장 낮은 지점이라 R1 실행 후 채움 비율을 보고한다.

- [ ] 테스트 먼저:
  - (1) 테스트 분할 정답이 섞이면 `ValueError`를 낸다(Review Focus 3).
  - (2) 모든 항목에 `family_id`가 있다.
  - (3) 한정 정보가 있는 정답 사실 98개가 모두 예시가 된다. 한정 정보가 없는 사실도 "없음" 예시로 들어간다. "비워야 할 때"를 보여 주는 예시도 필요하기 때문이다.
  - (4) 예시의 `qualifiers`를 정규화기에 넣으면 정답 사실의 기준·조건·범위로 되돌아온다(왕복).
  - (5) 저장 해시가 결정론적이다.

**DoD:** 테스트·ruff·mypy 통과, KB 해시와 항목 수·evidence 채움 비율이 decisions.md에 기록된다.

### Task R2: 검색기

**설명:** 같은 KB에 대해 검색 방식만 바꿔 끼울 수 있게 팩토리로 만든다. 평가 모드에서는 질의 문서의 계열을 결과에서 빼는 필터가 모든 검색기에 똑같이 걸려야 한다. 한 검색기라도 빠지면 그 변형만 점수가 부풀려진다.

**Interfaces:**
- `make_retriever(kind: Literal["bm25", "dense", "hybrid"], kb, *, store: Literal["chroma", "faiss"] = "chroma", embedding: str = "bge-m3", k: int = 5) -> Retriever`
- `retrieve(retriever, query: str, *, exclude_family: str | None) -> list[KbExample]`
- `parent_context(example_or_line) -> str`

**결정(승인 필요) — 하이브리드 결합 방식:** LangChain 앙상블 검색기의 순위 융합(RRF, 가중치 동일)으로 시작한다. 가중치는 R3 진단에서만 고른다.

- [ ] 테스트(임베딩은 가짜 임베딩으로 대체, 결정론):
  - (1) 세 검색기 모두 `exclude_family`가 주어지면 그 계열을 반환하지 않는다(Review Focus 1).
  - (2) BM25는 기호 질의("R1")에서 해당 기호가 있는 예시를 1위로 낸다.
  - (3) 하이브리드는 두 결과를 합치고 중복을 없앤다.
  - (4) 빈 질의나 결과 없음에서 예외 없이 빈 목록을 낸다(Review Focus 5).

**DoD:** 테스트·ruff·mypy 통과.

### Task R3: 검색 품질 진단과 검색 설정 선택

**설명:** "Advanced RAG 검색 품질 진단"을 생성과 분리해 한다. 이 데이터의 장점은 정답이 있어서 "검색된 예시가 맞는 예시인가"를 직접 셀 수 있다는 것이다. 맞는 예시 = 정답 한정 정보(서명)가 같은 예시다. 생성(LLM) 비용 없이 검색기를 고를 수 있다.

**Interfaces:** `diagnose(kb, retriever_configs, *, ks=(1, 3, 5)) -> DiagnosisTable`(구성별 recall@k, MRR, 질의당 지연, 임베딩 차원). 사전 검증(D-042, Jaccard top-1 73%·top-3 82%)이 하한 기준선이다.

- [ ] 진단 대상 구성:
  - `bm25`
  - `dense` × {bge-m3, nomic-embed-text} × {chroma, faiss}
  - `hybrid`(bm25 + 최고 dense)
  - 질의 변형: 줄 전체 / 비고만 / 세미콜론 조각별(Multi-Query 규칙형) / LLM 재작성(Multi-Query, 사용자 실행)
- [ ] 사용자 실행: `uv run python -m spec_bridge.rag.diagnose` (임베딩은 로컬 Ollama 필요)
- [ ] 헬퍼: 표를 기록하고 **검색 설정 1개를 고정**한다(조정 1회). 선택 근거는 top-3 recall 우선, 동률이면 지연이다.

**DoD:** 진단 표와 선택이 decisions.md와 보고서 초안에 기록된다.

### Task R4: 한정 정보 RAG 체인 (LCEL) + 근거 구절 검증

**설명:** 문제를 **값 하나 단위로 분해**한다. 모델은 "이 줄의 이 값에 대해 기준·조건·범위가 무엇인가"만 답한다. 프롬프트에는 다음이 들어간다.
1. 해당 축의 어휘 정의(D-039)
2. 검색 예시 k개(줄 → 한정 정보 + 근거 구절)
3. 부모 문맥(머리글·절 제목)
4. 현재 줄

모델은 각 필드에 근거 구절을 인용한다. 코드가 그 구절이 현재 줄·라벨·비고에 실제로 있는지 확인한다. 이것이 **W4-1에서 범위를 지어낸 문제**와 **예시 값 복사**(Review Focus 2)를 막는 하네스다.

**Interfaces:**
- `llm/runnable.py`: `as_runnable(provider: JsonProvider, *, schema, task) -> Runnable[dict, dict]`
- `rag/qualifiers.py`: `build_chain(onto, retriever, provider, *, k, exclude_family) -> Runnable`, `qualify(chain, observation: RawObservation, line, parent) -> QualifierResult`
- `QualifierResult(StrictModel)`: `basis`, `condition`, `scope`, `evidence`, `rejected: list[str]`(근거 없음·어휘 밖·단위 차원), `retrieved_ids: list[str]`
- 출력 스키마: 축별 enum(D-039의 숨김 토큰 제외) + 필드별 `evidence` 문자열. 필드는 선택(optional)이다. 비우는 것이 정상 선택지다.

- [ ] 테스트(FakeProvider):
  - (1) 근거 구절이 줄에 없는 필드는 버려지고 `rejected`에 사유가 남는다.
  - (2) 검색 예시의 수치("20 degC")를 그대로 낸 경우, 현재 줄에 그 구절이 없으면 버려진다.
  - (3) 어휘 밖 토큰은 버려진다.
  - (4) 조건 수량은 정규화기의 단위 차원 검사를 통과해야 한다.
  - (5) 평가 모드에서는 같은 계열 예시가 프롬프트에 들어가지 않는다.
  - (6) 검색 결과가 0개여도 체인이 동작한다. 이 경우 정의만으로 답한다.
  - (7) 프롬프트에 개발 문서 문장이 예시 외의 자리에 들어가지 않는다(예시는 KB에서 온 것으로 표시).

**DoD:** 테스트·ruff·mypy 통과.

### Task R5: Self-RAG 판정 단계

**설명:** 생성 전후로 모델 스스로 판정하게 한다.
- **관련성 판정**: 검색 예시 중 현재 줄과 같은 종류인 것만 남긴다.
- **지지 판정**: 낸 한정 정보가 인용 구절로 뒷받침되는지 판정한다.

코드 검증(R4)은 그대로 둔다. 둘 다 통과해야 채택한다. 효과는 R7의 변형 비교로 잰다. 호출 수가 늘어나므로 지연도 함께 기록한다.

**Interfaces:** `grade_examples(provider, line, examples) -> list[KbExample]`, `check_support(provider, line, result) -> QualifierResult`

- [ ] 테스트(FakeProvider): 관련 없음으로 판정된 예시는 프롬프트에서 빠진다. 지지 없음 판정은 해당 필드를 비운다. 판정 호출이 실패해도 R4 결과를 유지하고 사유를 기록한다.

**DoD:** 테스트·ruff·mypy 통과.

### Task R6: 구성 E 실행기 통합과 한정 정보 지표

**Interfaces:**
- `experiment.py --config E --retriever <고정 설정> --k 5 [--self-rag] [--no-retrieval]`. `--no-retrieval`은 문제 분해만 하고 예시를 넣지 않는 대조군이다(아래 E0).
- `run.json`에 KB 해시, 검색 설정, 임베딩 모델·차원, k, Self-RAG 여부, 질의당 호출 수를 남긴다.
- `qualifier_scoring.py`: 문맥 키 TP(/97), 문맥 없는 키 TP(/117), 지어낸 문맥(문맥이 붙은 FP 키), 근거 충실도(인용 구절 실재율), 검색 적중(정답과 같은 서명 예시의 top-k 포함률). `rescore.evaluation_hashes()`에 포함해 **새 scorer_id**를 기록하고, W3·W4-1 실행을 재채점해 나란히 둔다.

- [ ] 테스트: E가 C(optional) 추출 결과를 입력으로 쓰고 값마다 체인을 호출한다. 실패한 값은 한정 정보를 비우고 "확인 필요"로 표시한다. 문서 실패는 분모에 남긴다. 지표는 정답으로 만든 예측에서 1.0이다.

**DoD:** 테스트·ruff·mypy 통과, 새 scorer_id 기록.

### Task R7: 실험 행렬 실행 (ablation)

**설명:** RAG의 효과를 **분해**와 **검색**과 **판정**으로 나눠 잰다. E0(분해만)이 핵심 대조군이다. E0 대비 E1 이상이 나아지면 그 차이가 검색의 몫이다. 잡음 하한이 0(D-038)이므로 차이는 설정 차이로 읽는다. 문서 표본 변동은 부트스트랩 구간으로 표시한다.

| 실행 | 분해 | 검색 | 판정 | 비교 목적 |
|---|---|---|---|---|
| C-opt (기존) | 없음 | 없음 | 없음 | zero-shot 기준선 |
| R (기존) | — | — | — | 코드 규칙 기준선 |
| **E0** | 값 단위 | 없음(정의만) | 코드 검증 | 분해 효과 |
| **E1** | 값 단위 | R3에서 고른 설정 | 코드 검증 | 검색 효과(E1 − E0) |
| **E2** | 값 단위 | E1 + 질의 재작성 | 코드 검증 | Multi-Query 효과(R3에서 효과가 있을 때만) |
| **E3** | 값 단위 | E1 | + Self-RAG | 자기 판정 효과 |
| E1-cloud (선택) | 값 단위 | E1 | 코드 검증 | 같은 설계에서 모델 능력 차이(D-034 경로) |

- [ ] 사용자 실행: 각 행을 개발 24건, leave-family-out으로 실행한다.
- [ ] 헬퍼 분석: 문맥 키 TP(/97) 대비 목표(26/55), 지어낸 문맥, 근거 충실도, 사실 F1, 지연과 호출 수, 부트스트랩 구간을 낸다. 결과가 나빠도 그대로 기록한다.

**DoD:** 비교표와 해석(확인된 것과 가설 구분)이 보고서 초안에 기록된다.

### Task R8: 확장 판단 — 표시형·라벨 매핑 RAG

R7에서 E가 한정 정보에 효과가 있으면, 같은 KB(줄 → 속성, 표시형 → 토큰 예시)로 **개발 사전(코드)**을 대체하는 실험을 계획한다. 대상은 `normalize/dictionary.py`의 열거 표시형과 R의 라벨 사전이다. 효과가 없으면 원인 분석을 기록하고 확장하지 않는다. 별도 승인 후 진행한다.

### Task R9: W4-R 보고서

`docs/reports/w4r-rag-semantic-mapping.md`에 다음을 담는다.
- KB 구성(항목 수, evidence 채움 비율, 해시)
- 검색 진단 표
- 실험 행렬 결과
- 한계: 합성 생성 규칙 공유(D-039), 개발셋 leave-family-out의 낙관성, 독립 수기 사양서 평가 필요(W6)
- 다음 결정

헬퍼는 가설 성립을 판정하지 않고 증거를 정리한다.

---

## 승인이 필요한 결정

1. **의존성과 임베딩 후보**: R0의 패키지들, 로컬 임베딩 `bge-m3`·`nomic-embed-text`(Ollama). 클라우드 임베딩은 쓰지 않는다.
2. **LangChain 도입 경계**: 검색 부품(BM25·벡터 저장소·앙상블·Multi-Query)과 LCEL 조합은 LangChain을 쓴다. LLM 호출은 기존 제공자를 `Runnable`로 감싼다(감사·가드·결정성 유지). `ChatOllama` 직접 사용은 하지 않는다.
3. **KB 내용**: 개발 정답 예시(한정 정보가 있는 98개 + 없는 사실 예시) + 온톨로지 어휘 정의. 근거 구절은 코드가 찾을 수 있을 때만 채운다.
4. **평가 프로토콜**: 개발셋 leave-family-out, 검색 설정 1회 선택(검색 진단만), 생성 프롬프트 1회 고정 + 변형 비교. 테스트 분할은 W6에서 1회만 평가한다.
5. **하이브리드 결합**: RRF 동일 가중치로 시작하고, 가중치는 R3 진단으로만 정한다.
6. **실패 처리**: 근거가 검증되지 않은 한정 정보는 비우고 "확인 필요"로 남긴다(W4 검증기의 REVIEW와 연결).
