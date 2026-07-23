# Changelog helpers.
#
# CHANGELOG.rst is managed with chloggen
# (https://github.com/open-telemetry/opentelemetry-go-build-tools/tree/main/chloggen).
# chloggen is a Go tool; these targets invoke it with `go run`, so only a Go
# toolchain is required (no Go dependency is added to this Python project).
#
# See docs/changelog-maintenance.rst.

CHLOGGEN_VERSION = v0.30.0
CHLOGGEN = go run go.opentelemetry.io/build-tools/chloggen@$(CHLOGGEN_VERSION)
CHLOGGEN_CONFIG = .chloggen/config.yaml

.PHONY: chlog-new chlog-validate chlog-preview chlog-update

# Create a new entry file named after the current branch.
chlog-new:
	$(CHLOGGEN) new --config $(CHLOGGEN_CONFIG) --filename $(shell git branch --show-current)

# Check that every pending entry is well-formed (what CI runs).
chlog-validate:
	$(CHLOGGEN) validate --config $(CHLOGGEN_CONFIG)

# Render the pending entries without writing anything.
chlog-preview:
	$(CHLOGGEN) update --config $(CHLOGGEN_CONFIG) --dry

# Compile the pending entries into a new CHANGELOG.rst section and delete them.
# Pass the heading text as VERSION, e.g.
#   make chlog-update VERSION="0.2.0 - 2026-08-01"
chlog-update:
ifndef VERSION
	$(error VERSION is required, e.g. make chlog-update VERSION="0.2.0 - 2026-08-01")
endif
	$(CHLOGGEN) update --config $(CHLOGGEN_CONFIG) --version "$(VERSION)"
