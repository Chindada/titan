#!/bin/bash

VERSION=v1.0
set -e

docker buildx build \
    --ssh default \
    -f Dockerfile \
    -t ghcr.io/chindada/titan:$VERSION .
docker system prune --volumes -f
