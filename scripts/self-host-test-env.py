"""Generate private disposable installation credentials for local/CI smoke tests."""

import argparse
import json
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default=".")
    parser.add_argument("--port", type=int, default=18082)
    args = parser.parse_args()
    destination = Path(args.directory)
    destination.mkdir(parents=True, exist_ok=True)
    env = destination / ".env.selfhost-test"
    owner = destination / ".env.selfhost-owner.json"
    if env.exists() or owner.exists():
        raise SystemExit(
            "Test configuration already exists; refusing to replace credentials."
        )
    env.write_text(
        "APP_ENV=selfhost\nRAGHUB_IMAGE_TAG=validation\nLOCAL_IMAGE_PREFIX=raghub-selfhost-test\n"
        f"HTTP_PORT={args.port}\nHTTP_BIND_ADDRESS=127.0.0.1\nFRONTEND_URL=http://localhost:{args.port}\n"
        "POSTGRES_DB=raghub\nPOSTGRES_USER=raghub\nS3_ACCESS_KEY=raghub\nS3_BUCKET=raghub-documents\n"
        "PROXY_NETWORK_SUBNET=172.31.83.0/24\nPROXY_IP=172.31.83.10\n"
        "PUBLIC_CHAT_TRUSTED_PROXY_CIDRS=172.31.83.10/32\nOLLAMA_MODEL=gemma3:1b\n"
        "PUBLIC_CHAT_STREAM_TIMEOUT_SECONDS=300\nCHAT_PROVIDER_TIMEOUT_SECONDS=120\n"
        + "".join(
            f"{key}={secrets.token_urlsafe(36)}\n"
            for key in (
                "APP_SECRET_KEY",
                "PROVIDER_MASTER_KEY",
                "POSTGRES_PASSWORD",
                "S3_SECRET_KEY",
            )
        ),
        encoding="utf-8",
    )
    owner.write_text(
        json.dumps(
            {
                "email": "selfhost-owner@example.com",
                "password": secrets.token_urlsafe(24),
            }
        ),
        encoding="utf-8",
    )
    env.chmod(0o600)
    owner.chmod(0o600)
    print("Private test environment and owner input created.")


if __name__ == "__main__":
    main()
