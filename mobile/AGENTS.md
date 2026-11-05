# Mobile workspace rules

1. Read docs/backend-contracts.md and docs/release-gates.md first.
2. Flask/PostgreSQL remains authoritative. Never connect apps directly to the database.
3. Never invent API routes, fields, fare values, driver states, balances or booking states. Verify backend contracts before wiring screens.
4. Flask browser cookies and /api/csrf-token are not a native authentication protocol.
5. Store credentials only using expo-secure-store. Never log tokens or put them in AsyncStorage, analytics, URLs or crash reports.
6. EXPO_PUBLIC variables are bundled into client builds; never put secrets there.
7. Financial writes and booking/dispatch actions require server authorization, idempotency, validation and auditability.
8. Driver location must be permission-gated, purpose-limited and tested on real devices. Do not silently enable background tracking.
9. Do not claim a feature is live while it is a UI shell. Use honest loading, unavailable, error and empty states.
10. Keep user and driver identifiers, schemes, permissions and EAS projects separate.
11. No production DB changes, migrations, deployments, store submissions or credential changes without a separately approved work item.
12. Keep dense administration/reporting on desktop unless specifically required on mobile.
13. This workspace and its app-only PR contain native client code and mobile build tooling only. Website templates, Flask routes, authentication/token services, account deletion, models, migrations, Docker/server configuration, and backend tests belong on `main` in a separate server PR.
14. When a required API is missing or incorrect, do not add backend code to this branch. Record the contract gap and raise a server-side change against `main`; keep the app work based on that server PR until it merges, then retarget the app PR to `main`.
15. Preserve the public website download contract. Do not change `/download`, `templates/public_download.html`, preview APK destinations, or the User/Driver store-link environment variable names as part of mobile-client work.
