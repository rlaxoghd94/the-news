# The News 초기 scaffold 실행 계획

- 버전: 0.1 / 실행 승인됨: 사용자의 “브랜치 변경했으니 REQUIREMENTS.md 기반 구축을 kanban 보드 통해서 해봐” 지시.
- Spec: `REQUIREMENTS.md` v0.1. SHA-256: `56d1b8ec3753502a294bebdfe07addb9df5956c49044835cc42aad808da8ec07`.
- 원본 저장소: `.`.
- 기준 브랜치: `feature/1-project-scaffold`, HEAD `4519890cfad196a23805c2e2f8b9a346710f8527`.
- 실행 방식: native Kanban의 executor → 같은 카드 reviewer 검토 → 필요 시 executor 수정. 별도 reviewer 자식 카드는 만들지 않습니다.
- 작업공간: 위 저장소를 anchor로 native Kanban이 생성하는 `.worktrees/<task-id>` 보존형 Git worktree와 `wt/<task-id>` 브랜치. 기준 checkout에서 구현하지 않습니다.

## 목표와 범위

Hermes 운영 정의와 WordPress/MariaDB 배포 정의를 관리하고 검증할 수 있는 최소 scaffold를 구축합니다. 이 작업은 전체 신문사 런타임 구현이나 Ubuntu VM 배포가 아닙니다.

### 포함

- 다섯 역할의 책임·입력·산출물·완료 조건을 담은 `hermes/profiles/*/SOUL.md` 원본. 폴더 식별자 `anonymous-tipper`는 역할명 `anonymous tipper`와의 대응을 명시합니다.
- 비밀 값 없는 Hermes gateway 설정 예시와 `hermes/prompts/daily-edition.md`. 실제 profile·cron·board를 생성하거나 현재 Hermes 설정을 바꾸지 않습니다.
- `deploy/compose.yaml`, `deploy/.env.example`: 별도 WordPress/MariaDB 서비스, 호환되는 구체 버전 이미지, 영구 볼륨, 재시작 정책, MariaDB readiness, WordPress의 준비 상태 의존성, 로그 제한.
- WordPress 호스트 공개는 기본 loopback으로 제한하고 MariaDB host port는 두지 않습니다. 초안 구조가 공개 자동 발행을 활성화해서는 안 됩니다.
- 공식 Hermes 서비스 설치와 runtime/source 분리 안내. 실제 버전을 모르는 systemd unit 전체나 동작하지 않는 감시·백업 stub은 만들지 않습니다. 필요한 예시는 예시임을 명시합니다.
- 유효 설정과 필수 값 누락 실패 경로를 검증하는 재실행 가능한 경량 확인 수단. 의존성이 필요 없는 shell/Python 표준 라이브러리 검증은 허용하되 Python 애플리케이션 패키지와 uv는 추가하지 않습니다.
- 기존 `.gitignore`에서 실제 사용될 비밀 파일·로컬 runtime 경로 제외를 보완하고, README는 목적 중심으로 유지하면서 필요한 링크만 추가합니다. 상세 운영 안내가 필요하면 간결한 `deploy/README.md` 하나에 모읍니다.

### 제외

- Ubuntu/Proxmox/홈랩 네트워크 변경, 원격 VM 설치와 공개 서빙.
- 실제 Discord bot token 등록·gateway 수정·profile 생성·LLM 실행·cron 활성화.
- 발행 어댑터, 기사·비용 관리 애플리케이션, 별도 API/queue/DB, uv/pyproject/빈 src·tests 패키지.
- 실사용 백업·복구·감시 구현과 외부 서비스 연결, 공개 기사 발행.
- Git commit, push, PR 게시, merge. 검토 후 사용자 브랜치로 옮길지 판단할 수 있도록 변경 파일과 검증 증거를 보존합니다.

## 문서 조회와 제약

- Context7은 planner/executor/reviewer에 설정되지 않은 것으로 확인했습니다. 사용자는 별도 질문에 **“이번 scaffold는 공식 문서 직접 조회로 진행”**을 선택했습니다. 이 예외는 이번 scaffold에 한정합니다.
- Hermes는 공식 live docs와 설치된 CLI/source를, Compose·MariaDB·WordPress는 공식 문서를 직접 확인합니다. 설정 키·image tag·동작은 추측하지 않습니다.
- 로컬 환경에서 Docker Compose `v2.23.3-desktop.2`, Docker Engine `24.0.7` 응답을 확인했습니다. Ubuntu systemd 실행 검증은 할 수 없습니다.
- GitHub CLI 인증이 invalid 상태입니다. 원격 issue body·CI를 확인했다고 주장하지 않으며 로컬 결과만 전달합니다. 인증 설정이나 다른 프로필 파일을 수정하지 않습니다.
- 원본의 미추적 REQUIREMENTS.md는 사용자 파일입니다. 수정·삭제·stage하지 말고 worktree에 정확히 복사하여 명세를 보존합니다. 계획 문서도 worktree에 복사합니다. 원본 요구사항 전체가 구현 완료된 것처럼 표시하지 않습니다.

