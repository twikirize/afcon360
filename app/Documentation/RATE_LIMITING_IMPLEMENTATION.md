# Rate Limiting Implementation

## Overview

This document maps AFCON360's current rate-limiting implementation against a production-ready architecture for request throttling, abuse prevention, and security defense.

---

## 1. Gateway / Edge Layer

| Component | Status | Detail |
|-----------|--------|--------|
| Nginx `limit_req_zone` | **Missing** | `docker/nginx/afcon360.conf` has no edge-layer rate-limiting directives |
| WAF integration | **Missing** | No ModSecurity / Cloudflare-style rules in the proxy layer |
| TLS termination + headers | **Partial** | Nginx passes `X-Real-IP` and `X-Forwarded-For` (correct), but does not enforce limits at the edge |

**Current behavior:** All rate limiting happens inside Flask. The Nginx layer is a pure reverse proxy.

---

## 2. Multi-Identity Keys

| Identity | Status | Implementation |
|----------|--------|----------------|
| User ID | **Partial** | Wallet routes key by `current_user.id`; other modules default to IP |
| API Key | **Missing** | No `api_key:` namespace in Flask-Limiter |
| IP Address | **Active** | `get_remote_address` is the default key func everywhere |
| Device ID | **Missing** | Not extracted or used as a rate-limit key |
| JWT Subject | **Missing** | No `jwt_sub:` rate-limit namespace |
| Organization ID | **Missing** | No `org:` rate-limit namespace |

**Current behavior:** Flask-Limiter defaults to IP-based keys. Wallet endpoints override with `lambda: current_user.id`. There is no multi-identity aggregation.

---

## 3. Redis Cluster

| Feature | Status | Detail |
|---------|--------|--------|
| Redis backend | **Active** | `RATELIMIT_STORAGE_URI = REDIS_URL` |
| Memory fallback | **Active** | Falls back to `memory://` if Redis is unavailable |
| Atomic INCR + EXPIRE | **Active** | Custom event limiter uses `pipeline().incr().expire()` |
| Key namespacing | **Partial** | Flask-Limiter prefixes keys (`rl::`); custom keys use `rate_limit:` |
| Separate Redis DB | **Missing** | Same Redis DB (`/0`) is shared with cache, sessions, and Celery |
| Lua scripts | **Missing** | No Lua atomic sliding-window scripts |

**Current behavior:** Single Redis instance / single DB. No cluster, no Lua scripts, no separate key isolation.

---

## 4. Sliding Window Algorithm

| Algorithm | Status | Detail |
|-----------|--------|--------|
| Fixed Window | **Active** | `strategy="fixed-window"` in `app/extensions.py` and `app/config.py` |
| Sliding Window | **Missing** | Not configured |
| Token Bucket | **Missing** | Not configured |

**Current behavior:** Fixed-window is the only strategy. This creates burst-risk at window boundaries (e.g., 100 requests at :59 and 100 more at :01).

---

## 5. Multi-Level Limits

| Endpoint / Resource | Current Limit | Status |
|---------------------|---------------|--------|
| Global default | 2000/day; 500/hr | **Active** |
| Register | 10/min | **Active** |
| Login | 5–10/hr | **Active** |
| Password reset | 5/hr | **Active** |
| Media upload | 50/min | **Active** |
| Media admin | 20/min | **Active** |
| Accommodation checkout | 5/min | **Active** |
| Accommodation cancel | 10/min | **Active** |
| Accommodation host actions | 20/min | **Active** |
| Wallet PIN | 10/min | **Active** |
| Wallet deposit | 10/min; 50/hr (user-keyed) | **Active** |
| Wallet withdraw / transfer | 5/min; 20/hr (user-keyed) | **Active** |
| Event create | 5/300s (custom Redis) | **Active** |
| Event checkin | 60/60s (custom Redis) | **Active** |
| Transport provider registration | 10/hr (in-memory) | **Partial** |
| Transport vehicle registration | 20/hr (in-memory) | **Partial** |
| Transport driver status update | 60/min (in-memory) | **Partial** |

**Current behavior:** Per-endpoint limits exist for critical paths, but transport limits use an **in-memory** decorator (not safe for multi-worker deployments).

---

## 6. Risk Engine

| Check | Status | Implementation |
|-------|--------|----------------|
| VPN detection | **Missing** | No proxy/VPN header inspection |
| Tor exit nodes | **Missing** | No Tor IP list check |
| ASN reputation | **Missing** | No ASN / IP reputation scoring |
| Bot detection | **Missing** | No user-agent or behavioral bot scoring |
| Geo-location | **Missing** | No GeoIP lookups |
| Failed login count | **Partial** | Rate-limited by endpoint, but not cross-referenced with a risk score |

**Current behavior:** Risk engine exists as a stub (`FraudDetectionConfig.enabled = False`, `score_transaction()` is mostly `pass`). No risk-based tightening of rate limits.

---

## 7. Event Stream (Kafka / Async)

| Feature | Status | Detail |
|---------|--------|--------|
| Kafka / message broker | **Missing** | No `RateLimitExceeded` events published |
| Security service consumer | **Missing** | No async alerting on breaches |
| Analytics | **Missing** | No breach counters or histograms |
| Fraud detection integration | **Missing** | Fraud service is disconnected from rate-limit events |

**Current behavior:** Rate-limit breaches return HTTP 429 synchronously. There is no async event pipeline for security analytics.

---

## 8. Temporary Blocking

