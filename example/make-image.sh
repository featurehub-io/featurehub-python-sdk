#!/bin/sh
# the Dockerfile lives in the repository root so the image can include the local SDK
cd "$(dirname "$0")/.." && docker build --no-cache -t featurehub/python-example:1.0 .
