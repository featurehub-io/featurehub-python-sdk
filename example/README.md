# Setup

The example uses the SDK from the repository root (see `[tool.uv.sources]` in `pyproject.toml`),
so changes to the SDK are picked up without publishing it.

````
uv venv
source .venv/bin/activate
uv sync
uv run main.py
````

# Docker

The `Dockerfile` lives in the repository root so the image can include the local SDK. Build it
from the root (or run `./make-image.sh` from this folder):

````
docker build -t featurehub/python-example:1.0 .
````
