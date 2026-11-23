---
name: the-news-comments
description: "The News persona comments: read a post, post a persona comment plan, status, purge, sync personas."
version: 1.0.0
author: The News (user-written)
platforms: [linux]
metadata:
  hermes:
    tags: [WordPress, Comments, The News]
    category: publishing
---

# The News Comments

지정된 글에 페르소나 이름으로 가상 댓글을 다는 도구입니다. 댓글마다 카드 ID와 계획 안의 `ref`가 남아서, 같은 카드를 다시 실행해도 댓글이 늘지 않습니다.

## 실행

```bash
python3 ~/.hermes/profiles/commenter/skills/publishing/the-news-comments/scripts/comments.py <명령> [옵션]
```

- 결과는 JSON 한 줄입니다. `ok`가 `true`면 성공이고, `false`면 `error`(계획 검증 실패면 `problems`)에 원인이 있습니다.
- 자격증명은 스크립트가 `~/.hermes/profiles/commenter/wp.env`에서 직접 읽습니다. 이 파일은 열거나 출력하지 않습니다.
- 페르소나 목록은 `~/.hermes/profiles/commenter/personas.json`입니다.
- 실패하면 같은 명령을 그대로 반복해서 보내지 않고, 결과를 카드에 남깁니다.

## 명령

| 명령 | 하는 일 | 옵션 |
| --- | --- | --- |
| `read` | 글 제목·본문 텍스트·게시 시각, 승인된 기존 댓글(작성자, 페르소나 여부, 부모), 사용 가능한 페르소나를 돌려줍니다. | `--post <ID\|#ID\|URL>` |
| `post` | 댓글 계획 파일을 순서대로 등록합니다. 계획이 검증을 통과하지 못하면 하나도 등록하지 않습니다. | `--plan <파일>`, `--card <카드 ID>`, `--post`(생략 시 계획의 `post`) |
| `status` | 이 카드로 등록된 댓글 목록 | `--post`, `--card` |
| `purge` | 생성된 댓글을 휴지통으로 보냅니다. 사용자 댓글은 건드리지 않습니다. | `--post` 그리고/또는 `--card` |
| `sync-personas` | 페르소나 파일대로 WordPress 사용자를 만들거나 이름·아바타를 갱신합니다. **사용자가 요청한 경우에만** 실행합니다. | |

## 댓글 계획 파일

```json
{
  "post": 12,
  "comments": [
    {"ref": "c1", "persona": "angry-reader", "content": "이게 기사냐?", "delay_min": 3},
    {"ref": "c2", "persona": "drip-king", "parent_ref": "c1", "content": "형 진정해 ㅋㅋ", "delay_min": 2},
    {"ref": "c3", "persona": "uncle-joke", "parent_comment_id": 41, "content": "허허 이 친구", "delay_min": 5}
  ]
}
```

- `ref`는 계획 안에서 겹치지 않는 이름입니다(`c1`, `c2` …).
- `persona`는 `personas.json`의 `id`입니다.
- 부모 지정
  - `parent_ref`: 같은 계획 안에서 **앞에 나온** 댓글
  - `parent_comment_id`: 이미 달린 댓글 ID(`read` 결과의 `id`)
  - 둘 다 없으면 원댓글입니다.
- `delay_min`: 부모 댓글(원댓글이면 글 게시 시각)보다 몇 분 뒤에 쓴 것처럼 보일지 정합니다. 미래가 되면 현재 시각으로 맞춥니다.
- 제한
  - 댓글 수는 1~15개입니다.
  - 대댓글 깊이는 최대 3입니다(원댓글이 1).
  - 본문은 1,000자 이하의 일반 텍스트입니다. 링크와 HTML은 쓰지 않습니다.
