# 데모 대본 (약 30초)

README에 넣을 화면 녹화 대본이다. 녹화는 사용자가 한다. 결과 파일은 `docs/media/demo.gif`다.

## 준비

**1. 도구 (처음 한 번)**: GIF 변환에 `ffmpeg`가 필요하다.

```bash
brew install ffmpeg
```

**2. 리허설**: 버리는 폴더에서 장면 전체를 한 번 해 본다. 모델이 실제로 뽑은 값에 따라 등록을 막는 사유가 남을 수 있다. 무엇을 눌러야 하는지 미리 알아 둔다. 끝나면 서버를 끈다(Ctrl+C).

```bash
OFFLINE=1 SPEC_BRIDGE_APP_DIR=var/demo-rehearsal uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1 --port 8010
```

**3. 녹화용 서버**: 새 폴더(`var/demo`)를 쓴다. 작업 목록이 비고, 등록 목록은 개발 분할 기본값으로 시작한다. 이미 있으면 다른 이름(`var/demo2`)을 쓴다.

```bash
cd ~/projects/spec-bridge
npm --prefix web run build
ollama run exaone3.5:7.8b "ready" >/dev/null
OFFLINE=1 SPEC_BRIDGE_APP_DIR=var/demo uv run uvicorn spec_bridge.api.app:app --host 127.0.0.1 --port 8010
```

`ollama run …` 줄은 모델을 미리 메모리에 올린다(warm). 작업을 만들지 않으므로 목록은 빈 채로 시작한다.

**4. 브라우저**: 주소창·탭·북마크가 없는 앱 창으로 연다. 창은 1440×900이다.

```bash
open -na "Google Chrome" --args --app=http://127.0.0.1:8010/ --window-size=1440,900
```

- 확대 비율은 100%다(`Cmd+0`).
- 알림이 뜨지 않게 macOS 집중 모드(방해 금지)를 켠다.
- 업로드 창에서 바로 고를 수 있게, Finder에서 `data/synth/inputs/SYN-011.docx` 위치를 미리 열어 둔다.

## 장면

| 초 | 화면 | 조작 | 자막(선택) |
|---|---|---|---|
| 0–3 | 작업 목록 | `data/synth/inputs/SYN-011.docx` 업로드 | 합성 사양서 업로드 |
| 3–6 | 처리 중 → 검토 화면 | (대기 구간 빨리 감기) | 로컬 모델로 추출·검증 |
| 6–11 | 검토 화면 3분할 | 가운데 사실 하나(예: `rated_power`)를 누르면 왼쪽 원문이 강조된다 | 모든 값은 원문 위치를 가진다 |
| 11–16 | 사실 편집 | 값 하나를 고치고 사유를 적어 저장한다. 수정 표시(✎)와 이력이 보인다 | 수정은 같은 규칙으로 다시 검사 |
| 16–19 | 하단 막대 | **신규 등록**을 누른다. "신규 제품으로 등록되었습니다." 안내와 제품 링크가 뜬다(링크를 누르면 근거·수정 이력이 있는 제품 상세) | 사람이 확인한 뒤 등록 |
| 19–23 | 작업 목록 | 같은 SYN-011을 다시 업로드한다(빨리 감기) | 같은 제품을 다시 받으면 |
| 23–27 | 검토 화면 | 상단 "등록 차단 1", 오른쪽 "중복" 탭에 **동일 제품** 카드(빨간 테두리) | 동일 제품으로 판정, 등록 차단 |
| 27–30 | 하단 막대 | 연결 대상이 동일 제품으로 미리 선택돼 있다. **연결**을 누른다 | 새로 등록하지 않고 연결 |

## 녹화와 변환

macOS 화면 녹화는 일시 정지가 없다. 그래서 **대기 구간을 빼고 세 토막으로 녹화**한 뒤 이어 붙인다.

| 토막 | 장면 | 녹화 시작 → 끝 |
|---|---|---|
| `part1.mov` | 0–3초 | 작업 목록 → 업로드 직후 "처리 중"이 보이면 끝 |
| `part2.mov` | 3–19초 | 검토 화면이 뜬 뒤 → 원문 강조·수정·신규 등록 안내까지 |
| `part3.mov` | 19–30초 | 같은 파일 재업로드 → (처리 대기는 녹화하지 않음) → 동일 제품 카드·연결까지 |

`part3`는 업로드 직후 한 번 끊고, 검토 화면이 뜬 뒤 다시 녹화해도 된다(`part3a`, `part3b`). 그럴 때는 아래 목록에 두 파일을 모두 적는다.

1. `Cmd+Shift+5` → "선택 부분 기록"을 고르고, 영역을 브라우저 창에 맞춘다. "옵션"에서 "마우스 클릭 표시"를 켠다.
2. 토막마다 녹화를 시작하고, 메뉴 막대의 정지 버튼으로 끝낸다. 파일을 `part1.mov`처럼 이름 붙여 한 폴더에 둔다.
3. 이어 붙이고 GIF로 바꾼다(그 폴더에서 실행). 폭 960px, 10fps면 대략 수 MB다. 10 MB를 넘으면 `fps=8` 또는 `scale=800`으로 줄인다.

```bash
printf "file 'part1.mov'\nfile 'part2.mov'\nfile 'part3.mov'\n" > parts.txt
ffmpeg -f concat -safe 0 -i parts.txt -c copy demo.mov
ffmpeg -i demo.mov -vf "fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" demo.gif
mkdir -p ~/projects/spec-bridge/docs/media
cp demo.gif ~/projects/spec-bridge/docs/media/demo.gif
```

`demo.gif`를 브라우저에 끌어 놓아 30초 안팎인지, 글자가 읽히는지 확인한다.

## 확인

- 화면에 실제 제조사 이름이나 개인 정보가 없는지 본다. 합성 제조사 `SGDW-… Synthetic Works`만 보여야 한다.
- 브라우저 탭, 북마크 막대, 알림이 녹화 영역에 들어가지 않게 한다.
- 다 되면 `docs/media/demo.gif`가 생겼다고 알려 준다. README의 "녹화 예정" 줄을 이미지로 바꾸고 커밋한다.
