#!/usr/bin/env python3
"""The News WordPress tool: publish, update, feature, unfeature, unpublish, republish, status.

Every command finds the post by its article ID (the post slug), so the same article never
becomes two posts. Credentials come from an env file (default ~/.hermes/profiles/publisher/wp.env)
with WP_URL, WP_USER and WP_APP_PASSWORD; they are never printed.

Output: one JSON object on stdout. Exit code 0 on success, 1 on failure.
Standard library only.
"""
import argparse
import base64
import html
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENV = Path.home() / ".hermes" / "profiles" / "publisher" / "wp.env"


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
        self.base = url.rstrip("/") + "/wp-json/wp/v2"
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.auth = {"Authorization": f"Basic {token}"}

    def call(self, method, path, data=None, headers=None, raw=None):
        hdrs = dict(self.auth)
        body = None
        if raw is not None:
            body = raw
        elif data is not None:
            body = json.dumps(data).encode()
            hdrs["Content-Type"] = "application/json"
        hdrs.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read().decode() or "null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if "rest_not_logged_in" in detail or "rest_forbidden" in detail:
                detail += " (authentication failed: check WP_USER / WP_APP_PASSWORD in the env file)"
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None


# ---------------------------------------------------------------- Markdown
def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_blocks(md):
    """Small Markdown subset to block markup: paragraphs, ##-#### headings, quotes, lists, rules."""
    out, para, items, kind = [], [], [], None

    def flush_para():
        if para:
            out.append(f"<!-- wp:paragraph -->\n<p>{inline(' '.join(para))}</p>\n<!-- /wp:paragraph -->")
            para.clear()

    def flush_list():
        nonlocal kind
        if items:
            tag = "ol" if kind == "ol" else "ul"
            attrs = ' {"ordered":true}' if kind == "ol" else ""
            lis = "".join(f"<!-- wp:list-item -->\n<li>{inline(i)}</li>\n<!-- /wp:list-item -->" for i in items)
            out.append(f"<!-- wp:list{attrs} -->\n<{tag} class=\"wp-block-list\">{lis}</{tag}>\n<!-- /wp:list -->")
            items.clear()
        kind = None

    for line in md.splitlines():
        s = line.strip()
        m_ul = re.match(r"^[-*]\s+(.*)", s)
        m_ol = re.match(r"^\d+[.)]\s+(.*)", s)
        if not s:
            flush_para(); flush_list(); continue
        if s in ("---", "***"):
            flush_para(); flush_list()
            out.append('<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->')
            continue
        h = re.match(r"^(#{2,4})\s+(.*)", s)
        if h:
            flush_para(); flush_list()
            level = len(h.group(1))
            attrs = "" if level == 2 else f' {{"level":{level}}}'
            out.append(f"<!-- wp:heading{attrs} -->\n<h{level} class=\"wp-block-heading\">{inline(h.group(2))}</h{level}>\n<!-- /wp:heading -->")
            continue
        if s.startswith(">"):
            flush_para(); flush_list()
            q = inline(s.lstrip("> ").strip())
            out.append(f'<!-- wp:quote -->\n<blockquote class="wp-block-quote"><!-- wp:paragraph -->\n<p>{q}</p>\n<!-- /wp:paragraph --></blockquote>\n<!-- /wp:quote -->')
            continue
        if m_ul or m_ol:
            flush_para()
            new_kind = "ol" if m_ol else "ul"
            if kind and kind != new_kind:
                flush_list()
            kind = new_kind
            items.append((m_ol or m_ul).group(1))
            continue
        flush_list()
        para.append(s)
    flush_para(); flush_list()
    return "\n\n".join(out)


def parse_draft(path):
    """Front matter (optional), '# title', optional '## subtitle' (used as excerpt), body."""
    text = Path(path).read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    lines = text.strip().splitlines()
    title = subtitle = None
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and re.match(r"^#\s+", lines[i]):
        title = re.sub(r"^#\s+", "", lines[i]).strip()
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and re.match(r"^##\s+", lines[i]):
            subtitle = re.sub(r"^##\s+", "", lines[i]).strip()
            i += 1
    if not title:
        raise RuntimeError("draft has no '# title' line")
    return title, subtitle or "", markdown_to_blocks("\n".join(lines[i:]).strip())


