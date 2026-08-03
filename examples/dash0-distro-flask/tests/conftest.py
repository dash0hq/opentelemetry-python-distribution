"""Session-scoped fixture that runs the Docker Compose stack and returns the
path to the output directory containing the JSONL telemetry files."""

from os import environ, getgid, getuid, makedirs
from os.path import abspath, dirname, exists, join
from shutil import rmtree
from subprocess import run
from time import sleep

from pytest import fixture

DEMO_DIR = dirname(dirname(abspath(__file__)))
OUTPUT_DIR = join(DEMO_DIR, "output")
COMPOSE_FILE = join(DEMO_DIR, "docker-compose.yml")


def pytest_addoption(parser):
    parser.addoption(
        "--no-docker",
        action="store_true",
        default=False,
        help="Skip Docker; use the existing output/ directory.",
    )


def _env():
    return {**environ, "SCRIPT_UID": str(getuid()), "SCRIPT_GID": str(getgid())}


@fixture(scope="session")
def output_dir(request):
    """Run the full Docker Compose stack and return the output directory path.

    With --no-docker the existing output/ directory is used as-is.
    """
    if request.config.getoption("--no-docker"):
        return OUTPUT_DIR

    env = _env()

    run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "--timeout", "10"],
        env=env,
    )

    if exists(OUTPUT_DIR):
        rmtree(OUTPUT_DIR)
    makedirs(OUTPUT_DIR)

    makedirs(join(DEMO_DIR, "python-agent"), exist_ok=True)

    result = run(
        ["docker", "compose", "-f", COMPOSE_FILE, "up", "--detach"],
        env=env,
    )
    if result.returncode != 0:
        run(["docker", "compose", "-f", COMPOSE_FILE, "logs"], env=env)
        result.check_returncode()
    # Wait for the traffic generator to finish (it exits after sending requests).
    run(
        ["docker", "compose", "-f", COMPOSE_FILE, "wait", "traffic"],
        check=True,
        env=env,
    )
    # Brief pause so the app flushes the last spans to the collector.
    sleep(2)
    run(
        ["docker", "compose", "-f", COMPOSE_FILE, "down", "--timeout", "10"],
        check=True,
        env=env,
    )

    return OUTPUT_DIR
