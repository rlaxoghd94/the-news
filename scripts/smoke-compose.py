#!/usr/bin/env python3
"""Opt-in local Docker smoke: isolated project, loopback only, always clean up.

Requires Python standard library, Docker Engine and Compose v2. No LLM/Hermes.
Only the newly generated project is removed. Images remain in the local cache.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def smoke():
    project = "the-news-smoke-" + uuid.uuid4().hex[:12]
    passwords = [secrets.token_hex(24), secrets.token_hex(24)]
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("MARIADB_", "WORDPRESS_", "COMPOSE_"))}

    def redact(text):
        for password in passwords:
            text = text.replace(password, "<redacted-test-password>")
        return text

    def run(args, *, input=None, check=True):
        print("+ " + redact(" ".join(map(str, args))), flush=True)
        try:
            result = subprocess.run(args, cwd=ROOT, env=env, input=input,
                                    text=True, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            # TimeoutExpired includes argv (including MYSQL_PWD) in its repr.
            raise RuntimeError("command timed out after 300s: " +
                               redact(" ".join(map(str, args)))) from None
        if result.stdout.strip():
            print(redact(result.stdout.rstrip()), flush=True)
        if result.stderr.strip():
            print(redact(result.stderr.rstrip()), flush=True)
        print(f"exit={result.returncode}", flush=True)
        if check and result.returncode:
            raise RuntimeError(f"command failed (exit {result.returncode})")
        return result.stdout.strip()

    def inventory():
        return {
            "container": set(run(["docker", "ps", "-aq"]).split()),
            "volume": set(run(["docker", "volume", "ls", "-q"]).split()),
            "network": set(run(["docker", "network", "ls", "-q"]).split()),
        }

    def project_resources():
        label = "label=com.docker.compose.project=" + project
        return {
            "container": run(["docker", "ps", "-aq", "--filter", label]),
            "volume": run(["docker", "volume", "ls", "-q", "--filter", label]),
            "network": run(["docker", "network", "ls", "-q", "--filter", label]),
        }

    before = inventory()
    assert not any(project_resources().values()), "new project must not already exist"
    print(f"PROJECT={project}", flush=True)
    with tempfile.TemporaryDirectory(prefix=project + "-") as tmp:
        envfile = Path(tmp) / "smoke.env"
        envfile.touch(mode=0o600)
        envfile.write_text(
            "MARIADB_DATABASE=the_news\nMARIADB_USER=the_news\n"
            f"MARIADB_PASSWORD={passwords[0]}\nMARIADB_ROOT_PASSWORD={passwords[1]}\n"
            "WORDPRESS_PORT=0\n")
        base = ["docker", "compose", "--project-name", project,
                "--env-file", str(envfile), "-f", str(ROOT / "deploy/compose.yaml")]

        def compose(*args, **kwargs):
            return run(base + list(args), **kwargs)

        def sql(statement):
            return compose("exec", "-T", "-e", "MYSQL_PWD=" + passwords[0],
                           "mariadb", "mariadb", "--user=the_news", "--database=the_news",
                           "--batch", "--skip-column-names", input=statement + "\n")

        def runtime():
            ids = [compose("ps", "-q", service) for service in ("mariadb", "wordpress")]
            raw = subprocess.run(["docker", "inspect", *ids], cwd=ROOT, env=env,
                                 text=True, capture_output=True, timeout=30)
            if raw.returncode:
                raise RuntimeError("docker inspect failed: " + redact(raw.stderr))
            # Full inspect contains test secrets. Never emit it to logs.
            print("+ docker inspect <project-container-ids> (secret-bearing output withheld)")
            print(f"exit={raw.returncode}")
            db, wp = json.loads(raw.stdout)
            assert db["State"]["Health"]["Status"] == "healthy"
            assert not db["HostConfig"]["PortBindings"], "DB published a port"
            for binding in wp["NetworkSettings"]["Ports"]["80/tcp"]:
                assert binding["HostIp"] == "127.0.0.1", binding
            mounts = []
            for container, target in ((db, "/var/lib/mysql"), (wp, "/var/www/html")):
                assert container["Config"]["Labels"]["com.docker.compose.project"] == project
                assert container["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
                assert container["HostConfig"]["LogConfig"] == {
                    "Type": "json-file", "Config": {"max-file": "3", "max-size": "10m"}}
                mount = next(m for m in container["Mounts"] if m["Destination"] == target)
                assert mount["Type"] == "volume"
                mounts.append(mount["Name"])
            print("PASS runtime DB healthy/unpublished, WP loopback, restart/log limits and volume mounts")
            return ids, mounts

        def http_ready():
            binding = compose("port", "wordpress", "80")
            assert binding.startswith("127.0.0.1:"), binding
            url = "http://" + binding + "/wp-admin/install.php"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 120
            last_error = ""
            while time.monotonic() < deadline:
                try:
                    with opener.open(url, timeout=5) as response:
                        body = response.read().decode("utf-8", errors="replace")
                        if response.status == 200 and "WordPress" in body and "install" in body.lower():
                            print(f"PASS GET {url} HTTP {response.status}, WordPress installer (site not installed)")
                            return
                        last_error = f"HTTP {response.status}, unexpected page"
                except (OSError, urllib.error.URLError) as error:
                    last_error = str(error)
                time.sleep(2)
            raise RuntimeError("WordPress HTTP readiness timed out: " + last_error)

        started = False
        try:
            started = True  # Even partial `up` must be cleaned on failure.
            compose("up", "-d", "--wait", "--wait-timeout", "180")
            ids, mounts = runtime()
            http_ready()
            marker = uuid.uuid4().hex
            sql("CREATE TABLE scaffold_probe (id INT PRIMARY KEY, marker VARCHAR(64) NOT NULL);\n"
                f"INSERT INTO scaffold_probe VALUES (1, '{marker}');")
            assert sql("SELECT marker FROM scaffold_probe WHERE id=1;") == marker
            compose("exec", "-T", "wordpress", "tee", "/var/www/html/wp-content/scaffold-probe.txt",
                    input=marker)
            expected = hashlib.sha256(marker.encode()).hexdigest()
            assert compose("exec", "-T", "wordpress", "sha256sum",
                           "/var/www/html/wp-content/scaffold-probe.txt").split()[0] == expected
            print("PASS real DB row and WordPress volume file written/read")
            compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180")
            new_ids, new_mounts = runtime()
            assert set(ids).isdisjoint(new_ids), "containers were not recreated"
            assert mounts == new_mounts, "persistent volumes changed"
            http_ready()
            assert sql("SELECT marker FROM scaffold_probe WHERE id=1;") == marker
            assert compose("exec", "-T", "wordpress", "sha256sum",
                           "/var/www/html/wp-content/scaffold-probe.txt").split()[0] == expected
            print("PASS both containers replaced; exact DB row and WordPress file survived")
        except BaseException:
            if started:
                compose("logs", "--no-color", "--tail", "60", check=False)
            raise
        finally:
            if started:
                compose("down", "--volumes", "--remove-orphans", "--timeout", "30")
                assert not any(project_resources().values()), "test project resources remain"
                after = inventory()
                for kind in before:
                    assert before[kind] <= after[kind], f"pre-existing {kind} resource disappeared"
                print("PASS cleanup: no project containers/volumes/networks; all baseline resource IDs retained")
    print("PASS local Compose smoke; no WP install, article, Discord, LLM or VM changes")


if __name__ == "__main__":
    smoke()
