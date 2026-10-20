"""Unit tests for the injected-tree dependency manifest generator."""

from pathlib import Path
from sys import path as sys_path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys_path.insert(0, str(_REPO_ROOT / "scripts"))
sys_path.insert(0, str(_REPO_ROOT / "packages" / "dash0-opentelemetry" / "src"))

from dash0.opentelemetry.injector._packaging.requirements import (  # noqa: E402
    Requirement,
)
from dash0.opentelemetry.injector._packaging.version import Version  # noqa: E402
from generate_all_dependencies import (  # noqa: E402
    manifest_lines,
    normalize,
    read_tree,
)


def write_dist(tree: Path, name: str, version: str, requires: list[str]) -> None:
    """Create one ``.dist-info/METADATA`` inside an installed tree."""
    dist_info = tree / f"{name.replace('-', '_')}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    headers = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
    ]
    headers.extend(f"Requires-Dist: {requirement}" for requirement in requires)
    (dist_info / "METADATA").write_text("\n".join(headers) + "\n\n", encoding="utf-8")


def generate(tree: Path) -> list[str]:
    installed, demands = read_tree(tree)
    return manifest_lines(installed, demands)


def test_an_upstream_range_is_emitted_rather_than_the_installed_version(tmp_path):
    write_dist(tmp_path, "wrapt", "1.17.3", [])
    write_dist(
        tmp_path, "opentelemetry-instrumentation", "0.65b0", ["wrapt<3.0.0,>=1.0.0"]
    )

    assert "wrapt<3.0.0,>=1.0.0" in generate(tmp_path)
    assert "wrapt==1.17.3" not in generate(tmp_path)


def test_every_upstream_declaration_is_conjoined(tmp_path):
    write_dist(tmp_path, "wrapt", "1.17.3", [])
    write_dist(
        tmp_path, "opentelemetry-instrumentation", "0.65b0", ["wrapt<3.0.0,>=1.0.0"]
    )
    write_dist(
        tmp_path, "opentelemetry-instrumentation-redis", "0.65b0", ["wrapt>=1.12.1"]
    )

    line = next(line for line in generate(tmp_path) if line.startswith("wrapt"))
    specifier = Requirement(line).specifier
    assert specifier.contains(Version("1.12.1"))
    assert specifier.contains(Version("1.17.3"))
    assert not specifier.contains(Version("1.12.0"))
    assert not specifier.contains(Version("3.0.0"))


def test_a_curation_pin_from_the_distribution_is_ignored(tmp_path):
    write_dist(tmp_path, "pyyaml", "6.0.3", [])
    write_dist(tmp_path, "dash0-opentelemetry", "0.3.2", ["pyyaml==6.0.3"])

    assert "pyyaml" in generate(tmp_path)


def test_an_upstream_declaration_survives_a_curation_pin_on_the_same_package(tmp_path):
    write_dist(tmp_path, "psutil", "7.2.2", [])
    write_dist(tmp_path, "dash0-opentelemetry", "0.3.2", ["psutil==7.2.2"])
    write_dist(
        tmp_path,
        "opentelemetry-instrumentation-system-metrics",
        "0.65b0",
        ["psutil>=5.9.0,<8"],
    )

    line = next(line for line in generate(tmp_path) if line.startswith("psutil"))
    specifier = Requirement(line).specifier
    assert specifier.contains(Version("5.9.0"))
    assert not specifier.contains(Version("8.0.0"))


def test_a_package_nothing_depends_on_is_unconstrained(tmp_path):
    write_dist(tmp_path, "iniconfig", "2.1.0", [])

    assert generate(tmp_path) == ["iniconfig"]


def test_a_requirement_gated_on_an_extra_is_skipped(tmp_path):
    write_dist(tmp_path, "packaging", "26.3", [])
    write_dist(tmp_path, "psutil", "7.2.2", ['packaging ; extra == "dev"'])

    assert "packaging" in generate(tmp_path)


def test_a_marked_requirement_gets_its_own_line(tmp_path):
    write_dist(tmp_path, "typing-extensions", "4.16.0", [])
    write_dist(tmp_path, "opentelemetry-api", "1.44.0", ["typing-extensions>=4.5.0"])
    write_dist(
        tmp_path,
        "opentelemetry-sdk",
        "1.44.0",
        ['typing-extensions>=4.0 ; python_version < "3.11"'],
    )

    lines = generate(tmp_path)
    assert "typing-extensions>=4.5.0" in lines
    assert 'typing-extensions>=4.0; python_version < "3.11"' in lines


def test_every_generated_line_parses_with_the_vendored_packaging(tmp_path):
    """The bootstrap parses this file with its vendored subset, not packaging."""
    write_dist(tmp_path, "wrapt", "1.17.3", [])
    write_dist(tmp_path, "asgiref", "3.12.1", [])
    write_dist(tmp_path, "typing-extensions", "4.16.0", [])
    write_dist(tmp_path, "pyyaml", "6.0.3", [])
    write_dist(
        tmp_path,
        "opentelemetry-instrumentation",
        "0.65b0",
        [
            "wrapt<3.0.0,>=1.0.0",
            "asgiref~=3.0",
            'typing-extensions>=4.12 ; python_version < "3.13"',
        ],
    )
    write_dist(tmp_path, "dash0-opentelemetry", "0.3.2", ["pyyaml==6.0.3"])

    for line in generate(tmp_path):
        requirement = Requirement(line)
        assert requirement.name
        if requirement.specifier:
            requirement.specifier.contains(Version("1.0.0"))


def test_names_are_normalized(tmp_path):
    write_dist(tmp_path, "typing_extensions", "4.16.0", [])
    write_dist(tmp_path, "opentelemetry-api", "1.44.0", ["typing_extensions>=4.5.0"])

    assert "typing-extensions>=4.5.0" in generate(tmp_path)
    assert normalize("Typing_Extensions") == "typing-extensions"
