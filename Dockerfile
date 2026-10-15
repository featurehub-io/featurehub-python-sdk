# Builds the example app in example/ against the SDK in this (root) folder.
# Build from the repository root: docker build -t featurehub/python-example:1.0 .
FROM python:3.14-alpine

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

WORKDIR /app/example

# Install the example's third party dependencies using its lockfile, without the example or the local SDK
COPY example/pyproject.toml example/uv.lock ./
RUN uv sync --frozen --no-cache --no-install-project --no-install-local

# Copy the SDK (resolved by the example via path = "..")
COPY pyproject.toml README.md /app/
COPY featurehub_sdk /app/featurehub_sdk

# Copy the rest of the example
COPY example/ ./

# Complete the installation (installs the SDK and the example itself)
RUN uv sync --frozen --no-cache
CMD ["uv", "run", "--no-sync", "main.py"]