| Mechanism | Status | Detail |
|-----------|--------|--------|
| Progressive delays | **Missing** | No exponential backoff on repeated 429s |
| CAPTCHA trigger | **Missing** | No CAPTCHA integration |
| Temporary IP ban | **Missing** | No IP blocklist or ban escalation |
| API key suspension | **Missing** | No key-level suspension logic |
| Account lock (sensitive endpoints) | **Partial** | Login attempts are rate-limited, but no lockout escalation |

**Current behavior:** Flask-Limiter returns 429. There is no progressive punishment, CAPTCHA, or ban list.

---

## 9. Monitoring

| Metric / Tool | Status | Detail |
|---------------|--------|--------|
| Top blocked IPs | **Missing** | No dashboard or query |
| Attack countries | **Missing** | No GeoIP + rate-limit join |
| Endpoint abuse | **Missing** | No per-endpoint breach histograms |
| Redis latency | **Partial** | Generic Redis health check exists; no rate-limit-specific latency |
| False positives | **Missing** | No tracking or tuning workflow |
| Requests/sec | **Partial** | Generic request logging exists; no rate-limit-specific RPS |
| Prometheus / Grafana | **Missing** | `prometheus_client` is in `requirements.txt` but unused for rate limits |
| OpenTelemetry | **Missing** | No rate-limit spans or traces |

**Current behavior:** Basic request logging exists. No dedicated rate-limit observability.

---

## Code Locations

| File | Relevance |
|------|-----------|
| `app/config.py` | Flask-Limiter config defaults |
| `app/extensions.py` | `Limiter` instance |
| `app/__init__.py` | Runtime wiring |
| `app/utils/rate_limiting.py` | Custom in-memory + Redis event limiter |
| `app/utils/monitoring.py` | Generic metric logging (unused for rate limits) |
| `app/auth/routes.py` | Per-route `@limiter.limit` usage |
| `app/auth/decorators.py` | Placeholder `rate_limit` decorator |
| `app/auth/config_model.py` | DB-backed verification rate limits |
| `app/events/routes.py` | Custom Redis `rate_limit()` function |
| `app/accommodation/routes.py` | Multiple `@limiter.limit` decorators |
| `app/accommodation/services/abuse_prevention_service.py` | DB-backed booking rate limits |
| `app/media/routes.py` | Multiple `@limiter.limit` decorators |
| `app/wallet/routes_pin.py` | `@limiter.limit` on PIN endpoints |
| `app/wallet/api/wallet_api.py` | `@limiter.limit` with `current_user.id` key |
| `app/wallet/services/nonce_protection_service.py` | Hourly nonce rate checks |
| `app/wallet/models/fraud_detection.py` | Fraud detection config (dormant) |
| `app/wallet/services/fraud_detection_service.py` | Fraud scoring (stub) |
| `app/transport/decorator.py` | Placeholder transport rate limit decorator |
| `app/transport/services/settings_service.py` | Custom `@rate_limit` on methods |
| `app/transport/services/provider_service.py` | Custom `@rate_limit` on methods |
| `app/admin/owner/security_service.py` | `RATE_LIMIT_ENABLED` status read |
| `app/admin/owner/security_routes.py` | `RATE_LIMIT_ENABLED` setting exposure |
| `app/audit/comprehensive_audit.py` | `APICallStatus.RATE_LIMITED` enum |
| `docker/nginx/afcon360.conf` | Nginx proxy (no rate limiting) |

---

## Gaps Summary

| # | Gap | Severity |
|---|-----|----------|
| 1 | No edge-layer (Nginx/WAF) rate limiting | High |
| 2 | Only fixed-window strategy; no sliding window / token bucket | High |
| 3 | In-memory decorator in transport module breaks multi-worker | Medium |
| 4 | No multi-identity key aggregation (user + IP + device + org) | Medium |
| 5 | Risk engine is dormant (`enabled=False`, stubbed methods) | Medium |
| 6 | No progressive blocking, CAPTCHA, or ban escalation | Medium |
| 7 | No async event stream (Kafka / Celery) for breaches | Low |
| 8 | No Prometheus / Grafana dashboards for rate-limit metrics | Low |
| 9 | `RATE_LIMIT_ENABLED` toggle is not wired to Flask-Limiter init | Low |

---

## Tech Stack Alignment

| Article Recommendation | AFCON360 Status |
|------------------------|-----------------|
| API Gateway | ❌ Nginx is a reverse proxy only |
| Redis Cluster | ⚠️ Single Redis instance, single DB |
| Lua Scripts | ❌ Not used |
| Kafka | ❌ Not used |
| WAF | ❌ Not configured |
| Prometheus / Grafana | ❌ Client present, unused for rate limits |
| OpenTelemetry | ❌ Not instrumented |

---

## Recommendations

1. **Strategy upgrade:** Change `RATELIMIT_STRATEGY` from `fixed-window` to `sliding-window`.
2. **Transport decorator fix:** Replace in-memory `_rate_limit_store` with Redis-backed logic.
3. **Edge limiting:** Add `limit_req_zone` and `limit_req` to `docker/nginx/afcon360.conf`.
4. **Key diversity:** Use composite keys (`user_id:ip`) instead of IP-only where possible.
5. **Risk engine:** Un-stub `FraudDetectionService` and connect it to route-level enforcement.
6. **Monitoring:** Instrument Flask-Limiter hits/misses with `prometheus_client` or structured logging.
7. **Blocking:** Implement IP blocklist and progressive backoff for repeated 429s.
