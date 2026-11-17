#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
major=${1:?OS major required}
name="fleetops-offline-test$major-${2:-run}"
engine=${CONTAINER_ENGINE:-podman}
"$engine" run --name "$name" --network none --security-opt label=disable -v "$PWD:/src:ro" "docker.io/rockylinux/rockylinux:$major" bash -c "cd /src/releases/2.1.0/el$major && bash install.sh && runuser -u fleetops -- /opt/fleetops/venv/bin/python /src/tests/runtime_smoke.py"
