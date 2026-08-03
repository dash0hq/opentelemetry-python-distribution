#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../.."

COMMIT_MSG=$(git log -1 --pretty=%B)

# Match: "docs: update changelog to prepare release vX.Y.Z[pre-release-suffix]"
VERSION_PATTERN='^docs: update changelog to prepare release (v[0-9]+\.[0-9]+\.[0-9]+(([ab]|rc)[0-9]+|\.post[0-9]+)?)$'
if [[ "$COMMIT_MSG" =~ $VERSION_PATTERN ]]; then
  VERSION="${BASH_REMATCH[1]}"
  echo "Found release commit for version: $VERSION"

  echo "Creating tag $VERSION"
  git config user.name d0etu
  git config user.email d0etu@users.noreply.github.com
  git tag "$VERSION"
  git push origin "$VERSION"
  echo "Successfully created and pushed tag: $VERSION"
else
  echo "Most recent commit is not a release commit — nothing to do."
fi
