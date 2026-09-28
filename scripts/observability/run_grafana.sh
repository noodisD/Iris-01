#!/usr/bin/env bash
# Optional local Grafana LGTM. IRIS itself stays one service (ADR-0004).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if docker container inspect iris-lgtm >/dev/null 2>&1; then
  docker start iris-lgtm
else
  docker run -d --name iris-lgtm --restart unless-stopped \
    -p 127.0.0.1:3000:3000 \
    -p 127.0.0.1:4317:4317 \
    -p 127.0.0.1:4318:4318 \
    -v iris_lgtm:/data \
    -v "$here/grafana/dashboards.yaml:/otel-lgtm/grafana/conf/provisioning/dashboards/iris.yaml:ro" \
    -v "$here/grafana/iris-chokepoints.json:/otel-lgtm/grafana/conf/provisioning/dashboards/iris/iris-chokepoints.json:ro" \
    -e PROMETHEUS_EXTRA_ARGS="--storage.tsdb.retention.time=30d" \
    grafana/otel-lgtm:0.34.0
fi

echo "Grafana: http://127.0.0.1:3000 (admin/admin)"
echo "Set OBS_OTLP_ENDPOINT=http://127.0.0.1:4318 and restart IRIS to export."
