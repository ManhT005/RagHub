"""Offline-consistent backup/restore for one self-host installation.

Uses Docker and stdlib only. Archives contain secrets and must be stored privately.
Restore refuses existing target volumes and requires a different Compose project.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_VOLUMES = ("minio-data", "elasticsearch-data", "redis-data")
MODEL_VOLUMES = ("ollama-data", "huggingface-cache")


def run(command, *, output=None, input_file=None, allow_failure=False):
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdout=output or subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=input_file,
        check=False,
    )
    if result.returncode and not allow_failure:
        raise RuntimeError(
            f"{command[0]} operation failed (exit {result.returncode}); inspect service health/logs."
        )
    return result


def compose_command(args, *command):
    files = ["infrastructure/docker-compose.self-host.yml", *args.compose_override]
    return [
        "docker",
        "compose",
        "--env-file",
        args.env_file,
        "-p",
        args.project,
        *[item for file in files for item in ("-f", file)],
        "--profile",
        "local-ai",
        *command,
    ]


def compose(args, *command, **kwargs):
    return run(compose_command(args, *command), **kwargs)


def model(args):
    return json.loads(compose(args, "config", "--format", "json").stdout)


def archive_volume(image, volume, directory, key, *, restore=False):
    operation = (
        ["tar", "-xf", f"/backup/{key}.tar", "-C", "/data"]
        if restore
        else ["tar", "-cf", f"/backup/{key}.tar", "-C", "/data", "."]
    )
    run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0",
            "--entrypoint",
            "",
            "--mount",
            f"type=volume,src={volume},dst=/data" + ("" if restore else ",readonly"),
            "--mount",
            f"type=bind,src={directory},dst=/backup" + (",readonly" if restore else ""),
            image,
            *operation,
        ]
    )


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def backup(args):
    configuration = model(args)
    directory = Path(args.directory).resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Backup destination must be empty.")
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    active = (
        compose(args, "ps", "--services", "--status", "running")
        .stdout.decode()
        .splitlines()
    )
    try:
        for name in ("nginx", "api", "worker"):
            if name in active:
                compose(args, "stop", "-t", "90", name)
        print("Capture consistent database and offline data volumes", flush=True)
        with (directory / "postgres.dump").open("wb") as destination:
            compose(
                args,
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"',
                output=destination,
            )
        compose(args, "stop", "-t", "90", "elasticsearch", "minio", "redis")
        volumes = [*DATA_VOLUMES, *(MODEL_VOLUMES if args.include_models else ())]
        for key in volumes:
            archive_volume(
                configuration["services"]["postgres"]["image"],
                configuration["volumes"][key]["name"],
                directory,
                key,
            )
        shutil.copyfile(args.env_file, directory / "runtime.env")
        (directory / "runtime.env").chmod(0o600)
        manifest = {
            "format": 1,
            "project": args.project,
            "created_at": datetime.now(UTC).isoformat(),
            "images": {
                key: value["image"] for key, value in configuration["services"].items()
            },
            "volumes": volumes,
            "checksums": {
                path.name: checksum(path)
                for path in directory.iterdir()
                if path.is_file()
            },
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        for path in directory.iterdir():
            path.chmod(0o600)
        print(
            "PASS: database, storage, exact Elasticsearch data, Redis and runtime secrets backed up",
            flush=True,
        )
    finally:
        if active:
            compose(
                args,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
                "--no-deps",
                *active,
            )


def restore(args):
    directory = Path(args.directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != 1 or manifest["project"] == args.project:
        raise ValueError(
            "Restore requires a supported backup and a new Compose project."
        )
    allowed = {
        "postgres.dump",
        "runtime.env",
        *[f"{key}.tar" for key in (*DATA_VOLUMES, *MODEL_VOLUMES)],
    }
    for filename, expected in manifest["checksums"].items():
        if filename not in allowed or checksum(directory / filename) != expected:
            raise ValueError("Backup integrity check failed.")
    if not set(DATA_VOLUMES).issubset(manifest["volumes"]):
        raise ValueError("Backup is missing required data volumes.")
    if not set(manifest["volumes"]).issubset({*DATA_VOLUMES, *MODEL_VOLUMES}):
        raise ValueError("Unsupported backup volume.")
    required = {"postgres.dump", "runtime.env", *[f"{key}.tar" for key in manifest["volumes"]]}
    if set(manifest["checksums"]) != required:
        raise ValueError("Backup manifest must cover every required artifact.")
    configuration = model(args)
    for key in ("postgres-data", *manifest["volumes"]):
        volume = configuration["volumes"][key]["name"]
        if (
            run(["docker", "volume", "inspect", volume], allow_failure=True).returncode
            == 0
        ):
            raise ValueError(
                "Target volumes already exist; restore only to a fresh project."
            )
    if (
        configuration["services"]["elasticsearch"]["image"]
        != manifest["images"]["elasticsearch"]
    ):
        raise ValueError(
            "Restore requires the exact Elasticsearch image; upgrade after verification."
        )
    # Secret equality is checked without logging either environment.
    original = dict(
        line.split("=", 1)
        for line in (directory / "runtime.env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )
    current = configuration["services"]["api"]["environment"]
    if any(
        current.get(key) != original.get(key)
        for key in ("APP_SECRET_KEY", "PROVIDER_MASTER_KEY")
    ):
        raise ValueError(
            "Restore must preserve APP_SECRET_KEY and PROVIDER_MASTER_KEY."
        )
    for key in manifest["volumes"]:
        volume = configuration["volumes"][key]["name"]
        run(
            [
                "docker",
                "volume",
                "create",
                "--label",
                f"com.docker.compose.project={args.project}",
                "--label",
                f"com.docker.compose.volume={key}",
                volume,
            ]
        )
        archive_volume(
            configuration["services"]["postgres"]["image"],
            volume,
            directory,
            key,
            restore=True,
        )
    compose(args, "up", "-d", "--wait", "--wait-timeout", "120", "postgres")
    with (directory / "postgres.dump").open("rb") as source:
        compose(
            args,
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
            input_file=source,
        )
    compose(
        args,
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "240",
        "api",
        "worker",
        "nginx",
        "ollama",
    )
    print(
        "PASS: restored new installation; run self-host-smoke.py --verify-only before switching traffic",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("backup", "restore", "upgrade"))
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--directory", required=True)
    parser.add_argument("--compose-override", action="append", default=[])
    parser.add_argument("--include-models", action="store_true")
    parser.add_argument("--image-tag", help="New immutable image tag for upgrade")
    args = parser.parse_args()
    if args.command == "upgrade" and (
        not args.image_tag
        or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", args.image_tag)
    ):
        parser.error("Upgrade requires --image-tag with a valid immutable tag.")
    if args.command == "restore":
        restore(args)
    else:
        backup(args)
        if args.command == "upgrade":
            env_file = Path(args.env_file)
            previous = env_file.read_text(encoding="utf-8")
            lines = [
                line
                for line in previous.splitlines()
                if not line.startswith("RAGHUB_IMAGE_TAG=")
            ]
            env_file.write_text(
                "\n".join([*lines, f"RAGHUB_IMAGE_TAG={args.image_tag}"]) + "\n",
                encoding="utf-8",
            )
            env_file.chmod(0o600)
            compose(args, "pull")
            compose(args, "stop", "-t", "90", "nginx", "api", "worker")
            compose(args, "run", "--rm", "migrate")
            compose(
                args,
                "up",
                "-d",
                "--wait",
                "--wait-timeout",
                "240",
                "api",
                "worker",
                "nginx",
            )
            print(
                "Upgrade health passed; run application smoke before accepting traffic.",
                flush=True,
            )


if __name__ == "__main__":
    main()
