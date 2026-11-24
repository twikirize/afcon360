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
  ["Selected curated Pamoja Home composition and offline integration remain intact", (() => { const home = read("apps/user/app/(tabs)/index.tsx"); return /<Header\s*\/>/.test(home) && /<HeroParallax/.test(home) && /<ServiceGrid/.test(home) && /<TrendingRail/.test(home) && /MyEventsSection/.test(home) && /userOfflineRepository\.refreshHomeFeed/.test(home) && /userOfflineRepository\.refreshEventRegistrations/.test(home); })()],
  ["Expo Updates native module remains installed", read("apps/user/package.json").includes('"expo-updates"')],
  ["Expo Updates native config plugin remains enabled", /"expo-updates"/.test(read("apps/user/app.config.ts"))],
  ["Native runtime fingerprint automatically gates OTA compatibility", /runtimeVersion:\s*\{\s*policy:\s*"fingerprint"\s*\}/.test(read("apps/user/app.config.ts"))],
  ["Internal preview builds alone opt into Android cleartext for private laptop testing", /withPreviewCleartextTraffic/.test(read("apps/user/app.config.ts")) && /enabled:\s*isPreview/.test(read("apps/user/app.config.ts")) && /options\.enabled !== true/.test(read("apps/user/plugins/withPreviewCleartextTraffic.js")) && /android:usesCleartextTraffic/.test(read("apps/user/plugins/withPreviewCleartextTraffic.js"))],
  ["Preview API validation permits USB ADB-reverse loopback only on port 5000", /isUsbLoopback/.test(read("apps/user/src/services/api.ts")) && /parsed\.port === "5000"/.test(read("apps/user/src/services/api.ts"))],
  ["Server settings uses the active Metro runtime API address", /Constants\.expoConfig\?\.extra\?\.apiBaseUrl/.test(read("apps/user/app/server-settings.tsx")) && /Use server for this development session/.test(read("apps/user/app/server-settings.tsx"))],
  ["Connection screen identifies the development client by its existing dedicated app scheme", /afcon360-preview-dev/.test(read("apps/user/app/server-settings.tsx")) && /const appScheme = isDevelopmentClient \? "afcon360-preview-dev"/.test(read("apps/user/app.config.ts"))],
  ["Server settings identifies live Pamoja and explains that live users do not need Metro", /isPamojaServerUrl/.test(read("apps/user/app/server-settings.tsx")) && /PUBLIC PAMOJA — LIVE SERVER/.test(read("apps/user/app/server-settings.tsx")) && /ordinary live users do not need Metro/i.test(read("apps/user/app/server-settings.tsx"))],
  ["Metro controls are restricted to the dedicated development-client build", /isDevelopmentClient && \(/.test(read("apps/user/app/server-settings.tsx")) && /Metro — developer-only Fast Refresh/.test(read("apps/user/app/server-settings.tsx"))],
  ["Server settings checks database readiness and no longer calls missing URL discovery endpoint", /\/api\/health\/ready/.test(read("apps/user/app/server-settings.tsx")) && !/server-urls/.test(read("apps/user/app/server-settings.tsx"))],
  ["Windows development startup supports Auto, LAN and USB and has no machine-specific path", /ValidateSet\("Auto", "Lan", "Usb"\)/.test(read("scripts/windows/start-user-dev.ps1")) && !/C:\\\\Users\\\\/.test(read("scripts/windows/start-user-dev.ps1"))],
  ["Windows helper supports Auto, Local and Pamoja targets", /ValidateSet\("Auto", "Local", "Pamoja"\)/.test(read("scripts/windows/start-user-dev.ps1"))],
  ["Auto mode detects the public Pamoja API target", /AFCON360_API_BASE_URL/.test(read("scripts/windows/start-user-dev.ps1")) && /www\.pamoja\.space/.test(read("scripts/windows/start-user-dev.ps1"))],
  ["Pamoja mode health-checks the live API and exits before Metro startup", (() => { const s = read("scripts/windows/start-user-dev.ps1"); const live = s.indexOf('if ($TargetEnvironment -eq "Pamoja") {'); const metro = s.indexOf('Start-Process -FilePath "powershell.exe"', live); return live >= 0 && metro > live && /Test-ApiReady -Url \$liveApiBaseUrl/.test(s.slice(live, metro)) && /Metro\s+: not started/.test(s.slice(live, metro)) && /return/.test(s.slice(live, metro)); })()],
  ["Auto connection mode checks that the development APK is installed before choosing USB", /pm path \$PackageId/.test(read("scripts/windows/start-user-dev.ps1")) && /Auto will use Wi-Fi\/hotspot and the Metro QR flow/.test(read("scripts/windows/start-user-dev.ps1"))],
  ["LAN development preserves the Flask-advertised IP selection instead of guessing an adapter", /Flask startup and active network adapters/.test(read("scripts/windows/start-user-dev.ps1")) && /Read-Host \("Enter the number/.test(read("scripts/windows/start-user-dev.ps1")) && /Select the address that matches/.test(read("scripts/windows/start-user-dev.ps1")) && !/Find-LanAddress/.test(read("scripts/windows/start-user-dev.ps1"))],

  ["LAN startup binds Flask to all interfaces only with debugger disabled", /\$env:FLASK_HOST = \$BindAddress/.test(read("scripts/windows/start-user-dev.ps1")) && /\$env:FLASK_DEBUG = "false"/.test(read("scripts/windows/start-user-dev.ps1")) && /\$BindAddress = "0\.0\.0\.0"/.test(read("scripts/windows/start-user-dev.ps1"))],
  ["USB startup creates reverse tunnels for both Metro and local API", /reverse "tcp:\$Port" "tcp:\$Port"/.test(read("scripts/windows/launch-user-dev-client.ps1")) && /reverse "tcp:\$ApiPort" "tcp:\$ApiPort"/.test(read("scripts/windows/launch-user-dev-client.ps1"))],
  ["Dev-client launcher targets the current package and deep-link scheme", /space\.pamoja\.afcon360\.user\.preview\.dev/.test(read("scripts/windows/launch-user-dev-client.ps1")) && /afcon360-preview-dev/.test(read("scripts/windows/launch-user-dev-client.ps1"))],
  ["Unknown API listeners are not silently reused or terminated", /unmanaged or differently-bound process/.test(read("scripts/windows/start-user-dev.ps1")) && /does not kill an unknown process/.test(read("scripts/windows/README.md"))],
  ["Generated native projects are excluded from Git and EAS archives", /\/mobile\/apps\/user\/android\//.test(read("../.gitignore")) && /\/mobile\/apps\/user\/android\//.test(read("../.easignore"))],
  ["Signed APK metadata parser is self-tested before builds and checks package/version/SDK identity", read("scripts/verify-user-dev-apk-metadata.mjs").includes("targetSdk must be at least 36") && read("../.github/workflows/mobile-workspace.yml").includes("verify-user-dev-apk-metadata.mjs --self-test") && read("../.github/workflows/mobile-workspace.yml").includes("verify-user-dev-apk-metadata.mjs \"$RUNNER_TEMP/afcon360-user-dev-badging.txt\" \"$EXPECTED_VERSION_NAME\"")],
  ["Explicit Metro APK verification-recipe changes request one gated candidate requalification", /^\s*AFCON360_USER_DEV_APK_RECIPE_VERSION: "v\d+"$/m.test(read("../.github/workflows/mobile-workspace.yml")) && read("../.github/workflows/mobile-workspace.yml").includes("outputs.dev_apk_recipe == \'true\'") && read("../.github/workflows/mobile-workspace.yml").includes("dev_apk_recipe = any(")],
  ["E2E APK cache uses the v6 native-fingerprint key without legacy restore keys", /AFCON360_USER_E2E_APK_RECIPE_VERSION: "v6"/.test(read("../.github/workflows/mobile-workspace.yml")) && /Restore native-fingerprint-keyed User E2E APK[\s\S]*?key: \$\{\{ steps\.user-apk-key\.outputs\.key \}\}[\s\S]*?- name: Validate cached User APK/.test(read("../.github/workflows/mobile-workspace.yml")) && !/Restore native-fingerprint-keyed User E2E APK[\s\S]*?restore-keys:/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Authenticated-journey APK is reused across OTA-only commits when the native fingerprint matches", /afcon360-user-e2e-apk-recipe-\$\{AFCON360_USER_E2E_APK_RECIPE_VERSION\}-native-\$FINGERPRINT/.test(read("../.github/workflows/mobile-workspace.yml")) && !/source-\$GITHUB_SHA/.test(read("../.github/workflows/mobile-workspace.yml")) && !/EXPECTED_SOURCE_COMMIT/.test(read("../.github/workflows/mobile-workspace.yml"))],

  ["CI parses PowerShell development helpers before APK-related validation", /Parse Windows User App development helpers/.test(read("../.github/workflows/mobile-workspace.yml")) && /Parser\]::ParseFile/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Reconciliation branch runs pre-build checks before the Metro APK", (() => {
    const workflow = read("../.github/workflows/mobile-workspace.yml");
    const prebuildStart = workflow.indexOf("  user-prebuild-tests:");
    const prebuildEnd = workflow.indexOf("  user-authenticated-journey:", prebuildStart);
    const metroStart = workflow.indexOf("  build-user-dev-apk:");
    const throwawayStart = workflow.indexOf("  user-authenticated-journey:");
    const previewStart = workflow.indexOf("  publish-preview-ota:");
    const previewEnd = workflow.indexOf("  user-prebuild-tests:", previewStart);
    const previewJob = previewStart >= 0 && previewEnd > previewStart ? workflow.slice(previewStart, previewEnd) : "";
    const throwawayEnd = workflow.indexOf("  user-android-version-compatibility:", throwawayStart);
    const prebuildJob = prebuildStart >= 0 && prebuildEnd > prebuildStart
      ? workflow.slice(prebuildStart, prebuildEnd) : "";
    const metroJob = metroStart >= 0 ? workflow.slice(metroStart) : "";
    const throwawayJob = throwawayStart >= 0 && throwawayEnd > throwawayStart
      ? workflow.slice(throwawayStart, throwawayEnd) : "";
    return workflow.includes("- reconcile/user-local-files-20261121") &&
      workflow.includes('docs/engineering/AFCON360_MOBILE_UPDATE_REBUILD_CONSTITUTION.md') &&
      prebuildJob.includes("needs: [classify-user-changes, mobile-typecheck]") &&
      prebuildJob.includes("mobile-user-e2e-backend.py prebuild") &&
      !/sdkmanager|gradlew|assembleRelease|android-emulator-runner|expo prebuild/i.test(prebuildJob) &&
      metroJob.includes("needs: [classify-user-changes, mobile-typecheck, user-prebuild-tests]") &&
      metroJob.includes("needs.user-prebuild-tests.result == 'success'") &&
      metroJob.includes("outputs.e2e_harness == 'true'") &&
      metroJob.includes("steps.validate-dev-apk.outputs.reusable != 'true'") &&
      metroJob.includes("Exact signed developer APK cache hit; SHA-256 verified") &&
      previewJob.includes("needs: [classify-user-changes, mobile-typecheck, user-prebuild-tests]") &&
      previewJob.includes("needs.user-prebuild-tests.result == 'success'") &&
      throwawayJob.includes("needs: [classify-user-changes, mobile-typecheck, user-prebuild-tests]") &&
      throwawayJob.includes("needs.user-prebuild-tests.result == 'success'") &&
      !throwawayJob.includes("github.ref_name != 'reconcile/user-local-files-20261121'");
  })()],
  ["Hybrid Android config plugins execute in CI before any APK build", (() => {
    const workflow = read("../.github/workflows/mobile-workspace.yml");
    const typecheckStart = workflow.indexOf("  mobile-typecheck:");
    const typecheckEnd = workflow.indexOf("  publish-preview-ota:", typecheckStart);
    const typecheckJob = typecheckStart >= 0 && typecheckEnd > typecheckStart
      ? workflow.slice(typecheckStart, typecheckEnd) : "";
    return typecheckJob.includes("Execute hybrid Android config plugins before any EAS APK build") &&
      typecheckJob.includes("expo prebuild --platform android --no-install --clean") &&
      typecheckJob.includes("PREBUILD_LOG") &&
      typecheckJob.includes("AFCON360 automatic fallback enabled: Metro -> EAS Update -> embedded app") &&
      typecheckJob.includes("debuggableVariants = []") &&
      typecheckJob.indexOf("Bundle User app for Android and iOS") <
        typecheckJob.indexOf("Execute hybrid Android config plugins before any EAS APK build");
  })()],
  ["Hybrid config plugin resolves the matching nested Expo Dev Launcher from pnpm", (() => {
    const plugin = read("apps/user/plugins/withDevClientEmbeddedBundle.js");
    return plugin.includes("findPackageRootFromEntry") &&
      plugin.includes("findInstalledPackageRoot") &&
      plugin.includes('entry.startsWith(packageName + "@")') &&
      plugin.includes('devClientPackage.dependencies?.["expo-dev-launcher"]') &&
      plugin.includes("package root for ");
  })()],
  ["Metro Fast Refresh qualification uses a temporary root route and restores the original source byte-for-byte", (() => {
    const script = read("scripts/verify-user-dev-client-delivery.py");
    const unit = read("scripts/test-user-dev-client-delivery.py");
    return script.includes('ROUTE = Path("apps/user/app/index.tsx")') &&
      script.includes("ROUTE_BACKUP = ROUTE.read_bytes()") &&
      script.includes("def restore_qa_route()") &&
      script.includes("restore_qa_route()") &&
      unit.includes("restored byte-for-byte") &&
      unit.includes("TEMPORARY_ROOT_ROUTE") &&
      read("../.github/workflows/mobile-workspace.yml").includes("python scripts/test-user-dev-client-delivery.py");
  })()],
  ["SDK 58 automated Dev Client launch suppresses onboarding, floating tool and automatic dev menu", (() => {
    const script = read("scripts/verify-user-dev-client-delivery.py");
    return script.includes("__expo_disable_onboarding=1") &&
      script.includes("__expo_disable_fab=1") &&
      script.includes("__expo_disable_auto_launch=1");
  })()],
  ["Offline development-client qualification records whether EAS content or embedded fallback launched", (() => {
    const script = read("scripts/verify-user-dev-client-delivery.py");
    return script.includes("offline_cached_marker or offline_embedded_fallback") &&
      script.includes("persistent_eas_cache_qualification") &&
      script.includes("not_proven_by_development_client");
  })()],
  ["Metro qualification removes GitHub CI mode so Metro WebSocket reloads and Fast Refresh remain enabled", (() => { const script = read("scripts/verify-user-dev-client-delivery.py"); const start = script.indexOf("def start_metro"); const end = script.indexOf("def open_dev_url", start); const block = script.slice(start, end); return block.includes("env.pop(\"CI\", None)") && !block.includes('"CI": "1"'); })()],
  ["EAS fallback qualification follows the development APK configured channel URL", read("scripts/verify-user-dev-client-delivery.py").includes('update_url = f"https://u.expo.dev/{project_id}?channel-name=user-development-client"') && read("apps/user/app.config.ts").includes('"https://u.expo.dev/" + easProjectId + "?channel-name=" + updateChannel')],
  ["Temporary EAS qualification channel routing is restored after emulator tests, including failures", (() => { const workflow = read("../.github/workflows/mobile-workspace.yml"); return workflow.includes('channel:edit "$CHANNEL" --branch "$QA_BRANCH" --non-interactive') && workflow.includes("Restore User development channel after Android qualification") && workflow.includes("if: always()") && workflow.includes("channel:edit user-development-client --branch user-development-client --non-interactive"); })()],
  ["Mobile update/rebuild constitution is versioned and included in workflow path filters", read("../docs/engineering/AFCON360_MOBILE_UPDATE_REBUILD_CONSTITUTION.md").includes("PRE-BUILD TEST GATE") && read("../.github/workflows/mobile-workspace.yml").includes('docs/engineering/AFCON360_MOBILE_UPDATE_REBUILD_CONSTITUTION.md')],
  ["Test-harness-only changes reuse an exact compatible APK and build one baseline only when cache is absent", (() => {
    const workflow = read("../.github/workflows/mobile-workspace.yml");
    return workflow.includes("build-user-dev-apk:") &&
      workflow.includes("outputs.e2e_harness == 'true'") &&
      workflow.includes("if: steps.validate-dev-apk.outputs.reusable != 'true'") &&
      workflow.includes("eas-cli@latest build") &&
      workflow.includes('grep -Fxq "apk_sha256=$ACTUAL_SHA" "$INFO"');
  })()],
  ["Disposable authenticated-journey APK is gated behind strict TypeScript and Android/iOS bundle exports", /user-authenticated-journey:[\s\S]*?needs: \[classify-user-changes, mobile-typecheck, user-prebuild-tests\]/.test(read("../.github/workflows/mobile-workspace.yml")) && /name: Bundle User app for Android and iOS/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Compatible preview updates are also published to the release-like user-development channel", /Publish compatible bundle to release-like User preview OTA channel/.test(read("../.github/workflows/mobile-workspace.yml")) && /AFCON360_UPDATE_CHANNEL: "user-development"/.test(read("../.github/workflows/mobile-workspace.yml"))],

  ["E2E OTA channel is isolated from user-facing preview", /isE2EBuild\s*\?\s*"afcon360-user-e2e"/.test(read("apps/user/app.config.ts")) && /updates: easProjectId\s*\?/.test(read("apps/user/app.config.ts"))],
  ["E2E startup waits briefly for the isolated OTA bundle", /fallbackToCacheTimeout: isE2EBuild \? 30_000 : 0/.test(read("apps/user/app.config.ts"))],
  ["Preview APK retains its user-facing preview channel", /"apk-share"[\s\S]*?"channel": "preview"[\s\S]*?"buildType": "apk"/.test(read("apps/user/eas.json"))],
  ["Metro development APK uses its dedicated development-client profile and identity", /"development"[\s\S]*?"developmentClient": true[\s\S]*?"channel": "user-development-client"/.test(read("apps/user/eas.json")) && /package: c\.android\?\.package === "space\.pamoja\.afcon360\.user\.preview\.dev"/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Metro development APK uses frozen remote credentials and EAS auto-increment", /"development"[\s\S]*?"autoIncrement": true[\s\S]*?"credentialsSource": "remote"/.test(read("apps/user/eas.json"))],
  ["Metro development APK package is isolated by the tested metadata validator", /package: c\.android\?\.package === "space\.pamoja\.afcon360\.user\.preview\.dev"/.test(read("../.github/workflows/mobile-workspace.yml")) && /verify-user-dev-apk-metadata\.mjs/.test(read("../.github/workflows/mobile-workspace.yml")) && /space\.pamoja\.afcon360\.user\.preview\.dev/.test(read("scripts/verify-user-dev-apk-metadata.mjs"))],
  ["APK post-build metadata validation uses the repository-root-relative mobile/scripts path", read("../.github/workflows/mobile-workspace.yml").includes('node mobile/scripts/verify-user-dev-apk-metadata.mjs "$RUNNER_TEMP/afcon360-user-dev-badging.txt" "$EXPECTED_VERSION_NAME"')],
  ["Android emulator action switches to mobile before running its qualification script", read("../.github/workflows/mobile-workspace.yml").includes("script: cd mobile && python scripts/verify-user-dev-client-delivery.py user-dev-apk-artifact/afcon360-user-metro-development.apk")],
  ["Metro development APK is signature-verified without depending on the old preview app certificate", /apksigner verify --verbose --print-certs/.test(read("../.github/workflows/mobile-workspace.yml")) && /signing_certificate_sha256=\$CERT_SHA256/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Metro development APK cache is keyed by recipe, native fingerprint, EAS profile and app version", /afcon360-user-dev-apk-\$\{AFCON360_USER_DEV_APK_RECIPE_VERSION\}-native-\$FINGERPRINT-profile-\$PROFILE_SHA256-version-\$VERSION_SHA256/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Compatible User changes publish to the isolated Metro development-client OTA branch", /outputs\.ota == 'true'[\s\S]*?Publish current User bundle to the isolated Metro development-client OTA channel[\s\S]*?CHANNEL="user-development-client"[\s\S]*?eas-cli@latest update/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Manual OTA update flow still checks, downloads and reloads updates", /Updates\.checkForUpdateAsync/.test(read("apps/user/app/(service)/settings.tsx")) && /Updates\.fetchUpdateAsync/.test(read("apps/user/app/(service)/settings.tsx")) && /Updates\.reloadAsync/.test(read("apps/user/app/(service)/settings.tsx"))],
  ["Android uninstall uses an explicit in-app confirmation", /Uninstall AFCON360\?/.test(read("apps/user/app/(service)/settings.tsx")) && /Linking\.openSettings/.test(read("apps/user/app/(service)/settings.tsx"))],
  ["React Native Foojay resolver can use Gradle Plugin Portal", /gradlePluginPortal\(\)/.test(read("apps/user/plugins/withReactNativeGradlePluginPortal.js"))],
  ["Account-to-settings journey taps the real Version & updates action, not the App settings section heading", /tap_text_scrolling\("Version & updates"\)/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Account return restores the scroll position before asserting the heading", /def wait_for_text_scrolling_to_top/.test(read("scripts/verify-user-authenticated-journey.py")) && /wait_for_text_scrolling_to_top\(\s*"Your account\."/s.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Login route has one authenticated-state redirect, not duplicate submit-handler navigation", read("apps/user/app/login.tsx").includes('if (!loading && user) router.replace("/(tabs)");') && !read("apps/user/app/login.tsx").includes('onPress={() => signIn(identifier, password).then') && !read("apps/user/app/login.tsx").includes('onPress={() => verifyMfa(code).then')],
  ["ServiceEntry receives serviceKey because React reserves the key attribute", /serviceKey: ServiceKey/.test(read("apps/user/src/components/ServiceEntry.tsx")) && /function ServiceEntry\(\{\s*serviceKey,/.test(read("apps/user/src/components/ServiceEntry.tsx")) && !/function ServiceEntry\(\{\s*key,/.test(read("apps/user/src/components/ServiceEntry.tsx"))],
  ["Every Pamoja Home service card supplies its explicit serviceKey", (read("apps/user/src/components/GeminiHomeTop.tsx").match(/<ServiceEntry\b[^>]*serviceKey=/g) || []).length === 6 && !/<ServiceEntry\b(?![^>]*serviceKey=)[^>]*>/.test(read("apps/user/src/components/GeminiHomeTop.tsx"))],
  ["Focused login-and-navigation mode verifies Home, Activity, Wallet, Account and returns Home", /AFCON360_E2E_LOGIN_NAVIGATION_ONLY/.test(read("scripts/verify-user-authenticated-journey.py")) && /USER_ANDROID_E2E_LOGIN_NAVIGATION_PASS/.test(read("scripts/verify-user-authenticated-journey.py")) && /tap_text\("Activity", last=True\)/.test(read("scripts/verify-user-authenticated-journey.py")) && /tap_text\("Wallet", last=True\)/.test(read("scripts/verify-user-authenticated-journey.py")) && /tap_text\("Account", last=True\)/.test(read("scripts/verify-user-authenticated-journey.py")) && /tap_text\("Home", last=True\)/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Focused login-and-navigation gate blocks the complete authenticated journey", /name: Focused login and primary navigation gate[\s\S]*?id: login_navigation_journey[\s\S]*?AFCON360_E2E_LOGIN_NAVIGATION_ONLY=1/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Android-version matrix runs only after the primary journey succeeds", /needs\.user-authenticated-journey\.result == 'success'[\s\S]*?needs\.user-authenticated-journey\.outputs\.apk_rebuilt == 'true'/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Failure diagnostics capture the app process log independently", /failure-app-logcat\.txt/.test(read("scripts/verify-user-authenticated-journey.py")) && /failure-activity-top\.txt/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["CI runs focused login and primary navigation before the full authenticated journey", /name: Focused login and primary navigation gate[\s\S]*?id: login_navigation_journey[\s\S]*?AFCON360_E2E_LOGIN_NAVIGATION_ONLY=1/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Full authenticated journey is gated on successful login-and-navigation proof", /name: Install, authenticate, test services, restore session and sign out\s+if: \$\{\{ steps\.login_navigation_journey\.outcome == 'success' \}\}/.test(read("../.github/workflows/mobile-workspace.yml"))],
  ["Android journey scrolls Home to assert My Events instead of expecting the entire page in one viewport", /wait_for_text_scrolling/.test(read("scripts/verify-user-authenticated-journey.py")) && !/wait_for_text\("Your world,",\s*"My Events"/.test(read("scripts/verify-user-authenticated-journey.py"))],
  ["Active offline foundation branch is included in CI", /feat\/user-offline-first-foundation-20261117/.test(read("../.github/workflows/mobile-workspace.yml"))],
];

let failed = false;
for (const [label, passed] of checks) {
  process.stdout.write((passed ? "PASS " : "FAIL ") + label + "\n");
  failed ||= !passed;
}
if (failed) process.exit(1);