## 작업 순서와 검증

### 1. Baseline과 명세 고정

- [ ] `kanban_show`로 실제 배정 카드와 workspace를 확인합니다.
- [ ] worktree HEAD가 위 기준 HEAD이고 원본 REQUIREMENTS.md hash가 위 값과 일치하는지 확인합니다. 다르면 조용히 덮어쓰지 말고 기록합니다.
- [ ] 원본 요구사항과 이 계획을 같은 상대 경로로 worktree에 복사합니다. Git의 기존 추적 파일과 사용자 원본은 그대로 보존합니다.

### 2. 구성과 역할 정의

- [ ] 실제 지원되는 Hermes 설정·Compose·이미지 호환성을 확인하고 필수 설정 실패 조건을 먼저 정합니다.
- [ ] 최소 Compose와 설정 예시, 역할별 지침, 일일 시작 prompt, 검증 수단을 작성합니다.
- [ ] root README의 기존 목적은 유지하고 source/runtime, profile/gateway/bot 구분, AGENTS.md가 실제 worker에게 전달되어야 한다는 조건을 설명합니다.

### 3. 실행 검증과 검토 인계

- [ ] 예시 값으로 `docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet`가 통과합니다.
- [ ] 필수 DB 비밀 값이 없는 별도 깨끗한 환경에서는 설정 검증이 실패합니다. 예시 파일을 운영 비밀 값으로 사용하도록 안내하지 않습니다.
- [ ] 렌더링된 구성에서 DB host port 없음, WordPress loopback, 영구 볼륨, healthcheck 의존성, restart policy와 로그 제한을 확인합니다.
- [ ] Docker 사용 가능 상태이므로 고유 project 이름과 테스트 전용 임시 설정으로 로컬 smoke test를 수행합니다. 외부 공개 금지, 모델 호출 금지. DB readiness와 WordPress HTTP 응답을 실제 확인하고 컨테이너 재생성 후 테스트 데이터 보존을 확인합니다. 이미지 pull 등 외부 실패는 사실 그대로 기록하고 capability/transient로 다룹니다. 해당 테스트가 만든 컨테이너·볼륨·네트워크만 종료·정리하고 기존 Docker 자원은 건드리지 않습니다.
- [ ] 공식 프로필 정의와 지침의 완결성, 민감정보·불필요한 파일 부재, 문서 상대 링크, `git diff --check`, `git check-ignore`를 확인합니다.
- [ ] 실제 명령·출력·정리 결과와 변경 파일, branch/workspace, 명세 버전을 카드에 기록합니다. reviewer가 같은 명령을 재실행할 수 있어야 합니다.
- [ ] 구현 완료 후 `kanban_request_review(reviewer="reviewer", ...)`로 같은 카드를 전달합니다. executor가 `kanban_complete`로 자체 승인하지 않습니다.

## Review Focus

1. 필요 없는 Python 프레임워크·uv·작동하지 않는 stub 또는 live 설정 변경이 섞이지 않았는가.
2. Compose 필수 값 누락이 fail-closed이고 DB port·비밀 값이 외부나 Git에 노출되지 않는가.
3. readiness·restart·persistent volumes를 서로 다른 조건으로 검증했는가.
4. 역할 지침이 실제 발행 승인·출처·영구 산출물 조건을 잃지 않았으며 profile 분리를 보안 격리로 과장하지 않는가.
5. 로컬 smoke 성공과 Ubuntu/Discord/실제 신문사 운영 검증을 혼동하지 않았는가.

## 완료와 후속 경계

이 카드의 done은 최소 scaffold의 독립 리뷰 통과를 의미합니다. REQUIREMENTS.md의 R-01~R-12 전체 운영 검증이나 배포·발행 승인을 뜻하지 않습니다. 각 미구현 요구사항은 기존 REQUIREMENTS.md에 남겨두며 미완료 사실을 전달합니다.
