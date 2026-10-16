# Atlas CMMS 호스트 연동 조사 (설계안, 이후 확장)

2026-10-14 · 작성: 헬퍼 모델 · 상태: **조사 기록**. 구현하지 않는다(D-078). 대상은 `~/projects/atlas-cmms`(로컬 Docker 호스트 예시)와 선례 `atlas-mcp`(uptime-copilot 연동)다. 읽기만 했고 자격 증명 파일(`.env`)은 열지 않았다.

## 1. Atlas 연동 지점

| Atlas 기능 | 확인한 내용 | spec-bridge와의 관계 |
|---|---|---|
| Asset | `name`, `model`, `manufacturer`(자유 문자열), `serialNumber`, `power`(문자열), `category`, `parentAsset`, `parts`, `vendors`, `files`, `description`, `additionalInfos`, `customFieldValues` | 등록 제품 전송의 주 대상 |
| CustomField | 대상 `ASSET`/`PART`/…, 형식 `NUMBER`, `SHORT_TEXT`, `SINGLE_CHOICE`, `DATE`, `LINK`. `PATCH /assets/{id}`의 `customFields`로 기록 | 온톨로지 속성(요약용) |
| File | `POST /files/upload`, Asset·Part에 첨부 | 원본 사양서와 표준 JSON 첨부(NFR-07 보존) |
| Import | `POST /import/assets`, `/parts`(비동기, `uuid`). `AssetImportDTO`에 사용자 정의 필드 없음 | 일괄 적재(사양 값은 생성 후 PATCH) |
| Search | `POST /assets/search`, `/parts/search` | 중복 판정 대상을 호스트 실데이터로 확장 |
| Webhook | `NEW_ASSET`, `NEW_PART`, `PART_CHANGE` … | 역방향 보강 제안 |
| 인증 | `x-api-key` 헤더 또는 서비스 계정 JWT(atlas-mcp) | 루프백 연결 |
| Asset.parentAsset | 설비 계층 | BOM `has_component`(D-060) |

선례: uptime-copilot → atlas-mcp(MCP, 베어러 인증, `127.0.0.1:3100`) → Atlas. 승인, 전달 ID, 모호한 실패의 자동 재시도 없음이 그쪽 정책이다. atlas-mcp의 Asset 도구는 읽기 전용이다.

## 2. 연동 후보

1. **등록 결과 전송**: `Registrar` 인터페이스(`register`, `link`)에 Atlas 구현을 추가한다. 클래스→AssetCategory, maker/model→`manufacturer`/`model`, 속성→사용자 정의 필드(단위는 라벨), 원본 사양서와 표준 JSON은 파일로 첨부한다. `link`는 기존 Asset에 문서만 첨부한다(S2).
2. **Atlas 설비를 중복 판정 대상으로(읽기 전용)**: `POST /assets/search` 결과를 matcher 입력으로 쓴다. 제조사 별칭 해석의 가치가 크다.
3. **Webhook 역방향 보강(제안만)**: `NEW_ASSET` → manufacturer+model로 등록 제품을 찾아 사양 채우기를 제안한다(자동 기입 없음, D-066).
4. **BOM → parentAsset**: BOM 확장(D-060) 때.
5. **uptime-copilot과의 관계**: D-078 참조.

## 3. 먼저 정할 불일치

1. **제품 형식 대 설치 설비**: spec-bridge는 형식(모델) 단위, Atlas Asset은 위치·일련번호를 가진 개체다. 권장안은 담당자가 고른 설치 Asset에 사양을 채우는 방식이다.
2. **문맥 손실**: 사용자 정의 필드는 값 하나만 담는다. 기준·조건·범위와 조건별 복수 값은 표준 JSON 첨부로 보존한다.
3. **식별 제약 없음**: Atlas에는 (제조사, 모델) 유일 제약이 없다. 중복 방지와 멱등 전송(전달 ID, 모호한 실패 자동 재시도 금지)은 spec-bridge 쪽 책임이다.
4. **범위**: 계획서의 "실제 ERP/PLM 연동"은 제외 항목이다. 이후 확장으로 다룬다.

## 4. 대안 호스트: openMAINT / CMDBuild (2026-10-15 조사, 결정 보류 D-088)

