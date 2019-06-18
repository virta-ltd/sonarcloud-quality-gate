#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"/..

./setup.sh

. venv/bin/activate
python -m doctest -v pipe/pipe.py
