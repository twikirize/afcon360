import fs from "node:fs";
import path from "node:path";

const read = file => fs.readFileSync(path.join(process.cwd(), file), "utf8");
const checks = [
  ["SDK 58 SQLite package is declared", read("apps/user/package.json").includes('"expo-sqlite": "~58.0.17"')],
  ["SDK 58 cryptographic random package is declared", read("apps/user/package.json").includes('"expo-crypto": "~58.0.8"')],
  ["SQLCipher native build plugin is enabled", /useSQLCipher:\s*true/.test(read("apps/user/app.config.ts"))],
  ["Native app version is incremented for this binary change", /version:\s*"1\.0\.2"/.test(read("apps/user/app.config.ts"))],
  ["Runtime SQLCipher support is verified", /PRAGMA cipher_version/.test(read("apps/user/src/offline/storage.ts"))],
  ["Database key is generated with secure random bytes", /getRandomBytesAsync\(32\)/.test(read("apps/user/src/offline/storage.ts"))],
  ["Database key is stored in platform secure storage", /SecureStore\.setItemAsync/.test(read("apps/user/src/offline/storage.ts"))],
  ["SQLCipher key is applied before schema access", /PRAGMA key/.test(read("apps/user/src/offline/storage.ts"))],
  ["Cache scope includes the API environment and account", /getOfflineAccountScope/.test(read("apps/user/src/offline/storage.ts")) && /new URL\(environmentOrigin\)\.origin/.test(read("apps/user/src/offline/storage.ts"))],
  ["Offline identity and server-only verification are wired", /readOfflineIdentity/.test(read("apps/user/src/auth/AuthProvider.tsx")) && /getMe/.test(read("packages/core/src/auth/mobile-auth-client.ts"))],
  ["Offline mutation guard is enforced in the shared API client", /offlineReadOnly/.test(read("packages/core/src/auth/mobile-auth-client.ts")) && /offline_read_only/.test(read("packages/core/src/auth/mobile-auth-client.ts"))],
  ["Home feed cache is accessed through a repository", /readHomeFeed/.test(read("apps/user/src/offline/repositories.ts")) && /refreshHomeFeed/.test(read("apps/user/src/offline/repositories.ts"))],
  ["My Events cache excludes ticket QR payloads", /qr_code:\s*""/.test(read("apps/user/src/offline/repositories.ts"))],
  ["Selected Pamoja Home composition remains intact", /GeminiHomeTop/.test(read("apps/user/app/(tabs)/index.tsx")) && /MyEventsOverview/.test(read("apps/user/app/(tabs)/index.tsx"))],
  ["Expo Updates native module remains installed", read("apps/user/package.json").includes('"expo-updates"')],
  ["Expo Updates native config plugin remains enabled", /"expo-updates"/.test(read("apps/user/app.config.ts"))],
  ["Only the disposable E2E binary disables OTA", /updates: isE2EBuild\s*\?\s*\{\s*enabled: false\s*\}/.test(read("apps/user/app.config.ts")) && /checkAutomatically: "ON_LOAD"/.test(read("apps/user/app.config.ts"))],
  ["Preview APK uses the OTA preview channel and APK distribution", /"apk-share"[\s\S]*?"channel": "preview"[\s\S]*?"buildType": "apk"/.test(read("apps/user/eas.json"))],
  ["Manual OTA update flow still checks, downloads and reloads updates", /Updates\.checkForUpdateAsync/.test(read("apps/user/app/(service)/settings.tsx")) && /Updates\.fetchUpdateAsync/.test(read("apps/user/app/(service)/settings.tsx")) && /Updates\.reloadAsync/.test(read("apps/user/app/(service)/settings.tsx"))],
  ["Android uninstall uses an explicit in-app confirmation", /Uninstall AFCON360\?/.test(read("apps/user/app/(service)/settings.tsx")) && /Linking\.openSettings/.test(read("apps/user/app/(service)/settings.tsx"))],
  ["React Native Foojay resolver can use Gradle Plugin Portal", /gradlePluginPortal\(\)/.test(read("apps/user/plugins/withReactNativeGradlePluginPortal.js"))],
  ["Account-to-settings journey taps the real Version & updates action, not the App settings section heading", /tap_text_scrolling\("Version & updates"\)/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Android journey scrolls Home to assert My Events instead of expecting the entire page in one viewport", /wait_for_text_scrolling/.test(read("scripts/verify-user-authenticated-journey.py")) && !/wait_for_text\("Your world,",\s*"My Events"/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Active offline foundation branch is included in CI", /feat\/user-offline-first-foundation-20261117/.test(read("../.github/workflows/mobile-workspace.yml"))],
];

let failed = false;
for (const [label, passed] of checks) {
  process.stdout.write((passed ? "PASS " : "FAIL ") + label + "\n");
  failed ||= !passed;
}
if (failed) process.exit(1);