# ---------------------------------------------------------------- helpers
def slug_of(article_id):
    return re.sub(r"[^a-z0-9-]+", "-", article_id.lower()).strip("-")


def find_post(wp, slug):
    found = wp.call("GET", f"/posts?slug={urllib.parse.quote(slug)}&status=any&context=edit")
    return found[0] if found else None


def require_post(wp, slug):
    post = find_post(wp, slug)
    if not post:
        raise RuntimeError(f"no post for article ID slug '{slug}'")
    return post


def category_id(wp, name):
    cats = wp.call("GET", f"/categories?search={urllib.parse.quote(name)}&per_page=100")
    cat = next((c for c in cats if c["name"] == name), None)
    return (cat or wp.call("POST", "/categories", {"name": name}))["id"]


def upload_image(wp, path, slug, caption, title):
    img = Path(path)
    ctype = mimetypes.guess_type(img.name)[0] or "application/octet-stream"
    media = wp.call("POST", "/media", raw=img.read_bytes(), headers={
        "Content-Type": ctype, "Content-Disposition": f'attachment; filename="{slug}{img.suffix.lower()}"'})
    wp.call("POST", f"/media/{media['id']}", {"caption": caption or "", "alt_text": caption or title, "title": title})
    return media["id"]


def trim_featured(wp, limit, keep):
    """Keep only the newest `limit` featured (sticky) posts; unfeature the rest. Returns unfeatured IDs."""
    featured = wp.call("GET", "/posts?sticky=true&per_page=100&orderby=date&order=desc&_fields=id,date&context=edit")
    ids = [p["id"] for p in featured]
    if keep in ids:
        ids.remove(keep)
        ids.insert(0, keep)
    extra = ids[max(limit, 1):]
    for pid in extra:
        wp.call("POST", f"/posts/{pid}", {"sticky": False})
    return extra


def summary(wp, post_id, slug, **extra):
    p = wp.call("GET", f"/posts/{post_id}?context=edit")
    out = {"post_id": p["id"], "slug": slug, "status": p["status"], "url": p["link"],
           "title": p["title"]["raw"], "sticky": bool(p.get("sticky")), "featured_media": p["featured_media"]}
    out.update(extra)
    return p, out


# ---------------------------------------------------------------- commands
def cmd_publish(wp, a, slug):
    existing = find_post(wp, slug)
    if existing:
        _, out = summary(wp, existing["id"], slug, duplicate=True,
                         note="already exists; use update, feature or republish instead")
        return True, out
    title, excerpt, content = parse_draft(a.draft)
    media_id = upload_image(wp, a.image, slug, a.caption, title) if a.image else 0
    post = wp.call("POST", "/posts", {
        "title": title, "content": content, "excerpt": excerpt, "slug": slug, "status": "publish",
        "categories": [category_id(wp, a.category)], "featured_media": media_id, "sticky": a.sticky})
    unfeatured = trim_featured(wp, a.max_sticky, keep=post["id"]) if a.sticky else []
    p, out = summary(wp, post["id"], slug, duplicate=False, unfeatured=unfeatured)
    ok = (p["status"] == "publish" and p["slug"] == slug and bool(p.get("sticky")) == a.sticky
          and (not media_id or p["featured_media"] == media_id))
    return ok, out


