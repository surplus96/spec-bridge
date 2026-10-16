# spec-bridge

선박 기자재 제품 문서 → 간이 온톨로지 기반 추출·정규화·검증 → 중복·유사 검사 → 담당자 검토 → 등록(SQLite + 표준 JSON) 자동화 도구. 로컬 우선(Ollama), 결정론 검증, 근거 추적.

- 계획서(v2, 2026-10-05 재설계): [docs/spec-bridge-project-plan.md](docs/spec-bridge-project-plan.md) — **작업 전 "🧭 개발 헬퍼 모델 운영 지침"(H1~H4)을 따른다. H3(도메인 사실 프로토콜)이 최우선.**
- 결정 기록: [docs/decisions.md](docs/decisions.md) · 데이터셋 준비 계획: [docs/dataset-plan.md](docs/dataset-plan.md) · 수기 사양서 골격: [docs/spec-sheet-skeletons.md](docs/spec-sheet-skeletons.md) · 과제 정합성 검토: [docs/spec-bridge-task-alignment-review.md](docs/spec-bridge-task-alignment-review.md)
- 착수 리서치·체크리스트: [docs/spec-bridge-kickoff-research.md](docs/spec-bridge-kickoff-research.md), [docs/spec-bridge-kickoff-checklist.md](docs/spec-bridge-kickoff-checklist.md)
- 스택: Python(uv), pytest, ruff, mypy, LangGraph, FastAPI, React·TypeScript·Vite(web/, D-061), Docling, SQLite, Chroma, pint

## 핵심 규칙 요약 (상세는 계획서 H1~H4)

- 한 번에 작업 ID 하나. 시작 시 목표·DoD를 한 줄로 재확인.
- **교육 모드**: 전체 코드를 완성해 주지 말고 단계별 설명 + 참고 코드 조각. 사용자가 명시적으로 요청할 때만 전체 구현.
- 장비 파라미터 범위·형식명 규칙·제조사 별칭·규제 수치는 기억으로 쓰지 않는다. 원문 없으면 `[미검증]`. `verified_by`는 사용자만 채운다. 테스트의 도메인 수치는 온톨로지·마스터 데이터에서 읽는다. 프로젝트가 정한 항목은 `origin: synthetic`.
- 커밋·푸시·외부 전송은 사용자 요청 시에만.
- 🔶 체크포인트(CP-S1~S4)와 에스컬레이션 트리거에서는 멈추고 검토 패키지를 제공한다. 스스로 "검토 통과" 판정 금지.

## 스킬 사용 기본값

| 상황 | 스킬 | 이 프로젝트에서의 조정 |
|---|---|---|
| 새 작업 ID 착수, 설계가 모호할 때 | `superpowers:brainstorming` | 결과는 계획서와의 차이만 제안. 계획 변경은 승인 후 |
| 작업 ID를 단계로 쪼갤 때 | `superpowers:writing-plans` | 단계마다 DoD를 명령(테스트·린터·평가 수치)으로 정의 |
| 단계 실행 | `superpowers:executing-plans` | 교육 모드 유지 — 사용자가 타이핑, Claude는 설명·조각 제시 |
| 기능·버그 수정 구현 | `superpowers:test-driven-development` | 실패 테스트를 먼저 함께 작성. 규제 값은 레지스트리 픽스처 사용 |
| 버그·테스트 실패 | `superpowers:systematic-debugging` | 같은 버그 2회 재발 시 H2 에스컬레이션 |
| "완료" 선언 전 | `superpowers:verification-before-completion` | `uv run pytest`, `uv run ruff check .`, `uv run mypy spec_bridge tests` 결과 확인. 못 하면 "미확인" |
| 코드 작성 전반 | `andrej-karpathy-skills:karpathy-guidelines` | 최소 변경, 가정 명시 |
| 작업 ID 종료 시 | `code-review`, `simplify` | 🔶 체크포인트는 별도로 Opus급 교차 검토 패키지 작성 |
| LLM 제공자 어댑터(클라우드 비교용) | `claude-api` | 기본은 Ollama. 클라우드는 비교 실험 옵션 |

- 서브에이전트 기반 스킬(`subagent-driven-development`, `dispatching-parallel-agents`)은 교육 모드와 맞지 않으므로 사용자가 요청할 때만 쓴다.

## 전역 규칙(~/.claude/rules, ECC) 대비 이 프로젝트의 적용 (2026-10-15, D-083)

전역 규칙은 기본값이다. 아래 항목은 이 프로젝트에서 다음과 같이 적용한다.

| 항목 | 적용 |
|---|---|
| 서브에이전트 선제·병렬 사용 | **쓰지 않는다.** 사용자가 요청할 때만 쓴다(테스트 분할 격리 D-020, 동결 규율 D-080, 결정 맥락 유지). CP-S4 교차 검토처럼 독립 시각이 필요하면 요청해서 쓴다 |
| 커밋 메시지 | Conventional Commits(`feat:`, `fix:`, `docs:`, `test:`, `chore:` …)를 따른다 |
| Co-Authored-By | **유지한다**(AI 기여의 투명성, 사용자 결정) |
| 테스트 커버리지 80% | 통과 조건이 아니다. W6에 측정해 보고한다. DoD는 pytest·ruff·mypy(+웹 check·build) |
| 불변성, 함수 50줄 이하 | 새 코드에 적용한다. **동결 대상 모듈(채점기 등 해시 고정 파일)은 이 규칙에 맞추려고 고치지 않는다** |
| API 응답 봉투(success/data/error) | 쓰지 않는다. HTTP 상태 + 타입 응답 모델 + OpenAPI 생성 타입을 유지한다 |
| 모든 엔드포인트 속도 제한·CSRF | 적용하지 않는다(127.0.0.1 단일 사용자 로컬 도구). 공개 전에는 비밀정보·원문 미커밋 검사를 한다 |
| 구현 전 라이브러리 검색 | 따른다. 도메인 사실은 H3가 우선한다 |

## 명령

```bash
uv sync                 # 의존성 설치
uv run pytest           # 테스트
uv run ruff check .     # 린트
uv run ruff format .    # 포맷
uv run mypy spec_bridge tests   # 타입 검사 (테스트 포함, W2-6부터)
uv run pytest -m "not docling"  # 빠른 테스트 (Docling PDF 제외)
```
