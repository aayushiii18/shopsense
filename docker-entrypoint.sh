#!/usr/bin/env bash
set -e

# Execute ShopSense Python container initialization and then launch command
exec python docker_entrypoint.py "$@"
