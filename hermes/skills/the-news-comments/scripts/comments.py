#!/usr/bin/env python3
"""The News persona comments: read, post, status, purge, sync-personas, watch.

Talks to the `the-news/v1` REST routes from deploy/wordpress/mu-plugins/the-news-comments.php.
Credentials come from an env file (default ~/.hermes/profiles/commenter/wp.env) with WP_URL,
WP_USER and WP_APP_PASSWORD; they are never printed.

Output: one JSON object on stdout. Exit code 0 on success, 1 on failure.
Standard library only.
"""
import argparse
import base64
import html
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROFILE = Path.home() / ".hermes" / "profiles" / "commenter"
DEFAULT_ENV = PROFILE / "wp.env"
DEFAULT_PERSONAS = PROFILE / "personas.json"
MAX_COMMENTS = 15
MAX_DEPTH = 3
MAX_CHARS = 1000
POST_TEXT_LIMIT = 6000


# ---------------------------------------------------------------- API
def read_env(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in ("WP_URL", "WP_USER", "WP_APP_PASSWORD") if not values.get(k)]
    if missing:
        raise RuntimeError(f"missing in env file: {', '.join(missing)}")
    return values


class WP:
    def __init__(self, url, user, password):
        self.base = url.rstrip("/") + "/wp-json"
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = {"Authorization": f"Basic {token}"}

    def call(self, method, path, data=None):
        hdrs = dict(self.auth)
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode() or "null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if "rest_not_logged_in" in detail or "rest_forbidden" in detail:
                detail += " (authentication or permission failed: check the env file and the account's tn_commenter role)"
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None


# ---------------------------------------------------------------- helpers
def parse_time(value):
    """WordPress dates: '2026-11-21T09:26:00' (GMT fields have no offset) or RFC3339."""
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def resolve_post(wp, ref):
    """Accept 12, #12, ?p=12 URLs, or a post URL / slug."""
    ref = str(ref).strip()
    m = re.fullmatch(r"#?(\d+)", ref) or re.search(r"[?&]p=(\d+)", ref)
    fields = "id,link,title,content,date_gmt,status,comment_status,categories,slug"
    if m:
        return wp.call("GET", f"/wp/v2/posts/{m.group(1)}?_fields={fields}")
    slug = urllib.parse.urlparse(ref).path.rstrip("/").split("/")[-1] if "/" in ref else ref
    found = wp.call("GET", f"/wp/v2/posts?slug={urllib.parse.quote(slug)}&_fields={fields}")
    if not found:
        raise RuntimeError(f"no published post for '{ref}'")
    return found[0]


