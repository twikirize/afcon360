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
  ["Native runtime fingerprint automatically gates OTA compatibility", /runtimeVersion:\s*\{\s*policy:\s*"fingerprint"\s*\}/.test(read("apps/user/app.config.ts"))],
  ["Internal preview builds alone opt into Android cleartext for private laptop testing", /withPreviewCleartextTraffic/.test(read("apps/user/app.config.ts")) && /enabled:\s*isPreview/.test(read("apps/user/app.config.ts")) && /options\.enabled !== true/.test(read("apps/user/plugins/withPreviewCleartextTraffic.js")) && /android:usesCleartextTraffic/.test(read("apps/user/plugins/withPreviewCleartextTraffic.js"))],
  ["E2E OTA channel is isolated from user-facing preview", /isE2EBuild\s*\?\s*"afcon360-user-e2e"/.test(read("apps/user/app.config.ts")) && /updates: easProjectId\s*\?/.test(read("apps/user/app.config.ts"))],
  ["E2E startup waits briefly for the isolated OTA bundle", /fallbackToCacheTimeout: isE2EBuild \? 30_000 : 0/.test(read("apps/user/app.config.ts"))],
  ["Preview APK retains its user-facing preview channel", /"apk-share"[\s\S]*?"channel": "preview"[\s\S]*?"buildType": "apk"/.test(read("apps/user/eas.json"))],
  ["Signed developer APK has its own OTA channel and live API", /"dev-apk"[\s\S]*?"channel": "user-development"[\s\S]*?"EXPO_PUBLIC_API_BASE_URL": "https:\/\/www\.pamoja\.space"/.test(read("apps/user/eas.json"))],
  ["Signed developer APK cache is keyed by native fingerprint and profile", /user-dev-apk-recipe-v1-native-\$FINGERPRINT-profile-\$PROFILE_SHA256/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["OTA-only source changes test on cached APK and publish to developer channel", /outputs\.ota == 'true'[\s\S]*?Publish current User bundle to the isolated development OTA channel/.test(read("../.github/workflows/mobile-workspace.yml"))],
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
