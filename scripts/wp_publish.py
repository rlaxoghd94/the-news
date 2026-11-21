#!/usr/bin/env python3
"""Publish one approved The News article to WordPress through the REST API.

Reads the approved Markdown draft (optional front matter, "# title", optional "## subtitle"
used as the excerpt, then the body), uploads the featured image, creates the post with the
article ID as its slug and verifies the result by reading the post back.

Duplicate guard: if a post with the same article ID slug already exists (any status), nothing
is created and the existing post is reported.

Credentials are read from an env file (default ~/.hermes/profiles/publisher/wp.env) with
WP_URL, WP_USER and WP_APP_PASSWORD. They are never printed.

Output: one JSON object on stdout. Exit code 0 on success or duplicate, 1 on failure.
Standard library only.
"""
import argparse
import base64
import html
import json
import mimetypes
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_ENV = Path.home() / ".hermes" / "profiles" / "publisher" / "wp.env"


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
        raise SystemExit(json.dumps({"ok": False, "error": f"missing in env file: {', '.join(missing)}"}, ensure_ascii=False))
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
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}") from None


def inline(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    return text


def markdown_to_blocks(md):
    """Small Markdown subset to block markup: paragraphs, ##/### headings, quotes, lists, rules."""
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


def parse_draft(text):
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
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
        raise ValueError("draft has no '# title' line")
    return meta, title, subtitle, "\n".join(lines[i:]).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--draft", required=True, help="approved Markdown draft")
    ap.add_argument("--article-id", required=True, help="article ID, used as the post slug")
    ap.add_argument("--image", help="featured image file")
    ap.add_argument("--caption", default="", help="featured image caption")
    ap.add_argument("--category", default="제보", help="category name (created if missing)")
    ap.add_argument("--status", default="publish", choices=["publish", "draft"])
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    ap.add_argument("--dry-run", action="store_true", help="parse and convert only, no API calls")
    a = ap.parse_args()

    slug = re.sub(r"[^a-z0-9-]+", "-", a.article_id.lower()).strip("-")
    meta, title, subtitle, body = parse_draft(Path(a.draft).read_text(encoding="utf-8"))
    content = markdown_to_blocks(body)
    if a.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "slug": slug, "title": title, "excerpt": subtitle,
                          "content_chars": len(content), "front_matter": meta}, ensure_ascii=False))
        return 0

    env = read_env(a.env_file)
    wp = WP(env["WP_URL"], env["WP_USER"], env["WP_APP_PASSWORD"])
    try:
        existing = wp.call("GET", f"/posts?slug={urllib.parse.quote(slug)}&status=any&context=edit")
        if existing:
            p = existing[0]
            print(json.dumps({"ok": True, "duplicate": True, "post_id": p["id"], "status": p["status"],
                              "url": p["link"], "slug": slug}, ensure_ascii=False))
            return 0

        cats = wp.call("GET", f"/categories?search={urllib.parse.quote(a.category)}&per_page=100")
        cat = next((c for c in cats if c["name"] == a.category), None)
        if cat is None:
            cat = wp.call("POST", "/categories", {"name": a.category})

        media_id = 0
        if a.image:
            img = Path(a.image)
            ctype = mimetypes.guess_type(img.name)[0] or "application/octet-stream"
            media = wp.call("POST", "/media", raw=img.read_bytes(), headers={
                "Content-Type": ctype,
                "Content-Disposition": f'attachment; filename="{slug}{img.suffix.lower()}"',
            })
            media_id = media["id"]
            wp.call("POST", f"/media/{media_id}", {"caption": a.caption, "alt_text": a.caption or title, "title": title})

        post = wp.call("POST", "/posts", {
            "title": title, "content": content, "excerpt": subtitle or "", "slug": slug,
            "status": a.status, "categories": [cat["id"]], "featured_media": media_id,
        })
        check = wp.call("GET", f"/posts/{post['id']}?context=edit")
        ok = check["status"] == a.status and check["slug"] == slug and (not media_id or check["featured_media"] == media_id)
        print(json.dumps({"ok": ok, "duplicate": False, "post_id": check["id"], "status": check["status"],
                          "url": check["link"], "slug": slug, "featured_media": check["featured_media"],
                          "category": cat["name"]}, ensure_ascii=False))
        return 0 if ok else 1
    except Exception as e:  # report and let the publisher record the failure
        print(json.dumps({"ok": False, "error": str(e), "slug": slug}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
