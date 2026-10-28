# 실행 가이드

spec-bridge는 로컬 우선 도구다. 서버는 `127.0.0.1`에만 열리고, `OFFLINE=1`이면 루프백이 아닌 모델 서버를 거부한다(NFR-01). 모든 데이터는 합성이다.

## 1. 준비

| 도구 | 용도 |
|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | 백엔드, 실험 |
| Node.js 22 이상 + npm | 검토 화면 빌드 |
| [Ollama](https://ollama.com) | 로컬 모델 `exaone3.5:7.8b`, 임베딩 `bge-m3` |

```bash
uv sync --frozen                # uv.lock 그대로
uv run docling-tools models download layout tableformer -o var/models/docling
ollama pull exaone3.5:7.8b
ollama pull bge-m3
npm --prefix web ci
npm --prefix web run build      # web/dist → FastAPI가 같은 주소에서 서빙
```

모델 다운로드(Docling·Ollama)만 네트워크를 쓴다. 파서는 `HF_HUB_OFFLINE=1`을 강제하므로 PDF를 파싱하다가 모델을 받지 않는다. `var/models/docling/`이 없으면 PDF 처리가 위 명령을 안내하며 거부된다. W6 평가 모델의 digest는 `c7c4e3d1ca22`다(`ollama list`로 확인). 태그가 같아도 digest가 다르면 다른 모델이다.

## 2. 검토 화면 실행

```bash
OFFLINE=1 SPEC_BRIDGE_APP_DIR=var/app uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1 --port 8010
```

브라우저에서 `http://127.0.0.1:8010/`을 연다. 처음 요청 때 서비스(모델 연결, KB 임베딩)를 만들므로 몇 초 걸린다.

- 앱 데이터: `SPEC_BRIDGE_APP_DIR`(등록 DB, 체크포인트, 업로드 원본). 처음 실행 때 개발 분할의 기존 등록 목록으로 만든다.
- 클라우드 모델로 바꾸기(비교용): `SPEC_BRIDGE_PROVIDER=openai`, `.env`에 `OPENAI_API_KEY`. 이때는 `OFFLINE=1`을 쓰지 않는다. 임베딩은 계속 로컬이다.
- API만으로 시연: `scripts/s1_s2_api_demo.sh ollama|openai`
- 설정 변수는 `.env.example`에 모아 두었다(`SPEC_BRIDGE_APP_DIR`, `SPEC_BRIDGE_PROVIDER`, `SPEC_BRIDGE_MODEL`, `SPEC_BRIDGE_BASE_URL`).

**운영 안전장치(D-116)**

- **이 컴퓨터에서만 접속**: 로그인이 없는 단일 사용자 도구다. 다른 컴퓨터에서 온 요청은 접속 주소로 판단해 403으로 거부한다. `--host 0.0.0.0`으로 띄워도 열리지 않는다.
- **상태 확인**: `curl http://127.0.0.1:8010/health`. 모델 서버에 설정한 모델이 있고 등록 저장소를 읽을 수 있으면 200이다. 아니면 503과 함께 무엇이 문제인지 보인다(예: `ollama pull …`이 필요함).
- **업로드 한도**: 사양서·BOM 파일은 50 MB까지 받는다. 넘으면 413으로 거부하고 아무것도 저장하지 않는다.
- **접속 주소를 바꾸는 옵션 주의**: uvicorn의 `--forwarded-allow-ips`는 기본값으로 둔다. `*`로 바꾸면 `X-Forwarded-For` 헤더로 접속 주소를 속여 위 제한을 넘을 수 있다.
- **실패한 명령**: 검토 중 보낸 명령이 실패하면(예: 모델 서버 시간 초과) 작업은 멈춘 지점에 남는다. 검토 화면 위에 사유가 보이고 같은 명령을 다시 보낼 수 있다. 실패 위치(traceback)는 서버 로그에 남는다(D-118).
- **저장소 백업과 복구**: 등록 저장소의 스키마를 올려야 하면(예: schema 2 → 3), 바꾸기 전에 같은 폴더에 `registry.sqlite.schema<옛 버전>-backup-<UTC 시각>` 사본을 만든다. 앱에서 등록한 제품과 수정 기록은 seed에 없으므로 이 사본이 유일한 되돌릴 길이다. 되돌리려면 다음 순서를 따른다.
  1. 서버를 끈다(Ctrl+C).
  2. 지금 파일을 다른 이름으로 옮긴다: `mv var/app/registry.sqlite var/app/registry.sqlite.after-migration`
  3. 사본을 원래 이름으로 복사한다: `cp var/app/registry.sqlite.schema2-backup-<시각> var/app/registry.sqlite`
  4. 이전 버전의 코드로 서버를 띄운다. 지금 코드로 띄우면 다시 스키마를 올리고 새 사본을 만든다.

  스키마 변경은 하나의 트랜잭션이다. 도중에 실패하면 파일은 바꾸기 전 상태로 남는다(D-118).

## 3. 검사 (완료 기준)

```bash
uv run pytest -q                    # 전체 (Docling·LLM 표시 테스트 포함 여부는 마커로 조절)
uv run pytest -q -m "not docling and not llm"   # 빠른 검사, CI와 같음
uv run ruff check .
uv run mypy spec_bridge tests
npm --prefix web run check          # tsc + Biome + Vitest
npm --prefix web run build
```

CI(`.github/workflows/ci.yml`)는 위 검사를 모델 서버 없이 돌린다. 로컬 검사와의 대조는 다음과 같다(W6-7, D-093).

| 로컬 검사 | CI | 차이 |
|---|---|---|
| `uv sync` | `uv sync --frozen` | CI는 `uv.lock`을 바꾸지 않는다 |
| `uv run ruff check .` | 같음 | — |
| `uv run mypy spec_bridge tests` | 같음 | — |
| `uv run pytest -q` | `-m "not docling and not llm"` | Docling PDF 모델과 Ollama가 필요한 테스트는 로컬에서만 돈다. 빌드 화면 검사(`tests/test_offline_app.py`)는 `web/dist`가 없으면 건너뛴다 |
| `npm --prefix web ci` / `run check` / `run build` | `npm ci` / `npm run check` / `npm run build` (Node 22) | — |

- git에 있는 파일만으로 통과하는지는 깨끗한 복제본에서 확인했다. 결과는 pytest 673 passed / 1 skipped / 1 xfailed, ruff·mypy 깨끗, 웹 32 passed, build 성공이다.
- Linux에서는 PyPI의 torch가 CUDA 패키지와 함께 설치된다(Docling 의존성). 그래서 첫 CI 설치가 오래 걸린다.

### 3-1. 브라우저 E2E (출시 전, 로컬 모델 필요, D-117)

```bash
npx --prefix web playwright install chromium   # 처음 한 번
npm --prefix web run e2e
```

- 화면을 빌드한 뒤 새 앱 폴더(`var/e2e/run-<시각>`)로 8011번 서버를 띄우고, 실제 브라우저로 두 경로를 확인한다.
  - BOM: 업로드 → 미리보기 → 검토 대기 행 지정 → 적용 → 제품 상세의 구성품. 모델 호출이 없다.
  - 사양서: 업로드 → 로컬 모델 처리 → 검토 화면 → 값 수정과 이력. 1~2분 걸린다.
- Ollama(`exaone3.5:7.8b`, `bge-m3`)가 켜져 있어야 한다. 서비스가 KB 임베딩을 만들기 때문이다. 그래서 CI는 이 테스트를 돌리지 않는다(Docling·LLM 테스트와 같음).
- 실패하면 `web/test-results/`의 화면 스냅숏과 `npx --prefix web playwright show-trace <trace.zip>`으로 원인을 본다.

## 4. 실험 재현

```bash
uv run python -m spec_bridge.parse.run dev                 # 파싱 → var/parsed/dev
uv run python -m spec_bridge.rag.knowledge                 # KB(개발 분할만) → data/rag/kb-dev.jsonl (커밋됨)
OFFLINE=1 uv run python -m spec_bridge.eval.experiment --config E --rag e1 --self-check --resolve-conflicts
uv run python -m spec_bridge.eval.rescore var/eval/<run_id>   # 현재 채점기로 재채점
```

테스트 분할과 수기 사양서는 동결 기록(`var/eval/FREEZE.json`)이 현재 시스템과 일치할 때만 실행된다(D-080). W6 실행 순서는 `scripts/w6_runs.sh dev|test|handwritten`이다. 구성을 고를 때는 `scripts/w6_runs.sh test Copt`처럼 쓴다.

W6 최종 평가([보고서](reports/w6-final-evaluation.md))의 수치는 다음 명령으로 다시 만든다.

```bash
uv run python -m spec_bridge.eval.freeze verify
uv run python -m spec_bridge.eval.rescore var/eval/test-*-20261015T* var/eval/handwritten-*
uv run python -m spec_bridge.eval.compare --e1 var/eval/test-E1SV-… --e0 var/eval/test-E0-… --r var/eval/test-R-…
uv run python -m spec_bridge.eval.errors var/eval/test-E1SV-… --list     # 오답 원인 분류
```

### 4-1. 새 환경에서 W6 평가 재현

원자료(`var/eval/`)는 저장소에 없다. 그래서 기존 날짜 경로의 `rescore`·`compare` 명령은 실행 원자료를 받아 둔 경우에만 쓸 수 있다(저장소의 재채점 묶음 `data/eval/w6-runs/`). 처음부터 다시 실행하려면 아래 순서를 따른다. 테스트·수기 실행은 약 2시간 걸린다.

```bash
uv sync --frozen
uv run docling-tools models download layout tableformer -o var/models/docling
ollama pull exaone3.5:7.8b
uv run python -m spec_bridge.parse.run dev
uv run python -m spec_bridge.parse.run test
uv run python -m spec_bridge.eval.handwritten build
uv run python -m spec_bridge.eval.freeze restore
uv run python -m spec_bridge.eval.freeze verify
uv run python -m spec_bridge.eval.manifest check
scripts/w6_runs.sh dev
scripts/w6_runs.sh test
scripts/w6_runs.sh handwritten
```

- `handwritten build`는 수기 입력을 파싱하고 변환 정답을 다시 만든다. 결과는 커밋된 변환 정답과 바이트 단위로 같다. 같지 않으면 `freeze verify`가 실패한다.
- `freeze restore`는 커밋된 W6 동결 기록(`docs/reports/w6-freeze.json`)을 `var/eval/FREEZE.json`에 둔다. **`freeze write`를 쓰지 않는다.** 그러면 W6 시스템이 아니라 지금 받은 코드를 새로 동결하게 된다.
- `manifest check`는 동결 기록 밖에서 결과를 정하는 22개 파일과 데이터셋 해시를 W6 manifest와 대조한다(CP-S4 R5).
- 모델 digest가 W6과 다르면 실행은 되지만 결과가 같다고 기대할 수 없다. 각 `run.json`의 `model.digest`로 확인한다.

## 5. 오프라인 확인 (W6-6)

모델 호출 기록에는 답한 서버(`base_url`)가 남는다. 실행 하나의 작업 DB나 감사 파일로 확인한다.

```bash
uv run python -m spec_bridge.llm.hosts var/app/registry.sqlite
```

운영체제 수준 관찰은 터미널 두 개로 한다. 터미널 1에서 `scripts/w6_offline_watch.sh`를 켜고, 터미널 2에서 `OFFLINE=1`로 서버를 띄워 시연한다. 시연이 끝나면 터미널 1을 `Ctrl+C`로 멈춘다. 그다음 기록을 읽는다.

```bash
uv run python -m spec_bridge.llm.hosts var/w6-6/connections-<time>.log
```

프로세스별(이름+PID) 상대 주소와 보인 시간이 나온다. 서버 PID는 `127.0.0.1:8010`에서 수신하는 프로세스다. Ollama 데스크톱 앱은 모델 서버와 다른 프로세스이고, 자체 외부 통신을 할 수 있다(보고서 §9).

## 6. Docker를 쓰지 않는 이유

범위 밖이다(D-085). macOS의 컨테이너는 Metal GPU를 쓰지 못해 Ollama를 호스트에서 돌려야 하고, 그러면 컨테이너가 `host.docker.internal`로 나가야 해서 오프라인 가드(루프백만 허용)와 충돌한다. Docling(PyTorch) 때문에 이미지도 수 GB가 된다. 로컬 단일 사용자 도구라 위의 로컬 실행과 CI로 충분하다.

## 7. BOM 연결 (1단계, D-101)

BOM 표(Excel 또는 Markdown, 열 `Component`·`Model`·`Manufacturer`·`Quantity`, 위에 `Root model:`·`Manufacturer:`)의 행을 등록 저장소의 기존 제품에 연결한다. 모델은 쓰지 않는다.

```bash
uv run python -m spec_bridge.registry.store dev
uv run python -m spec_bridge.bom data/synth/boms/BOM-001.md --registry var/registry/dev.sqlite
uv run python -m spec_bridge.bom data/synth/boms/BOM-001.md --registry var/registry/dev.sqlite --apply
```

- 첫 실행은 미리보기다. 행마다 `new`(추가될 관계), `existing`(이미 있음), `pending`(검토 대기와 사유)을 보인다. `--apply`일 때만 저장한다. 미리보기는 파일을 바꾸지 않으므로, 스키마가 옛 버전인 저장소는 열지 않고 `refused:`로 알린다(`--apply`나 앱이 스키마를 올린다, D-118).
- 수량 칸은 `2`, `2 x`, `(2)`, `2 pcs`, `Two`처럼 써도 읽는다. 모델 칸에 구분자가 다르거나 정격·일련번호가 붙어 있어도, 모델 부분이 등록 모델과 정확히 같고 제조사가 맞으면 연결한다. 제조사 표기가 다르거나, `or equal`이 붙었거나, 모델이 없으면 검토 대기로 남기고 사유를 보인다(D-108).
- 상위 제품(`Root model` + `Manufacturer`)이 저장소에 없으면 BOM 전체를 거부한다. 새 제품은 사양서 등록으로 만든다.
- 기존 관계는 지우지 않는다. BOM에 없는 기존 관계는 `not_in_bom`으로 보고한다. 수량은 제품 이벤트 `bom_linked`와 감사 기록에 남는다.
- 합성 BOM 4건의 관계는 seed에 이미 있으므로, seed 저장소에서는 모든 행이 `existing`이다. BOM-002·004는 테스트 분할 저장소(`test`)에 있다.

**화면(2단계, D-103)**: 검토 화면 목록의 "BOM 연결"(`#/boms`)에서 같은 일을 한다. 대상은 앱 저장소(`<앱 폴더>/registry.sqlite`)다.

- "BOM 올리기" → 미리보기. 검토 대기 행에는 사유와 같은 종류의 등록 제품 목록이 보인다. 제품을 고르고 사유를 적어 "지정"하면 그 행이 "담당자 지정"으로 바뀐다.
- "적용"은 서버가 다시 계획한 결과가 미리보기와 같을 때만 저장한다. 그사이 저장소가 바뀌었으면 거부하고 새 미리보기를 보인다.
- 제품 상세에 구성품(수량)과 상위 제품이 보인다. 업로드한 BOM 파일은 `<앱 폴더>/boms/`에 남는다.
- 검토 대기 행의 "제안 받기"는 로컬 모델(`exaone3.5:7.8b`)을 부른다(D-112). 검증을 통과한 제안만 지정 양식을 채우고, 담당자가 "지정"으로 확정한다. 모델 서버가 꺼져 있으면 그 사실만 알리고, 나머지는 그대로 쓸 수 있다.

