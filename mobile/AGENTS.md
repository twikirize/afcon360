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

13. Keep one shared mobile source system: place behavior common to User and Driver in `mobile/packages/`; only app identity, navigation differences and genuine platform-specific behavior belong under each app. Do not fork shared business logic for Android versus iOS.
14. Maintain explicit platform minimums and test the oldest supported Android API, representative Android releases, the current Android target, and current iOS simulator. A build-only green check is not installation or runtime evidence.
