# 초기 scaffold와 로컬 검증

이 디렉터리는 **배포 정의 원본**입니다. Ubuntu VM이나 운영 신문사가 이미 가동 중이라는 뜻이 아닙니다. 승인 범위는 [계획 v0.1](../.docs/plans/project-scaffold-v0.1.md)의 최소 scaffold·로컬 테스트이며, [요구사항 v0.1](../REQUIREMENTS.md)의 운영 검증은 별도입니다.

## 구성

- `compose.yaml`: 공식 `wordpress:7.1.4-php8.3-apache`와 `mariadb:11.4.13`. PHP 8.3/MariaDB 11.4는 [WordPress 권장 사양](https://wordpress.org/about/requirements/)을 충족합니다. 검증 시 pull한 digest와 실행 결과는 Kanban 작업 기록에 남깁니다. 태그 고정은 digest 불변성·보안 업데이트 보장을 뜻하지 않습니다.
- MariaDB는 호스트 포트를 publish하지 않습니다. WordPress만 기본 `127.0.0.1:8080`에 바인딩합니다. 외부 proxy·도메인·HTTPS는 미구현입니다.
- `mariadb_data`(`/var/lib/mysql`)와 `wordpress_data`(`/var/www/html`)는 서로 다른 named volume입니다. project 이름이 바뀌면 다른 볼륨이 생기므로 운영 시 project 이름을 고정해야 합니다. 볼륨은 백업이 아닙니다.
- `unless-stopped`는 프로세스 종료에 대한 restart policy입니다. 의도적으로 정지한 서비스·삭제된 컨테이너를 자동 복원하거나 `unhealthy`를 자동 복구하는 보장은 아닙니다.
- `healthcheck.sh --connect --innodb_initialized`와 `depends_on: service_healthy`로 초기 DB readiness를 기다립니다. 이후 DB 장애 감시·자동 복구/발행 재시도와는 다릅니다. WordPress healthcheck는 별도로 없으며 검증기가 실제 HTTP를 확인합니다.
- 두 서비스 로그는 `json-file`, `10m × 3` 제한입니다. 컨테이너 inspect·렌더된 config에는 환경변수 비밀 값이 나타날 수 있으므로 운영 출력을 카드/로그에 붙이지 마세요.

## 재실행 가능한 로컬 검증

저장소 루트에서 Python 3 표준 라이브러리, Docker CLI와 Compose v2가 필요합니다. 별도 Python 앱·패키지 설치나 uv는 필요하지 않습니다. 검증한 로컬 조합은 Compose `2.23.3-desktop.2` / Engine `24.0.7`입니다. 운영 버전 선택은 별도입니다.

```sh
# 설정만 검증: Docker daemon·모델·Hermes gateway를 시작하지 않음
python3 scripts/check-scaffold.py

# 같은 설정을 직접 확인(공개된 테스트 예시 값만 사용)
docker compose --env-file deploy/.env.example -f deploy/compose.yaml config --quiet

# Docker daemon 사용: 고유 project + 임시 랜덤 테스트 비밀 값
python3 scripts/smoke-compose.py
```

임시 파일은 Python이 사용하는 `TMPDIR` 아래 생성·정리됩니다. Hermes에서 실행할 때 `TMPDIR`를 해당 프로필의 관리 scratch 경로로 지정하세요. 다른 프로필 home은 쓰지 않습니다. smoke는 `WORDPRESS_PORT=0`으로 loopback의 임시 포트를 할당하고 해당 project의 컨테이너 두 개·볼륨 두 개·네트워크 하나만 생성합니다. DB healthy와 WordPress 설치 화면 HTTP 200, 실제 DB 행과 WordPress 볼륨 파일을 확인한 후 두 컨테이너를 강제 재생성하여 같은 데이터가 남는지 검사합니다. WordPress 사이트 설치·관리자 생성·기사/공개 발행·모델 호출은 하지 않습니다.

smoke는 `finally`에서 **그 고유 project에만** `down --volumes --remove-orphans`를 적용하고 label 재조회로 정리를 확인합니다. 기존 자원 ID도 전후 대조합니다. 이미지 캐시는 남깁니다. 전역 prune이나 기존 project 정리는 하지 마세요. 강제 종료/daemon 단절로 정리가 실패하면 출력의 `PROJECT=`를 확인하고 그 project만 수동 점검·정리해야 합니다. 일반 운영에서 `down --volumes`는 데이터 삭제이므로 사용하지 마세요.

Engine 24 같은 구버전의 loopback publish는 같은 L2 네트워크에서 접근될 수 있는 Docker의 알려진 제한이 있습니다([공식 포트 공개 문서](https://docs.docker.com/engine/network/port-publishing/)). 따라서 이 바인딩을 LAN/인터넷 격리 검증으로 해석하지 않습니다. smoke에서 방화벽·VM 네트워크를 바꾸지 않았으며 운영 전 지원되는 Engine과 실제 접근 경계를 검증해야 합니다.

## 비밀 값과 운영 활성화의 경계

`.env.example`은 누구나 읽는 **config 검증용 가짜 예시**이며 운영용 비밀번호가 아닙니다. 실제 배포 승인 뒤 별도 ignored `deploy/.env`에 고유한 DB root/user 비밀번호를 준비하고 파일 권한을 제한합니다(예: `chmod 600 deploy/.env`). `${VAR:?...}`로 두 필수 비밀번호의 누락/빈 값은 config 단계에서 실패합니다. 예시 문자열을 사용했다고 거부하거나 강도를 검증하는 기능은 아니므로 예시 재사용을 금지합니다.

Compose의 shell 환경변수가 env-file보다 우선합니다. 검증기는 관련 상속 변수를 제거하여 누락/빈 값 실패를 독립 검사합니다. 이미 초기화된 MariaDB 볼륨의 비밀번호는 env만 바꿔도 변경되지 않습니다. 운영 비밀 파일·DB 볼륨·Docker socket을 Hermes worker에게 공유하지 않습니다. Docker 제어 권한 자체가 강력한 호스트 권한이므로 운영 Hermes 계정에 제공하지 않습니다.

운영 배포 명령은 이 scaffold에서 실행하지 않습니다. 운영 전 HTTPS/접근 통제, 발행 정책과 검증된 발행 어댑터, 감시·백업/복구, 모델/예산과 Discord 권한을 결정해야 합니다.

## Hermes source와 runtime 분리

저장소의 [`hermes/config.example.yaml`](../hermes/config.example.yaml), [`SOUL.md` 원본](../hermes/profiles/anonymous-tipper/SOUL.md), [`일일 prompt`](../hermes/prompts/daily-edition.md)는 **정의 원본**입니다. 실제 profile·bot·cron·board는 생성하지 않았습니다. `anonymous-tipper`는 사람에게 보이는 역할명 `anonymous tipper`의 식별자이며 제보자의 기술적 익명성을 보장하지 않습니다. 같은 OS 계정의 프로필은 강제 보안 격리가 아닙니다.

향후 승인된 전용 비관리자 계정의 별도 `HERMES_HOME`(예: 해당 계정의 `~/.hermes`)에 config·자격증명·profile home·cron·Kanban DB/첨부물·세션/로그를 보존합니다. 기사 산출물도 별도 영구 경로에 두거나 durable task attachment로 선언합니다. 운영 runtime을 Git checkout이나 완료 시 삭제되는 scratch에 두지 않습니다. SQLite board는 VM 로컬 영구 디스크에 두고 개발 board와 분리합니다. 보드 이름·경로·OS 계정은 배포 때 확정합니다.

방향은 **한 gateway**의 multiplexing + 전용 뉴스 board/단일 dispatcher, 필요할 때만 다섯 역할 worker 실행입니다. gateway·profile·Discord bot의 수는 같은 개념이 아닙니다. 같은 bot token으로 다섯 gateway를 실행하지 않습니다. 예시는 dispatcher/triage/review/알림과 Discord를 꺼 두며 모델·token·라우트·cron job은 제공하지 않습니다. `config.yaml`에 존재하지 않는 `publish_enabled`, `cron.enabled` 같은 가상 차단 키를 추가하지 않습니다. 모델을 생략한 것은 호출 차단 장치가 아닙니다. **기존 credential/job-bearing home에 예시를 덮어쓴 뒤 gateway를 시작해도 안전하다는 뜻이 아닙니다.**

운영자는 승인 후 실제 설치 버전의 공식 CLI로 필요한 profile·board·cron을 만들고, 인증정보와 채널 allowlist·모델/예산·실행 시간대·회차 중복 정책·전용 board 선택을 검증해야 합니다. 여기서는 실사용 스케줄과 미정 운영값을 정하지 않습니다. 저장소 개발용 planner/executor/reviewer와 신문사 역할은 별개입니다.

### 공통 지침의 실제 전달

역할 SOUL은 profile home에서 독립적으로 로딩되지만 `AGENTS.md`는 worker cwd/실행 경로와 context 우선순위에 따라 로딩 여부가 달라집니다. scratch/worktree에 자동 복제된다고 가정하지 않습니다. 활성화 전에 실제 worker가 [AGENTS.md](../AGENTS.md)와 승인된 편집 정책/발행 정책 버전을 읽도록 카드에 절대 경로·버전을 제공하거나 작업공간에 지침을 준비하고, worker의 첫 확인 기록으로 전달을 검증합니다. 지침을 읽을 수 없으면 업무를 보류합니다.

### 공식 서비스 설치 흐름 — Ubuntu에서 추후 수행

[공식 Messaging Gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging)와 설치 버전의 `hermes gateway install --help`를 먼저 확인합니다. Linux 기본 user service 흐름은 `hermes gateway install`, 부팅용 system service 흐름은 `hermes gateway install --system --run-as-user <전용계정> --no-start-now`를 검토합니다. system service 설치에는 관리 권한이 필요하나 gateway 자체는 전용 비관리자 계정이어야 합니다. **이 명령들은 이번에 실행하지 않았습니다.** 실제 `HERMES_HOME`, CLI 절대 경로와 target user를 명시적으로 확인하며 sudo 환경에서 잘못된 home을 쓰지 않도록 합니다.

CLI가 생성한 unit의 `User`, `Environment`/home, `WorkingDirectory`, 실행 경로·재시작 지연/횟수 제한·정상 종료/운영자 stop 정책을 검토합니다. unit 이름/경로는 home·profile·버전에 따라 달라지므로 이 저장소에 추측한 unit을 복제하지 않습니다. user service 또는 dispatcher worker의 별도 systemd scope에는 해당 사용자 bus/linger 조건도 확인합니다. Ubuntu에서 로그아웃·무인 부팅·비정상 종료·의도적 정지·worker 재개를 각각 검증해야 하며 macOS smoke 성공으로 대체할 수 없습니다. Docker는 컨테이너 재시작을 담당하고 systemd와 이중 감독하지 않습니다.

## 미구현·미검증

VM 배포와 systemd 부팅, Discord 수신/권한/알림, 실제 profile/cron/모델 실행, 승인 차단·중복 발행 어댑터, HTTPS/외부 접근, 예산 제어, 독립 감시, 백업·복원과 Hermes 상태 복구는 후속 범위입니다. 빈 감시/백업 stub이나 동작한다고 가정한 운영 unit은 만들지 않습니다. 공개 발행은 비활성입니다. Kanban 작업 기록과 독립 리뷰를 확인한 뒤에도 사용자 배포/발행 승인은 별도로 필요합니다. `.docs/reports/`는 Git에서 제외하는 로컬 자료이며, 공유 검증 증거는 카드에 보존합니다.
