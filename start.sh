#!/usr/bin/env bash
# Compatibility entry point for existing installations.
exec bash "$(dirname -- "$0")/setup.sh" "$@"