def plain_text(rendered):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", rendered, flags=re.S)
    text = re.sub(r"</(p|h\d|li|blockquote)>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def load_personas(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["personas"] if isinstance(data, dict) else data
    return {p["id"]: p for p in items}


def wp_personas(wp):
    return {p["persona"]: p for p in wp.call("GET", "/the-news/v1/personas")}


def comments_of(wp, post_id):
    return wp.call("GET", f"/the-news/v1/comments?post={post_id}")


def depth_map(comments):
    by_id = {c["id"]: c for c in comments}
    depths = {}

    def depth(cid):
        if cid not in depths:
            parent = by_id[cid]["parent"]
            depths[cid] = 1 if not parent or parent not in by_id else depth(parent) + 1
        return depths[cid]

    for cid in by_id:
        depth(cid)
    return depths


# ---------------------------------------------------------------- commands
def cmd_read(wp, a):
    post = resolve_post(wp, a.post)
    if post.get("status") != "publish":
        raise RuntimeError("post is not published")
    text = plain_text(post["content"]["rendered"])
    comments = comments_of(wp, post["id"])
    out = {
        "post_id": post["id"], "url": post["link"], "title": html.unescape(post["title"]["rendered"]),
        "date_gmt": post["date_gmt"], "comments_open": post.get("comment_status") == "open",
        "text": text[:POST_TEXT_LIMIT], "text_truncated": len(text) > POST_TEXT_LIMIT,
        "comments": [{k: c[k] for k in ("id", "parent", "author", "persona", "generated", "date_gmt", "content")}
                     for c in comments if c["status"] == "approved"],
        "personas_available": sorted(wp_personas(wp)),
    }
    if not out["comments_open"]:
        return False, {**out, "error": "comments are closed on this post"}
    return True, out


def validate_plan(plan, personas, wp_map, existing):
    errors = []
    items = plan.get("comments") or []
    if not 1 <= len(items) <= MAX_COMMENTS:
        errors.append(f"comment count must be 1..{MAX_COMMENTS}, got {len(items)}")
    existing_by_id = {c["id"]: c for c in existing}
    existing_depth = depth_map(existing)
    seen, depth = set(), {}
    for i, c in enumerate(items):
        where = f"comments[{i}]"
        ref = c.get("ref")
        if not ref or ref in seen:
            errors.append(f"{where}: missing or duplicate ref")
        persona = c.get("persona")
        if persona not in personas:
            errors.append(f"{where}: persona '{persona}' not in personas file")
        elif persona not in wp_map:
            errors.append(f"{where}: persona '{persona}' has no WordPress user (run sync-personas)")
        content = (c.get("content") or "").strip()
        if not content or len(content) > MAX_CHARS:
            errors.append(f"{where}: content empty or over {MAX_CHARS} chars")
        if c.get("parent_ref") and c.get("parent_comment_id"):
            errors.append(f"{where}: use parent_ref or parent_comment_id, not both")
        d = 1
        if c.get("parent_ref"):
            if c["parent_ref"] not in seen:
                errors.append(f"{where}: parent_ref '{c['parent_ref']}' must point to an earlier ref")
            else:
                d = depth[c["parent_ref"]] + 1
        elif c.get("parent_comment_id"):
            pid = int(c["parent_comment_id"])
            if pid not in existing_by_id:
                errors.append(f"{where}: parent_comment_id {pid} is not a comment on this post")
            else:
                d = existing_depth[pid] + 1
        if d > MAX_DEPTH:
            errors.append(f"{where}: reply depth {d} exceeds {MAX_DEPTH}")
        if ref:
            seen.add(ref)
            depth[ref] = d
    return errors


def schedule(items, post_time, existing_times, now):
    """Comment times: each one delay_min after its parent (or the post). If that runs past now,
    the part after the latest anchor is compressed linearly into anchor..now, so order is kept,
    replies never precede parents, and nothing is in the future (a fresh post still gets
    spread-out comment times)."""
    raw, anchors = {}, []
    for c in items:
        if c.get("parent_ref"):
            base = raw[c["parent_ref"]]
        elif c.get("parent_comment_id"):
            base = existing_times.get(int(c["parent_comment_id"]), post_time)
            anchors.append(base)
        else:
            base = post_time
            anchors.append(base)
        raw[c["ref"]] = base + timedelta(minutes=max(int(c.get("delay_min") or 1), 1))
    latest = max(raw.values())
    if latest <= now:
        return raw
    anchor = min(max(anchors or [post_time]), now)
    scale = max((now - anchor) / (latest - anchor), 0) if latest > anchor else 0
    # Times up to the anchor stay; only the part after it is squeezed into anchor..now.
    return {ref: t if t <= anchor else anchor + (t - anchor) * scale for ref, t in raw.items()}


def cmd_post(wp, a):
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    post = resolve_post(wp, a.post or plan.get("post"))
    post_id = post["id"]
    existing = comments_of(wp, post_id)
    personas = load_personas(a.personas)
    wp_map = wp_personas(wp)
    errors = validate_plan(plan, personas, wp_map, existing)
    if errors:
        return False, {"post_id": post_id, "posted": 0, "error": "plan rejected; nothing was posted", "problems": errors}

    times = schedule(plan["comments"], parse_time(post["date_gmt"]),
                     {c["id"]: parse_time(c["date_gmt"]) for c in existing}, datetime.now(timezone.utc))
    ids, results = {}, []
    for c in plan["comments"]:
        if c.get("parent_ref"):
            parent = ids.get(c["parent_ref"], 0)
        else:
            parent = int(c.get("parent_comment_id") or 0)
        when = times[c["ref"]]
        try:
            res = wp.call("POST", "/the-news/v1/comments", {
                "post": post_id, "parent": parent, "persona": c["persona"], "content": c["content"].strip(),
                "card": a.card, "ref": c["ref"], "date_gmt": iso(when)})
            com = res["comment"]
            ids[c["ref"]] = com["id"]
            results.append({"ref": c["ref"], "id": com["id"], "persona": c["persona"], "parent": com["parent"],
                            "skipped": res["skipped"]})
        except RuntimeError as e:
            results.append({"ref": c["ref"], "persona": c["persona"], "error": str(e)})

    # Re-read and confirm each comment exists with the intended parent.
    after = {c["id"]: c for c in comments_of(wp, post_id)}
    mismatched = [r["ref"] for r in results if "id" in r and (r["id"] not in after or after[r["id"]]["status"] != "approved")]
    failed = [r for r in results if "error" in r]
    out = {"post_id": post_id, "url": post["link"] + "#comments", "card": a.card,
           "posted": sum(1 for r in results if "id" in r and not r["skipped"]),
           "skipped": sum(1 for r in results if r.get("skipped")), "failed": len(failed),
           "not_visible": mismatched, "comments": results}
    return not failed and not mismatched, out


def cmd_status(wp, a):
    post = resolve_post(wp, a.post)
    mine = [c for c in comments_of(wp, post["id"]) if c["card"] == a.card]
    return True, {"post_id": post["id"], "card": a.card, "count": len(mine),
                  "comments": [{k: c[k] for k in ("id", "parent", "persona", "ref", "status")} for c in mine]}


def cmd_purge(wp, a):
    if not a.post and not a.card:
        raise RuntimeError("pass --post and/or --card")
    data = {}
    if a.post:
        data["post"] = resolve_post(wp, a.post)["id"]
    if a.card:
        data["card"] = a.card
    res = wp.call("POST", "/the-news/v1/comments/purge", data)
    return True, {**data, "trashed": res["trashed"], "count": len(res["trashed"])}


def cmd_sync(wp, a):
    personas = load_personas(a.personas)
    payload = [{"id": p["id"], "nickname": p["nickname"], "avatar_url": p.get("avatar_url", "")}
               for p in personas.values()]
    res = wp.call("POST", "/the-news/v1/personas", {"personas": payload})
    return True, {"synced": len(res), "personas": res}


def kanban(hermes, *args, stdin=None):
    res = subprocess.run([hermes, "kanban", *args], input=stdin, text=True, capture_output=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(f"hermes kanban {args[0]} failed: {(res.stderr or res.stdout).strip()[:300]}")
    return res.stdout


def cmd_watch(wp, a):
    """Turn new human comments into commenter reaction cards (one per post). No model call.

    The first run only records the current newest comment ID, so old comments are never
    reacted to. Run from a timer; safe to run repeatedly (idempotency key per post + comment)."""
    state_path = Path(a.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    last = int(state.get("last_id") or 0)
    res = wp.call("GET", f"/the-news/v1/user-comments?after_id={last}")
    if not last:
        state_path.write_text(json.dumps({"last_id": res["max_id"]}))
        return True, {"initialized": True, "last_id": res["max_id"], "cards": []}

    by_post = {}
    for c in res["comments"]:
        by_post.setdefault(c["post"], []).append(c)
    cards = []
    for post_id, comments in sorted(by_post.items()):
        ids = [c["id"] for c in comments]
        quoted = "\n".join(f"- #{c['id']} {c['author']}: {c['content']}" for c in comments)
        body = (f"작업 유형: 댓글공작\n대상 글: {post_id}\n요청 개수: 자동\n모드: 반응\n"
                f"대상 댓글: {', '.join(map(str, ids))}\n"
                f"요청 원문: (자동) 사이트에 사용자 댓글이 새로 달렸습니다.\n{quoted}\n")
        out = kanban(a.hermes, "create", "--assignee", "commenter", "--json",
                     "--idempotency-key", f"react-{post_id}-{max(ids)}", "--body-file", "-",
                     f"[반응] #{post_id} 사용자 댓글 {len(ids)}개", stdin=body)
        task = json.loads(out)
        tid = task.get("id") or task.get("task_id") or (task.get("task") or {}).get("id")
        if tid and a.notify_chat:
            kanban(a.hermes, "notify-subscribe", "--platform", "discord", "--chat-id", a.notify_chat,
                   "--chat-type", "channel", tid)
        cards.append({"post_id": post_id, "comments": ids, "card": tid})
    state_path.write_text(json.dumps({"last_id": max([last, res["max_id"]])}))
    return True, {"last_id": max(last, res["max_id"]), "cards": cards}


COMMANDS = {"read": cmd_read, "post": cmd_post, "status": cmd_status, "purge": cmd_purge,
            "sync-personas": cmd_sync, "watch": cmd_watch}


def main():
    ap = argparse.ArgumentParser(description="The News persona comments")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    ap.add_argument("--personas", default=str(DEFAULT_PERSONAS))
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("read", help="post text, existing comments and available personas")
    p.add_argument("--post", required=True, help="post ID, #ID, URL or slug")
    p = sub.add_parser("post", help="post a comment plan (idempotent per card + ref)")
    p.add_argument("--plan", required=True)
    p.add_argument("--card", required=True, help="Kanban card ID")
    p.add_argument("--post", help="post ID/URL; defaults to plan.post")
    p = sub.add_parser("status", help="comments posted for one card")
    p.add_argument("--post", required=True)
    p.add_argument("--card", required=True)
    p = sub.add_parser("purge", help="trash generated comments by post and/or card")
    p.add_argument("--post")
    p.add_argument("--card")
    sub.add_parser("sync-personas", help="create/update persona users from the personas file")
    p = sub.add_parser("watch", help="create commenter reaction cards for new human comments (timer)")
    p.add_argument("--state", default=str(PROFILE / "react-watch.json"))
    p.add_argument("--hermes", default=str(Path.home() / ".local" / "bin" / "hermes"))
    p.add_argument("--notify-chat", default="", help="Discord channel ID to notify when a card finishes")

    a = ap.parse_args()
    try:
        env = read_env(a.env_file)
        wp = WP(env["WP_URL"], env["WP_USER"], env["WP_APP_PASSWORD"])
        ok, out = COMMANDS[a.command](wp, a)
        print(json.dumps({"ok": ok, "command": a.command, **out}, ensure_ascii=False))
        return 0 if ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "command": a.command, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
