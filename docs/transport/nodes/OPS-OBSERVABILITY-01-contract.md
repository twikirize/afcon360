# OPS-OBSERVABILITY-01 — Production Observability (Minimal, Managed)

## Objective
Enable "button fails → I see the error instantly" on Oracle Cloud **without** custom consoles, self-hosted infra, or log noise.

## Authorized Scope
1. **Sentry (SaaS, free tier)**
   - Python SDK (`sentry-sdk[flask]`) + Browser SDK via CDN
   - DSN stored in `.env.prod` (never committed)
   - 5k errors/mo, 30-day retention, replaysOnErrorSampleRate=1.0

2. **OpenTelemetry auto-instrumentation**
   - `opentelemetry-instrument` wrapper (zero code changes)
   - Exporters: OTLP → OCI APM endpoint (native)
   - Service name: `afcon360`

3. **OCI Logging / Logging Analytics**
   - Fluent Bit sidecar (OCI-provided image) tails `/var/log/afcon360/*.json`
   - Existing structured `app.logger` JSON lines flow automatically
   - Retention: 90 days default

4. **Correlation-ID propagation**
   - Backend: `X-Correlation-ID` header → `flask.g.correlation_id` → every log line
   - Frontend: meta tag `<meta name="correlation-id">` → Sentry `trace_id`

5. **Feature flag guard**
   - Reuse `system_config` table key `OBSERVABILITY_ENABLED` (default `true`)
   - All three components no-op when flag is `false`

## Exclusions
- No custom Grafana/Prometheus/Jaeger/Loki deployment
- No new VMs, no Kubernetes Operators
- No Cloudflare Workers for observability (Cloudflare ≠ APM)
- No changes to wallet, KYC, or identity modules

## Secrets / Config
| Secret | Location | Rotation |
|--------|----------|----------|
| `SENTRY_DSN` | `.env.prod` (pgpass-protected) | Manual, 90-day |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `.env.prod` (OCI APM endpoint) | Oracle-managed |
| `OCI_LOGGING_AGENT_CONFIG` | OCI Console (not in repo) | Oracle-managed |

## Rollout Plan
1. **Canary** — enable flag for `app_owner` user only (via `system_config` override)
2. Verify: error appears in Sentry, trace in OCI APM, log query returns correlation-ID
3. **Full** — flip flag to `true` for all users
4. **Rollback** — flip flag to `false` instantly

## Acceptance Criteria (Gate = PASS)
1. `curl -X POST /api/transport/book -H "X-Correlation-ID: test-123" -d '{}'` → 500 error appears in Sentry UI within 30 s with `test-123` tag.
2. OCI APM console shows trace for same request with spans: Flask → SQLAlchemy → PostgreSQL.
3. OCI Logging Analytics query `correlation_id = "test-123"` returns ≥ 3 log lines (request, error, audit).
4. Setting `OBSERVABILITY_ENABLED=false` stops all telemetry egress (verified by network tab).

## Verification Commands
```bash
# 1. Sentry test
python -c "import sentry_sdk; sentry_sdk.capture_message('OPS-OBSERVABILITY-01 smoke test')"
# 2. OTel trace
opentelemetry-instrument --traces_exporter otlp flask run &
curl -H "X-Correlation-ID: trace-test" http://127.0.0.1:5000/api/health
# 3. OCI log query (run in Cloud Shell)
oci logging-search search-logs --log-group-id <id> --query 'correlation_id = "trace-test"'
```

## Risk
- **LOW** — all components are read-only telemetry; feature flag killswitch; no schema changes.

## Follow-ups (deferred)
- Custom Sentry dashboards per module
- Alert rules (error-rate > 1 %, p99 > 2 s) — separate node
- Frontend session replay sampling tuning — separate node