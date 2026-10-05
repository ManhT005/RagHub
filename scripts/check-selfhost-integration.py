"""Run the backend's live integration/widget suite in an ephemeral test container.

Infrastructure stays on its private Docker network. Test dependencies are installed
only under /tmp in the disposable container; the application image is unchanged.
"""

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = """
import json, os, subprocess, sys
from pathlib import Path
result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--target', '/tmp/test-deps',
                        'pytest==8.3.5', 'pytest-asyncio==0.26.0'], capture_output=True)
assert result.returncode == 0, 'Test dependency installation failed'
sys.path.insert(0, '/tmp/test-deps')
sys.path.insert(0, '/checks')
owner = json.loads(Path('/checks/owner.json').read_text())
os.environ.update(RAGHUB_TEST_BASE_URL='http://nginx', RAGHUB_WIDGET_TEST_URL='http://nginx',
                  RAGHUB_TEST_DATABASE_URL=os.environ['DATABASE_URL'],
                  RAGHUB_TEST_REDIS_URL=os.environ['REDIS_URL'],
                  RAGHUB_TEST_EMAIL=owner['email'], RAGHUB_TEST_PASSWORD=owner['password'])
import pytest
raise SystemExit(pytest.main(['-p', 'no:cacheprovider', '-m', 'integration', '/checks/tests',
    '--override-ini', 'markers=integration: requires Docker infrastructure',
    '--override-ini', 'asyncio_mode=auto', '--override-ini',
    'asyncio_default_fixture_loop_scope=function', '-q', '--tb=short']))
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--owner-file", type=Path, required=True)
    args = parser.parse_args()
    if "test" not in args.project:
        parser.error("Run the integration suite on an explicitly selected test project")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            args.env_file,
            "-p",
            args.project,
            "-f",
            "infrastructure/docker-compose.self-host.yml",
            "-f",
            "infrastructure/docker-compose.self-host.build.yml",
            "--profile",
            "local-ai",
            "run",
            "--rm",
            "--no-deps",
            "-T",
            "-v",
            f"{ROOT / 'backend/tests'}:/checks/tests:ro",
            "-v",
            f"{args.owner_file.resolve()}:/checks/owner.json:ro",
            "api",
            "python",
            "-c",
            RUNNER,
        ],
        cwd=ROOT,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
