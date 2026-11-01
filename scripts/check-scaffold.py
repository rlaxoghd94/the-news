#!/usr/bin/env python3
"""Offline scaffold checks; Compose plugin required, no daemon or LLM calls."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("anonymous-tipper", "researcher", "writer", "editor", "publisher")
SECRETS = ("MARIADB_ROOT_PASSWORD", "MARIADB_PASSWORD")


def run(args, *, env=None, cwd=ROOT):
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)


def check_compose():
    # No inherited DB values, .env or COMPOSE_FILE can satisfy negative tests.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("MARIADB_", "WORDPRESS_", "COMPOSE_"))}
    base = ["docker", "compose", "--project-name", "the-news-config-check",
            "-f", str(ROOT / "deploy/compose.yaml")]
    example = ROOT / "deploy/.env.example"
    result = run(base + ["--env-file", str(example), "config", "--quiet"], env=env)
    assert result.returncode == 0, result.stderr
    print("PASS example Compose config --quiet")
    result = run(base + ["--env-file", str(example), "config", "--format", "json"], env=env)
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    db, wp = (config["services"][s] for s in ("mariadb", "wordpress"))
    assert not db.get("ports"), "DB must not publish host ports"
    assert len(wp["ports"]) == 1
    port = wp["ports"][0]
    assert port["host_ip"] == "127.0.0.1" and port["target"] == 80
    assert wp["depends_on"]["mariadb"]["condition"] == "service_healthy"
    assert db["healthcheck"]["test"] == ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
    for service, target in ((db, "/var/lib/mysql"), (wp, "/var/www/html")):
        assert service["restart"] == "unless-stopped"
        assert service["logging"] == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
        mounts = [v for v in service["volumes"] if v["target"] == target]
        assert len(mounts) == 1 and mounts[0]["type"] == "volume"
        assert mounts[0]["source"] in config["volumes"]
        assert re.fullmatch(r"(?:wordpress|mariadb):\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", service["image"])
    assert db["environment"]["MARIADB_PASSWORD"] == wp["environment"]["WORDPRESS_DB_PASSWORD"]
    assert "MARIADB_ROOT_PASSWORD" not in wp["environment"]
    print("PASS rendered ports, volumes, readiness, restart, log limits, pinned versions")
    # Each secret is tested independently, both absent and empty, in a clean dir.
    lines = example.read_text().splitlines()
    with tempfile.TemporaryDirectory(prefix="the-news-config-") as tmp:
        for key in SECRETS:
            for empty in (False, True):
                test_env = Path(tmp) / "missing.env"
                kept = [line for line in lines if not line.startswith(key + "=")]
                if empty:
                    kept.append(key + "=")
                test_env.write_text("\n".join(kept) + "\n")
                result = run(base + ["--env-file", str(test_env), "config", "--quiet"], env=env, cwd=Path(tmp))
                assert result.returncode != 0 and key in result.stderr, result.stderr
                print(f"PASS {key} {'empty' if empty else 'absent'} rejected (exit {result.returncode})")


def check_files():
    for role in ROLES:
        text = (ROOT / "hermes/profiles" / role / "SOUL.md").read_text()
        for phrase in ("책임", "입력", "산출물", "완료 조건", "승인", "버전", "영구", "AGENTS.md"):
            assert phrase in text, (role, phrase)
        # Role-specific contracts, not identical prose in all five identities.
        if role in ("anonymous-tipper", "researcher", "writer"):
            assert "원출처" in text and "미확인" in text, role
        elif role == "editor":
            assert "출처" in text and "미확인" in text and "재승인" in text
        else:
            assert "승인본" in text and "재조회" in text and "중복" in text
            assert "발행 어댑터" in text and "보류" in text
    tipper = (ROOT / "hermes/profiles/anonymous-tipper/SOUL.md").read_text()
    assert "anonymous tipper" in tipper and "익명성" in tipper
    print("PASS five role contracts and explicit tipper mapping")
    # Check local Markdown file links (external URLs and anchors are not fetched).
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts:
            continue
        for link in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if "://" in link or link.startswith(("#", "mailto:")):
                continue
            assert (path.parent / link.split("#")[0]).exists(), (path, link)
    print("PASS Markdown relative links")
    for relative in ("hermes/config.example.yaml", "hermes/prompts/daily-edition.md",
                     "deploy/README.md", "scripts/smoke-compose.py"):
        assert (ROOT / relative).is_file(), relative
    print("PASS example config, inactive daily prompt, deployment guide and smoke entrypoint exist")
    ignored = ["deploy/.env", "deploy/.env.local", ".runtime/state.json", ".worktrees/probe/file", "hermes/auth.json", "deploy/volumes/probe", "hermes/profiles/writer/config.yaml", "hermes/profiles/writer/sessions/probe.jsonl", "hermes/profiles/publisher/.env"]
    included = ["deploy/.env.example", "hermes/config.example.yaml", "hermes/profiles/writer/SOUL.md", ".docs/plans/project-scaffold-v0.1.md"]
    for path in ignored + included:
        result = run(["git", "check-ignore", "--quiet", "--no-index", path])
        assert result.returncode == (0 if path in ignored else 1), path
    result = run(["git", "diff", "--check"])
    assert result.returncode == 0, result.stdout + result.stderr
    # Also check new files, which git diff does not include before staging.
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.name == ".git":
            continue
        if run(["git", "check-ignore", "--quiet", str(path)]).returncode == 0:
            continue
        text = path.read_text()
        assert all(line == line.rstrip() for line in text.splitlines()), f"trailing whitespace: {path}"
        assert not re.search(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}|\bmfa\.[A-Za-z0-9_-]{20,}", text), f"credential pattern: {path}"
    print("PASS ignore policy, diff --check, new-file whitespace, credential-pattern scan")
    print("NOTE pattern scan is not proof against every possible secret; manual review required")


if __name__ == "__main__":
    check_compose()
    check_files()
    print("PASS scaffold static checks (no runtime deployment claimed)")
