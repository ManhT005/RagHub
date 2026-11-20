"""Serialized, image-only deployment with verified offline-consistent backup.

Host config and runtime secrets stay outside release archives. Never removes volumes
or automatically rolls an old application over a potentially migrated database.
"""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

APP = (
    "api",
    "worker",
    "worker-provider",
    "worker-ocr",
    "admin-web",
    "chat-widget",
    "widget-demo",
    "nginx",
)
WRITERS = ("nginx", "api", "worker", "worker-provider", "worker-ocr")
STORAGE = ("postgres", "redis", "elasticsearch", "minio")
ARCHIVES = ("redis-data", "elasticsearch-data", "minio-data")


def run(command, *, env=None, output=None):
    result = subprocess.run(
        command, env=env, stdout=output or subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if result.returncode:
        # stderr may contain resolved secrets; keep diagnostics local and sanitized.
        raise RuntimeError(
            f"{command[0]} failed (exit {result.returncode}); inspect service logs privately"
        )
    return result.stdout


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2))
    temporary.chmod(0o600)
    temporary.replace(path)


def extract_release(archive, destination):
    destination.mkdir(mode=0o700)
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            # Only regular files/directories, never links, devices or traversal.
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise ValueError("Unsupported release archive entry")
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Release path escapes destination")
        source.extractall(destination, members=members, filter="data")


class Stack:
    def __init__(self, root, project, env_file, files, image_tag=None):
        self.project, self.image_tag = project, image_tag
        self.env = dict(os.environ)
        if image_tag:
            self.env["RAGHUB_IMAGE_TAG"] = image_tag
        self.command = ["docker", "compose", "--env-file", str(env_file), "-p", project]
        for path in files:
            self.command.extend(["-f", str(root / path)])
        self.command.extend(["--profile", "local-ai"])

    def call(self, *args, output=None):
        return run([*self.command, *args], env=self.env, output=output)

    def model(self):
        return json.loads(self.call("config", "--format", "json"))


def verify_layout(old, new):
    for key, volume in old["volumes"].items():
        if key not in new["volumes"] or volume["name"] != new["volumes"][key]["name"]:
            raise ValueError("Deployment would change volume identity")
    for name in STORAGE:
        if old["services"][name]["image"] != new["services"][name]["image"]:
            raise ValueError("Storage image upgrade requires separate maintenance")
    previous = old["services"]["api"]["environment"]
    target = new["services"]["api"]["environment"]
    for key in ("APP_SECRET_KEY", "PROVIDER_MASTER_KEY", "S3_SECRET_KEY", "DATABASE_URL"):
        if previous.get(key) != target.get(key):
            raise ValueError("Deployment would change runtime credentials")
    if (
        str(previous.get("RAG_RERANKER_ENABLED", "")).lower() == "true"
        and str(target.get("RAG_RERANKER_ENABLED", "")).lower() != "true"
    ):
        raise ValueError("Reranking overlay must be preserved")


def helper(image, directory, command, volume=None):
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "0",
        "--entrypoint",
        "sh",
        "--mount",
        f"type=bind,src={directory},dst=/backup",
    ]
    if volume:
        args += ["--mount", f"type=volume,src={volume},dst=/data,readonly"]
    return run([*args, image, "-ec", command])


def backup(stack, model, env_file, directory, active):
    directory.mkdir(mode=0o700)
    image = model["services"]["postgres"]["image"]
    writers = [service for service in WRITERS if service in active]
    try:
        stack.call("stop", "-t", "90", *writers)
        with (directory / "postgres.dump").open("wb") as output:
            stack.call(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"',
                output=output,
            )
        stack.call("stop", "-t", "90", "redis", "elasticsearch", "minio")
        for key in ARCHIVES:
            helper(
                image,
                directory,
                f"tar -cf /backup/{key}.tar -C /data .",
                model["volumes"][key]["name"],
            )
        shutil.copyfile(env_file, directory / "runtime.env")
        if stack.image_tag:
            saved_env = directory / "runtime.env"
            lines = [
                line
                for line in saved_env.read_text().splitlines()
                if not line.startswith("RAGHUB_IMAGE_TAG=")
            ]
            saved_env.write_text("\n".join([*lines, "RAGHUB_IMAGE_TAG=" + stack.image_tag]) + "\n")
        filenames = ["postgres.dump", "runtime.env", *[key + ".tar" for key in ARCHIVES]]
        # Verify archives using a root helper: Docker namespace ownership may differ
        # from the host user's UID. Never weaken the private directory permissions.
        checksum_output = helper(
            image, directory, "cd /backup; sha256sum " + " ".join(filenames)
        ).decode()
        checksums = {line.split()[1]: line.split()[0] for line in checksum_output.splitlines()}
        save(
            directory / "manifest.json",
            {
                "format": 1,
                "project": stack.project,
                "created_at": datetime.now(UTC).isoformat(),
                "checksums": checksums,
                "volumes": list(ARCHIVES),
                "images": {name: item["image"] for name, item in model["services"].items()},
            },
        )
        (directory / "SHA256SUMS").write_text(checksum_output)
        helper(
            image,
            directory,
            "cd /backup; sha256sum -c SHA256SUMS; "
            "pg_restore --list postgres.dump >/dev/null; chmod 600 /backup/*",
        )
        # Keep writers stopped; restart only storage for migration.
        stack.call(
            "start",
            "--wait",
            "--wait-timeout",
            "240",
            *[name for name in STORAGE if name in active],
        )
    except Exception:
        stack.call("start", "--wait", "--wait-timeout", "240", *active)
        raise