def cmd_update(wp, a, slug):
    post = require_post(wp, slug)
    data, changed = {}, []
    title = post["title"]["raw"]
    if a.draft:
        title, excerpt, content = parse_draft(a.draft)
        data.update({"title": title, "excerpt": excerpt, "content": content})
        changed += ["title", "excerpt", "content"]
    if a.image:
        data["featured_media"] = upload_image(wp, a.image, slug, a.caption, title)
        changed.append("featured_image")
    elif a.caption is not None and post["featured_media"]:
        wp.call("POST", f"/media/{post['featured_media']}", {"caption": a.caption, "alt_text": a.caption})
        changed.append("caption")
    if a.category:
        data["categories"] = [category_id(wp, a.category)]
        changed.append("category")
    if data:
        wp.call("POST", f"/posts/{post['id']}", data)
    p, out = summary(wp, post["id"], slug, updated=changed)
    ok = bool(changed) and ("featured_media" not in data or p["featured_media"] == data["featured_media"])
    if not changed:
        out["error"] = "nothing to update: pass --draft, --image, --caption or --category"
    return ok, out


def cmd_feature(wp, a, slug):
    post = require_post(wp, slug)
    if post["status"] != "publish":
        raise RuntimeError(f"post is '{post['status']}', not published; republish it first")
    wp.call("POST", f"/posts/{post['id']}", {"sticky": True})
    unfeatured = trim_featured(wp, a.max_sticky, keep=post["id"])
    p, out = summary(wp, post["id"], slug, unfeatured=unfeatured)
    return bool(p.get("sticky")), out


def cmd_unfeature(wp, a, slug):
    post = require_post(wp, slug)
    wp.call("POST", f"/posts/{post['id']}", {"sticky": False})
    p, out = summary(wp, post["id"], slug)
    return not p.get("sticky"), out


def cmd_unpublish(wp, a, slug):
    post = require_post(wp, slug)
    wp.call("POST", f"/posts/{post['id']}", {"status": "draft", "sticky": False})
    p, out = summary(wp, post["id"], slug)
    return p["status"] == "draft", out


def cmd_republish(wp, a, slug):
    post = require_post(wp, slug)
    wp.call("POST", f"/posts/{post['id']}", {"status": "publish"})
    p, out = summary(wp, post["id"], slug)
    return p["status"] == "publish", out


def cmd_status(wp, a, slug):
    post = find_post(wp, slug)
    if not post:
        return True, {"slug": slug, "exists": False}
    _, out = summary(wp, post["id"], slug, exists=True)
    return True, out


COMMANDS = {"publish": cmd_publish, "update": cmd_update, "feature": cmd_feature, "unfeature": cmd_unfeature,
            "unpublish": cmd_unpublish, "republish": cmd_republish, "status": cmd_status}


def main():
    ap = argparse.ArgumentParser(description="The News WordPress tool (article ID = post slug)")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--article-id", required=True, help="article ID, used as the post slug")
        return p

    p = add("publish", "publish a new post from an approved draft (no-op if the article already exists)")
    p.add_argument("--draft", required=True)
    p.add_argument("--image")
    p.add_argument("--caption", default="")
    p.add_argument("--category", default="제보")
    p.add_argument("--sticky", action="store_true", help="also feature it in the home slider")
    p.add_argument("--max-sticky", type=int, default=5)

    p = add("update", "replace content/title/excerpt, featured image, caption or category of an existing post")
    p.add_argument("--draft")
    p.add_argument("--image")
    p.add_argument("--caption")
    p.add_argument("--category")

    p = add("feature", "feature a published post in the home slider (keeps the newest --max-sticky)")
    p.add_argument("--max-sticky", type=int, default=5)
    add("unfeature", "remove a post from the home slider")
    add("unpublish", "take a post offline (back to draft; nothing is deleted)")
    add("republish", "put an unpublished post back online")
    add("status", "show status, URL and featured state")

    a = ap.parse_args()
    slug = slug_of(a.article_id)
    try:
        env = read_env(a.env_file)
        wp = WP(env["WP_URL"], env["WP_USER"], env["WP_APP_PASSWORD"])
        ok, out = COMMANDS[a.command](wp, a, slug)
        print(json.dumps({"ok": ok, "command": a.command, **out}, ensure_ascii=False))
        return 0 if ok else 1
    except Exception as e:
        print(json.dumps({"ok": False, "command": a.command, "slug": slug, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
