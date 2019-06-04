#!/bin/bash

# Commit back to the repository
# version number, push the tag back to the remote.

set -ex

# Tag and push
tag=$(semversioner current-version)

# Commit
git add .
git commit -m "Update files for new version '${tag}' [skip ci]"
git push origin ${BITBUCKET_BRANCH}

# Tag
git tag -a -m "Tagging for release ${tag}" "${tag}"
git push origin ${tag}