결정은 이후 확장 때 한다. 공통 호스트는 Atlas로 유지한다(D-078).

| 항목 | 확인 내용 |
|---|---|
| 정체 | openMAINT는 CMDBuild 플랫폼 위의 시설·자산 관리(CMMS) 구성이다. 운영사는 Tecnoteca / PAT srl(Zucchetti 그룹) |
| 최신판 | openMAINT 2.4(2025-04-30 배포, CMDBuild 4.0 기반). 공식 다운로드 페이지는 2.4 + CMDBuild 4.2로 표기. SourceForge에 `openmaint-2.4.2-4.2.0.war`가 있다(날짜 미확인). 2.5 소식 없음 |
| 경량판 | 없다. 대신 빈 데이터 모델(GIS 포함/미포함)이 있고, CMDBuild 코어만 쓸 수 있다. spec-bridge에는 **CMDBuild 코어 + 온톨로지에서 생성한 클래스**가 맞다(필요한 것은 스키마 엔진이지 시설관리 기능이 아니다) |
| 데이터 모델 | 관리자가 클래스·속성·도메인(관계, 자체 속성 가능)을 정의한다. 온톨로지(클래스, 타입 있는 속성, `has_component`)와 대응이 좋다 |
| REST(공식 웹서비스 매뉴얼 v4.0, 2025-06) | 4.0부터 REST만. 기본 `/cmdbuild/services/rest/v3`. 로그인 `POST /sessions?returnId=true`, 이후 헤더 `Cmdbuild-authorization`. 카드 `classes/{classId}/cards`(GET·POST·PUT·DELETE, PATCH 없음), 스키마 `classes`, `classes/{classId}/attributes`, 관계 `domains/{domainId}/relations`·`attributes`, 문서 `dms/…`·`uploads`, 연계 `etl/configs`·`etl/gates`. 응답 `{success, data, meta}`. **REST로 클래스·속성을 새로 만들 수 있는지는 미확인** |
| 설치 | Java 17, Tomcat 10, PostgreSQL 17(PostGIS 3.5 선택). 권장 사양 RAM 16 GB·4코어·150 GB(운영 기준). 공식 Docker 없음. 커뮤니티 itmicus/cmdbuild_docker가 openMAINT 2.4.2 + CMDBuild 4.2.0 Compose를 제공(비공식, 첫 실행 메모리 부족 경고) |
| 라이선스 | 2.0판 AGPL-3.0. 공식 페이지는 "사용 소프트웨어는 모두 오픈소스". 셀프서비스 포털은 비공개 라이선스(구독). **2.4판 라이선스 원문 미확인** |

**Atlas 대비**: 데이터 모델(설계 가능한 스키마, 관계 속성)은 openMAINT가 낫다. 운영 현실(공식 Docker, webhook, atlas-mcp·uptime-copilot 연동 선례, 공통 호스트 원칙)은 Atlas가 낫다. 이 Mac(16 GB)에서는 로컬 LLM과 CMDBuild를 함께 띄우기 어렵다.

**확장 때 할 일**: ① 2.4 라이선스 원문, ② REST 스키마 생성 지원 여부 확인, ③ 로컬 LLM을 끈 상태에서 itmicus Docker로 CMDBuild 코어를 띄워 클래스 1개 생성·제품 형식 1건 등록 시험(반나절), ④ 결과로 호스트 결정(uptime-copilot 이전 여부 포함).

출처: [openMAINT 2.4 release](https://www.cmdbuild.org/en/reference/news/openmaint-2-4-release-now-available), [openMAINT latest version](https://www.openmaint.org/en/download/latest-version), [CMDBuild docs — openMAINT](https://docs.cmdbuild.org/docs/overview/vertical-solutions/openmaint), [CMDBuild Webservice Manual v4.0](https://www.cmdbuild.org/file/manuali/versione-4.0/cmdbuild_webservicemanual_eng_v40.pdf), [itmicus/cmdbuild_docker](https://github.com/itmicus/cmdbuild_docker), [SourceForge openMAINT 2.4](https://sourceforge.net/projects/openmaint/files/2.4/), [CMDBuild forum — database to load](https://forum.cmdbuild.org/t/which-database-to-load-when-installing-openmaint/2225).
