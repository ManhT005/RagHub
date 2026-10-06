"""Validate resolved local/GHCR models without printing environment values or using Docker daemon."""

import json
import os
import re
import subprocess
from ipaddress import ip_address, ip_network
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_SERVICES = (
    "api", "worker", "worker-provider", "migrate", "admin-web", "chat-widget", "widget-demo",
    "nginx",
)
BACKEND_SERVICES = ("api", "worker", "worker-provider", "migrate")
RAG_QUEUES = {"rag-ingestion", "rag-embedding", "rag-reindex"}
PROFILE_OWNED_KEYS = (
    "RAG_WORKER_CONCURRENCY", "RAG_RETRIEVAL_CANDIDATES", "RAG_RERANK_SOURCE_COUNT",
    "RAG_RERANK_TOP_N", "RAG_RERANKER_ENABLED", "RAG_ADAPTIVE_RERANK_ENABLED",
    "PROVIDER_POOL_MAX_ACTIVE_JOBS_PER_WORKSPACE",
)
CONFIG_KEYS = set()
for path in (ROOT / "infrastructure").glob("docker-compose*.yml"):
    CONFIG_KEYS.update(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", path.read_text(encoding="utf-8")))
CLEAN_ENV = {key: value for key, value in os.environ.items() if key not in CONFIG_KEYS}
DEPLOY_ENV = {
    "RAGHUB_IMAGE_PREFIX": "ghcr.io/example/raghub",
    "RAGHUB_IMAGE_TAG": "sha-" + "1" * 40,
    "APP_SECRET_KEY": "compose-validation-only-app-key",
    "PROVIDER_MASTER_KEY": "compose-validation-only-provider-key",
    "POSTGRES_PASSWORD": "compose-validation-only-db-key",
    "S3_SECRET_KEY": "compose-validation-only-storage-key",
}


def resolve(entrypoint, env_file, overrides=None, expect_success=True):
    result = subprocess.run(
        ["docker", "compose", "--env-file", env_file,
         *[arg for path in ([entrypoint] if isinstance(entrypoint, str) else entrypoint) for arg in ("-f", path)],
         "--profile", "local-ai", "--profile", "ocr", "config", "--format", "json"],
        cwd=ROOT, env={**CLEAN_ENV, **(overrides or {})},
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if not expect_success:
        assert result.returncode != 0, "Deployment accepted a missing required setting"
        return None
    if result.returncode:
        # Config errors can include secrets; only print a redacted diagnostic.
        raise RuntimeError(f"Compose validation failed for {entrypoint}; exit {result.returncode}")
    return json.loads(result.stdout)


def queues(service):
    args = " ".join(service["command"]).split()
    value = next(arg for arg in args if arg.startswith("--queues="))
    return set(value.removeprefix("--queues=").split(","))


def check_shared(model):
    services = model["services"]
    assert len({services[name]["image"] for name in BACKEND_SERVICES}) == 1
    assert services["migrate"]["command"] == ["alembic", "upgrade", "head"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert "alembic" not in services["api"]["command"]
    assert services["worker"]["healthcheck"]
    assert services["worker-provider"]["healthcheck"]
    assert services["worker-ocr"]["command"][-1] == "--queues=rag-ocr"
    assert "rag-ocr" not in " ".join(services["worker"]["command"])
    # Provider jobs must never share an execution slot with user-facing ingestion.
    assert queues(services["worker"]) == RAG_QUEUES
    assert "rag-provider" in queues(services["worker-provider"])
    assert not queues(services["worker-provider"]) & RAG_QUEUES
    assert "--concurrency=1" in " ".join(services["worker-provider"]["command"])
    # RAG_HARDWARE_PROFILE owns these keys; Compose must not inject competing defaults.
    for name in BACKEND_SERVICES:
        environment = services[name]["environment"]
        for key in PROFILE_OWNED_KEYS:
            assert environment.get(key) in (None, ""), f"{name} hard-codes {key}"
    assert "postgres-data" in model["volumes"]
    for service in services.values():
        assert service["logging"]["options"]["max-size"] == "10m"


def main():
    for target in ("runtime", "local-ai"):
        local = resolve("infrastructure/docker-compose.yml", ".env.example", {
            "BACKEND_IMAGE_TARGET": target,
        })
        check_shared(local)
        for name in ("api", "admin-web", "chat-widget", "widget-demo", "nginx"):
            assert local["services"][name]["build"]
        for name in ("worker", "worker-provider", "migrate"):
            assert "build" not in local["services"][name]
            assert local["services"][name]["pull_policy"] == "never"
        assert local["services"]["api"]["build"]["target"] == target
        api_build = local["services"]["api"]["build"]
        assert Path(api_build["context"]).resolve() == ROOT
        assert api_build["dockerfile"] == "backend/Dockerfile"
        for name in ("api", "worker", "worker-provider"):
            mounts = {
                volume["target"]: Path(volume["source"]).resolve()
                for volume in local["services"][name]["volumes"]
                if volume["type"] == "bind"
            }
            assert mounts["/app/app"] == ROOT / "backend/app"
            assert mounts["/app/raghub_core"] == ROOT / "raghub-core/src/raghub_core"
            assert all(path.is_dir() for path in mounts.values())
        for service in local["services"].values():
            assert all(port["host_ip"] == "127.0.0.1" for port in service.get("ports", []))
        print(f"Local Compose ({target}): valid")

    for suffix in ("", "-local-ai"):
        deployment = resolve("infrastructure/docker-compose.ghcr.yml", ".env.ghcr.example", {
            **DEPLOY_ENV, "BACKEND_IMAGE_SUFFIX": suffix,
        })
        check_shared(deployment)
        for name, service in deployment["services"].items():
            assert "build" not in service, f"Deployment builds {name} from source"
            assert not any(volume["type"] == "bind" for volume in service.get("volumes", []))
            assert name == "nginx" or not service.get("ports"), f"Deployment exposes {name}"
        for name in APP_SERVICES:
            image = deployment["services"][name]["image"]
            assert image.startswith(DEPLOY_ENV["RAGHUB_IMAGE_PREFIX"] + "/")
            assert image.endswith(DEPLOY_ENV["RAGHUB_IMAGE_TAG"] + (
                suffix if name in BACKEND_SERVICES else ""
            ))
        api = deployment["services"]["api"]
        assert DEPLOY_ENV["POSTGRES_PASSWORD"] in api["environment"]["DATABASE_URL"]
        proxy = deployment["services"]["nginx"]["networks"]["ingress"]["ipv4_address"]
        assert ip_address(proxy) in ip_network(api["environment"]["PUBLIC_CHAT_TRUSTED_PROXY_CIDRS"])
        print(f"GHCR Compose ({suffix or 'runtime'}): valid")

    selfhost_path = "infrastructure/docker-compose.self-host.yml"
    selfhost_env = ".env.self-host.example"
    selfhost = resolve(selfhost_path, selfhost_env, DEPLOY_ENV)
    check_shared(selfhost)
    for name, service in selfhost["services"].items():
        assert name == "nginx" or not service.get("ports"), f"Self-host exposes {name}"
        assert not service.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices")
    assert selfhost["services"]["api"]["environment"]["APP_ENV"] == "selfhost"
    assert selfhost["services"]["api"]["image"].endswith("-local-ai")
    for name in BACKEND_SERVICES:
        profile = selfhost["services"][name]["environment"]["RAG_HARDWARE_PROFILE"]
        assert profile in {"lite_cpu", "standard_cpu", "gpu"}, f"{name} profile {profile}"
    gpu = resolve([selfhost_path, "infrastructure/docker-compose.gpu.yml"], selfhost_env, DEPLOY_ENV)
    devices = gpu["services"]["ollama"]["deploy"]["resources"]["reservations"]["devices"]
    assert devices[0]["driver"] == "nvidia"
    for required in DEPLOY_ENV.keys() - {"RAGHUB_IMAGE_PREFIX"}:
        resolve(selfhost_path, selfhost_env, {
            key: value for key, value in DEPLOY_ENV.items() if key != required
        }, expect_success=False)
    print("Self-host CPU/GPU packaging and required secrets: valid")

    source_build = resolve(
        [selfhost_path, "infrastructure/docker-compose.self-host.build.yml"],
        selfhost_env, DEPLOY_ENV,
    )
    check_shared(source_build)
    api_build = source_build["services"]["api"]["build"]
    assert Path(api_build["context"]).resolve() == ROOT
    assert api_build["dockerfile"] == "backend/Dockerfile"
    assert api_build["target"] == "local-ai"
    print("Self-host source build with standalone core: valid")

    for required in DEPLOY_ENV.keys() - {"RAGHUB_IMAGE_PREFIX"}:
        resolve("infrastructure/docker-compose.ghcr.yml", ".env.ghcr.example", {
            key: value for key, value in DEPLOY_ENV.items() if key != required
        }, expect_success=False)
    print("Required deployment settings: enforced")


if __name__ == "__main__":
    main()
