"""Seed a throwaway contract-test scope and emit a Postman environment.

Bootstraps owner -> login -> organization -> workspace -> chatbot, then
writes real IDs and the token to a temp environment file. Intended for
local runs and CI against ephemeral stacks only; never run against
production data.

Usage (from backend/):
    python scripts/seed_contract_env.py --base-url http://localhost:8000 \\
        --email owner@example.com --password <pass> --out /tmp/contract-env.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    client = httpx.Client(base_url=base, timeout=30.0)
    login = client.post("/api/v1/auth/login",
                        json={"email": args.email, "password": args.password})
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org = client.post("/api/v1/organizations",
                      json={"name": "Contract Env", "slug": "contract-env"}, headers=headers)
    org.raise_for_status()
    org_id = org.json()["id"]
    headers["X-Organization-ID"] = org_id
    workspace = client.post("/api/v1/workspaces",
                            json={"name": "Contract WS", "slug": "contract-ws"},
                            headers=headers)
    workspace.raise_for_status()
    workspace_id = workspace.json()["id"]
    chatbot = client.post(f"/api/v1/workspaces/{workspace_id}/chatbots",
                          json={"name": "Contract Bot"}, headers=headers)
    chatbot.raise_for_status()
    env = {
        "name": "RagHub contract (generated)",
        "values": [
            {"key": "base_url", "value": base, "enabled": True},
            {"key": "admin_token", "value": token, "enabled": True},
            {"key": "organization_id", "value": org_id, "enabled": True},
            {"key": "workspace_id", "value": workspace_id, "enabled": True},
            {"key": "chatbot_id", "value": chatbot.json()["id"], "enabled": True},
            {"key": "document_id", "value": "00000000-0000-0000-0000-000000000000",
             "enabled": True},
            {"key": "embed_key", "value": "DISABLED", "enabled": True},
            {"key": "search_query", "value": "tuyen sinh", "enabled": True},
        ],
    }
    out = Path(args.out)
    out.write_text(json.dumps(env, indent=2), encoding="utf-8")
    print(f"seeded org={org_id} workspace={workspace_id} -> {out}")


if __name__ == "__main__":
    main()
