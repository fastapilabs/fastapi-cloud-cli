#!/usr/bin/env bash

set -e
set -x

uv run coverage run -m pytest tests ${@}
