# 호스트 연동 설계안 (미구현)

2026-10-16 · 상태: **설계안**. 구현하지 않았다(D-078). 조사 원자료는 [Atlas CMMS 연동 조사](research/atlas-cmms-host-integration.md)에 있다. 대안 호스트 openMAINT는 같은 문서 §4에 기록만 해 두었다(D-088).

## 1. 원칙

- spec-bridge와 uptime-copilot은 같은 호스트(Atlas CMMS, 로컬 Docker)를 쓰지만 **독립 프로젝트**다. 코드·데이터·DB를 공유하지 않고 서로를 직접 호출하지 않는다. 각자 호스트와만 연동한다(D-078).
- 두 프로젝트 사이의 연결점과 계약(데이터 형식, 식별 키, 책임 경계)은 두 프로젝트가 어느 정도 완성된 뒤에 설계한다.
- 연동해도 spec-bridge의 원칙은 그대로다. 사람이 결정하고, 근거를 남기고, 자동 병합하지 않고, 빠진 값을 채우지 않는다.

## 2. 연결 지점: `Registrar` 인터페이스

등록 그래프는 저장소를 이 인터페이스로만 부른다(`spec_bridge/graph/registration.py`). 지금 구현은 로컬 SQLite 저장소다. 호스트 연동은 같은 인터페이스의 두 번째 구현으로 들어간다. 그래프·검토 화면·검증은 바뀌지 않는다.

```python
class Registrar(Protocol):
    def register(self, job_id: str, result: RegistrationResult, edits: list[dict]) -> str: ...
    def link(self, job_id: str, target_id: str, result: RegistrationResult, edits: list[dict]) -> None: ...
```

- 두 메서드 모두 작업(`job_id`)마다 멱등이어야 한다. 그래프가 재개될 때 같은 호출이 다시 올 수 있다.
- `result`는 표준 JSON(클래스, 사실과 근거 위치, 검증 결과, 중복 판정, 출처 해시)이다. `edits`는 사람 수정 기록이다.

## 3. 연동 후보 (우선순위 순)

| # | 방향 | 내용 | 비고 |
|---|---|---|---|
| 1 | 호스트 → spec-bridge (읽기) | Atlas 설비 검색 결과를 중복·유사 판정 대상에 더한다 | 읽기 전용. 등록 전에 호스트 실데이터와 비교한다 |
| 2 | spec-bridge → 호스트 (쓰기) | `AtlasRegistrar.register`: 클래스 → AssetCategory, maker/model → `manufacturer`/`model`, 속성 → 사용자 정의 필드, 원본 사양서·표준 JSON → 파일 첨부 | 사용자 정의 필드에는 값 하나만 담긴다. 문맥은 표준 JSON 첨부로 보존한다 |
| 3 | spec-bridge → 호스트 | `AtlasRegistrar.link`: 기존 Asset에 문서와 표준 JSON만 첨부한다 | 사실을 덮어쓰지 않는다(S2와 같음) |
| 4 | 호스트 → spec-bridge (제안) | Webhook `NEW_ASSET`이 오면 등록 제품을 찾아 사양 채우기를 **제안**한다 | 자동 기입 없음(D-066) |
| 5 | 양방향 | BOM `has_component` → `parentAsset` | BOM 확장(D-060) 뒤 |

## 4. 먼저 정할 것

1. **제품 형식 대 설치 설비**: spec-bridge는 형식(모델) 단위로 등록한다. Atlas Asset은 위치·일련번호가 있는 개체다. 권장안은 담당자가 고른 설치 Asset에 사양을 채우는 방식이다. 형식 하나가 Asset 여럿에 대응한다.
2. **식별과 멱등**: Atlas에는 (제조사, 모델) 유일 제약이 없다. 그래서 중복 방지와 멱등 전송은 spec-bridge 책임이다. 전달 ID를 쓰고, 결과가 모호한 실패는 자동 재시도하지 않는다(uptime-copilot의 atlas-mcp 정책과 같음).
3. **오프라인 가드**: 호스트도 루프백 주소여야 `OFFLINE=1`과 맞는다. Docker 컨테이너의 호스트 접근(`host.docker.internal`)은 루프백이 아니어서 별도 결정이 필요하다(D-085).
4. **인증**: API 키나 서비스 계정 토큰은 환경 변수로만 받는다. 저장소와 감사 기록에 남기지 않는다.

## 5. 시작 조건과 순서

순서는 W6(CP-S4) → BOM 1단계 → G5 후속 실험 → 두 프로젝트 완성 뒤 호스트 연동이다(D-065, D-078).

연동 시작 전에 할 일은 다음과 같다.

1. 4-1 매핑 결정(사용자)
2. 호스트 결정: Atlas 유지 또는 openMAINT 시험 연동 결과(D-088)
3. 계약 문서: 필드 매핑표, 식별 키, 오류·재시도 정책
4. 후보 1(읽기 전용)부터 시험 구현
