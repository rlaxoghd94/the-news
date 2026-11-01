# The News

Hermes Agent 기반의 여러 에이전트가 하나의 신문사처럼 협업하는 프로젝트입니다. 매일 재미있고 가치 있는 뉴스거리를 선정하고, 조사·집필·편집을 거쳐 WordPress 블로그에 기사를 발행하는 것을 목표로 합니다.

## 신문사 구성

| 역할 | 담당 업무 |
| --- | --- |
| anonymous tipper | 제보와 키워드를 기사 아이디어로 정리 |
| researcher | 원출처 조사와 사실관계 확인 |
| writer | 취재 자료를 바탕으로 기사 작성 |
| editor | 기사 후보 선정, 편집과 검토 |
| publisher | 승인된 기사의 WordPress 등록과 발행 결과 확인 |

## 운영 구상

- **Proxmox 전용 VM**에서 Hermes 운영 환경과 WordPress를 서빙합니다.
- **Discord**로 사용자 제보와 특종 키워드를 받고, 기사 후보군과 운영 알림을 전달합니다.
- **Hermes 프로필**이 역할을 나누어 협업하고, **WordPress**를 기사 발행 창구로 사용합니다.

## 현재 상태

초기 scaffold 구축과 WordPress/MariaDB의 로컬 실행·컨테이너 재생성 후 데이터 보존 검증을 완료했습니다. 운영 VM 배포·Discord 연결·일일 자동 실행·공개 발행은 아직 하지 않았습니다. 주제·언어·발행량·시각·모델/예산·승인 정책 등 운영 결정은 미확정입니다.

## 안내

- [작업 원칙과 역할](AGENTS.md) · [요구사항 v0.1](REQUIREMENTS.md)
- [초기 구성·로컬 검증·운영 경계](deploy/README.md)
- [Hermes 설정 예시](hermes/config.example.yaml) · [일일 시작 prompt 원본](hermes/prompts/daily-edition.md)

`hermes/`는 설정·역할의 **원본**이며 실제 `HERMES_HOME`이 아닙니다. 역할 프로필 수가 gateway나 Discord bot 수를 뜻하지 않으며, 이 저장소만으로 운영 기능을 자동 활성화하지 않습니다. 운영 전에는 공통 `AGENTS.md`가 실제 worker에 전달되는지도 확인해야 합니다.
