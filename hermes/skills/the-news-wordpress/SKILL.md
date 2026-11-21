---
name: the-news-wordpress
description: "The News WordPress: publish, update, feature, unfeature, unpublish, republish, status by article ID."
version: 1.0.0
author: The News (user-written)
platforms: [linux]
metadata:
  hermes:
    tags: [WordPress, Publishing, The News]
    category: publishing
---

# The News WordPress

The News 블로그 글을 기사 식별자 하나로 다루는 도구입니다. 기사 식별자가 글 주소(slug)가 되므로 같은 기사가 두 글로 갈라지지 않습니다.

## 실행

```bash
python3 ~/.hermes/profiles/publisher/skills/publishing/the-news-wordpress/scripts/wp.py <명령> --article-id <기사 식별자> [옵션]
```

- 결과는 JSON 한 줄입니다. `ok`가 `true`면 성공, `false`면 `error`에 원인이 있습니다.
- 자격증명은 스크립트가 `~/.hermes/profiles/publisher/wp.env`에서 직접 읽습니다. 이 파일은 열거나 출력하지 않습니다.
- 실패하면 같은 명령을 반복해서 보내지 않고, 결과를 카드에 남깁니다.

## 명령

| 명령 | 하는 일 | 옵션 |
| --- | --- | --- |
| `publish` | 승인본으로 새 글을 게시합니다. 이미 있는 기사면 새로 만들지 않고 `duplicate: true`를 돌려줍니다. | `--draft <승인본>` (필수), `--image <파일>`, `--caption "<캡션>"`, `--category "<분류>"` (기본 `제보`), `--sticky` |
| `update` | 이미 게시된 글의 본문·제목·요약, 대표 이미지, 캡션, 분류를 바꿉니다. 준 것만 바뀝니다. | `--draft`, `--image`, `--caption`, `--category` 중 하나 이상 |
| `feature` | 메인 대표 글 슬라이드에 올립니다. 게시 상태인 글만 됩니다. | `--max-sticky` (기본 5) |
| `unfeature` | 대표 글 슬라이드에서 내립니다. 글은 그대로 게시됩니다. | |
| `unpublish` | 글을 비공개(초안)로 내립니다. 지우지 않고, 대표 글에서도 빠집니다. | |
| `republish` | `unpublish`한 글을 다시 게시합니다. | |
| `status` | 게시 상태, URL, 대표 글 여부를 확인합니다. | |

## 규칙

- **대표 글 개수:** 대표 글은 최근 5개만 유지됩니다. `publish --sticky`나 `feature`로 하나를 올리면, 가장 오래된 대표 글이 자동으로 내려가고 결과의 `unfeatured`에 그 글 ID가 나옵니다. 테마 슬라이드가 5개까지만 보여 주고, 대표 글은 아래 목록에서 빠지기 때문입니다.
- **완전 삭제 없음:** 글을 완전히 지우는 명령은 없습니다. 내릴 때는 `unpublish`를 씁니다.
- **초안 형식:** 맨 위 front matter(선택), `# 제목`, 선택으로 `## 부제`(요약으로 들어감), 본문 순서입니다. 본문은 문단, `##`~`####` 제목, `>` 인용, `-`/`1.` 목록, `---` 구분선, `**굵게**`, `*기울임*`, `[링크](https://...)`를 지원합니다.
