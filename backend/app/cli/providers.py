"""python -m app.cli.providers import-env --organization-id UUID [--fill-legacy-gemini]."""

import argparse
import asyncio
from uuid import UUID

from app.core.database import SessionFactory, engine
from app.modules.ai_providers.bootstrap import ProviderBootstrapService


async def run(args):
    import app.models  # noqa: F401

    try:
        async with SessionFactory() as session:
            async with session.begin():
                imported = await ProviderBootstrapService(session).import_env(
                    args.organization_id, fill_legacy_gemini=args.fill_legacy_gemini
                )
                identities = [(item.catalog_id, str(item.id)) for item in imported]
            for catalog_id, connection_id in identities:
                print(
                    f"Credential imported: {catalog_id} connection={connection_id}; "
                    "test from AI Providers"
                )
            print(f"Imported {len(identities)} connections; existing credentials were preserved.")
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["import-env"])
    parser.add_argument("--organization-id", required=True, type=UUID)
    parser.add_argument("--fill-legacy-gemini", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
