# AFCON360 Native Mobile

Two separate native products share one React Native foundation:

- AFCON360 User — customers, riders and fans.
- AFCON360 Driver — approved drivers and transport operators.

Both use Expo SDK 58, React Native 0.88, React 19.3 and TypeScript 6. Flask remains the system of record. Mobile apps use authenticated APIs and never connect directly to PostgreSQL.

## Delivery stage

This branch establishes native workspaces, phone-first navigation shells, shared UI/API foundations, app identifiers, EAS build profiles and the public website /apps landing page.

This is not a store-ready release. Native authentication is the first backend gate: the current web session/CSRF flow is browser-oriented and must not be copied into native storage or assumed to be a bearer-token API. Live bookings, wallet operations, driver offers, GPS publishing and push notifications remain disabled until server contracts are implemented and tested.

## Requirements

Node.js 22.13+, pnpm 10, Android Studio for local Android builds, macOS/Xcode for local iOS builds, and an Expo account for EAS builds. Set EXPO_PUBLIC_API_BASE_URL to the approved API base URL; never put secrets in EXPO_PUBLIC variables.

## Commands

From this directory run corepack enable, pnpm install, then pnpm user:start or pnpm driver:start. Use pnpm user:typecheck and pnpm driver:typecheck for type checks. iOS local builds require macOS; cloud iOS builds can use EAS.

## App identities

| Product | Android package | iOS bundle ID | Scheme |
|---|---|---|---|
| User | space.pamoja.afcon360.user | space.pamoja.afcon360.user | afcon360 |
| Driver | space.pamoja.afcon360.driver | space.pamoja.afcon360.driver | afcon360-driver |

Confirm legal ownership and store-account availability before public release. EAS projects must be created and linked independently.

The /apps page intentionally shows development status instead of fake store buttons. Add official store URLs only after signed builds pass testing and store approval.

Read docs/backend-contracts.md, docs/release-gates.md and AGENTS.md before adding behavior.
