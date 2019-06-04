#!/usr/bin/env bash
#
# Release to dockerhub.
#
# Required globals:
#   DOCKERHUB_USERNAME
#   DOCKERHUB_PASSWORD

set -euo pipefail

IMAGE=$1
EXTRA_TAG=${2-}
VERSION=$(semversioner current-version)

docker login --username "${DOCKERHUB_USERNAME}" --password-stdin <<< "${DOCKERHUB_PASSWORD}"
docker build -t ${IMAGE} .

if [ "${EXTRA_TAG}" ]; then
    TAG="${VERSION}.${BITBUCKET_BUILD_NUMBER}-${EXTRA_TAG}"
    docker tag ${IMAGE} ${IMAGE}:${TAG}
    docker push ${IMAGE}:${TAG}
else
    docker tag ${IMAGE} ${IMAGE}:${VERSION}
    docker push ${IMAGE}
fi
