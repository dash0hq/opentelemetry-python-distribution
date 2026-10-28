"""Fail the image build when a dash0 distribution came from the package index.

The image installs the workspace wheels by file path so that the suite
exercises this checkout rather than the last release. That depends on
``/wheels/*.whl`` covering every dash0-owned distribution in the dependency
closure. A distribution missing from it resolves from the index instead and
the install still succeeds, which puts released code back in the container
with nothing to signal it.

pip records where each distribution came from in ``direct_url.json``, which it
writes only for an install from a path or a URL, so a ``file://`` origin is
what proves the checkout supplied it.
"""

from importlib.metadata import distributions
from json import loads

INDEX: str = "the package index"

origins: dict[str, str] = {}
for distribution in distributions():
    name: str | None = distribution.metadata["Name"]
    if name is None or not name.startswith("dash0-"):
        continue
    direct_url: str | None = distribution.read_text("direct_url.json")
    origins[name] = loads(direct_url)["url"] if direct_url else INDEX

if not origins:
    raise SystemExit(
        "no dash0 distribution is installed, so the image does not carry the "
        "distribution under test at all"
    )

from_index: list[str] = sorted(
    name for name, url in origins.items() if not url.startswith("file://")
)
if from_index:
    raise SystemExit(
        f"these dash0 distributions did not come from /wheels: {from_index}. "
        "uv build --all-packages has to produce a wheel for every workspace "
        "member in the dependency closure, or the suite tests the released "
        "code instead of this checkout."
    )

print(f"every dash0 distribution came from /wheels: {sorted(origins)}")