def deploy(args):
    root = Path(args.root).resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise ValueError("Require a full immutable commit SHA")
    area = root / ".deploy"
    config = json.loads((area / "config.json").read_text())
    if shutil.disk_usage(root).free < config.get("min_free_bytes", 2 * 1024**3):
        raise ValueError("Insufficient free disk for deployment/backup; free space before retry")
    project = config["project"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]+", project):
        raise ValueError("Invalid Compose project")
    env_file = root / config.get("env_file", ".env.self-host")
    state_file = area / "state.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else None
    if state and state["sha"] == args.sha:
        print("Already deployed this SHA")
        return
    source_root = Path(state["release"]) if state else root
    source_files = state["files"] if state else config["initial_compose_files"]
    source = Stack(source_root, project, env_file, source_files, state["tag"] if state else None)
    old = source.model()
    active = source.call("ps", "--services", "--status", "running").decode().splitlines()
    if not all(name in active for name in ("api", *STORAGE)):
        raise ValueError("Existing API/storage must be running before automated upgrade")
    for identifier in source.call("ps", "-q").decode().splitlines():
        instance = json.loads(run(["docker", "inspect", identifier]))[0]
        if instance["Config"]["Labels"].get("com.docker.compose.project") != project:
            raise ValueError("Running container project mismatch")
        mounts = {row["Name"] for row in instance["Mounts"] if row["Type"] == "volume"}
        allowed = {row["name"] for row in old["volumes"].values()}
        if not mounts.issubset(allowed):
            raise ValueError("Running volumes differ from source Compose")
    releases = area / "releases"
    releases.mkdir(exist_ok=True)
    release = releases / f"{args.sha}-{time.time_ns()}"
    extract_release(args.archive, release)
    files = ["infrastructure/docker-compose.self-host.yml", *config.get("overlays", [])]
    if any("build" in file for file in files):
        raise ValueError("Automatic deploy is image-only; build override is forbidden")
    target = Stack(release, project, env_file, files, "sha-" + args.sha)
    new = target.model()
    verify_layout(old, new)
    services = [service for service in APP if service in active]
    target.call("pull", *services, "migrate")
    for image in {new["services"][name]["image"] for name in [*services, "migrate"]}:
        metadata = json.loads(run(["docker", "image", "inspect", image]))[0]
        if (metadata["Config"].get("Labels") or {}).get(
            "org.opencontainers.image.revision"
        ) != args.sha:
            raise ValueError("Image revision label does not match approved commit")
    backup_root = root / ".backups"
    backup_root.mkdir(exist_ok=True)
    destination = backup_root / f"auto-{args.sha}-{time.time_ns()}"
    phase = "backup"
    try:
        backup(source, old, env_file, destination, active)
        phase = "migration"
        target.call("run", "--rm", "--no-deps", "migrate")
        phase = "health"
        target.call("up", "-d", "--wait", "--wait-timeout", "240", "--pull", "never", *services)
        # Nginx must resolve recreated API/web container addresses.
        target.call("restart", "nginx")
        target.call("up", "-d", "--wait", "--wait-timeout", "120", "--pull", "never", "nginx")
        health_url = config.get("health_url", "http://127.0.0.1:8080/health/ready")
        with urllib.request.urlopen(health_url, timeout=15) as response:
            if response.status != 200 or json.load(response).get("status") != "ok":
                raise RuntimeError("Readiness check failed")
        save(
            state_file,
            {
                "sha": args.sha,
                "release": str(release),
                "files": files,
                "backup": str(destination),
                "tag": "sha-" + args.sha,
            },
        )
        save(area / "last-attempt.json", {"sha": args.sha, "phase": "complete"})
        print("PASS: deployed " + args.sha + "; verified backup: " + str(destination))
    except Exception:
        save(
            area / "last-attempt.json",
            {"sha": args.sha, "phase": phase, "status": "failed", "backup": str(destination)},
        )
        if phase != "backup":
            target.call("stop", "-t", "90", *[name for name in WRITERS if name in services])
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--archive", required=True)
    args = parser.parse_args()
    area = Path(args.root).resolve() / ".deploy"
    area.mkdir(mode=0o700, exist_ok=True)
    with (area / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        deploy(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit(f"Deploy stopped: {type(exc).__name__}: {exc}") from None
