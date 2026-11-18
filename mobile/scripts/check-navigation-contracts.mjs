import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

// Every external website handoff must be reviewed and visibly labelled.
const approved = [
  ["apps/user/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', 'title="Privacy notice"'],
  ["apps/user/app/(tabs)/account.tsx", "WebBrowser.openBrowserAsync(target.toString())", "Opens on Pamoja website"],
  ["apps/user/app/(tabs)/explore.tsx", 'WebBrowser.openBrowserAsync(SITE + "/tourism")', 'label="Explore tourism on website"'],
  ["apps/user/app/(tabs)/explore.tsx", 'WebBrowser.openBrowserAsync(SITE + "/tournament")', 'label="Explore matches on website"'],
  ["apps/user/app/(tabs)/explore.tsx", 'WebBrowser.openBrowserAsync(SITE + "/onboarding/choose")', 'label="Become a partner on website"'],
  ["apps/user/app/(tabs)/index.tsx", "WebBrowser.openBrowserAsync(target)", "safeSameOriginUrl(path, SITE)"],
  ["apps/driver/app/login.tsx", 'WebBrowser.openBrowserAsync(SITE + "/transport/become-driver")', 'label="Continue driver registration on website"'],
  ["apps/user/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", 'label="Back to AFCON360 website home"'],
  ["apps/driver/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", 'label="Back to AFCON360 website home"'],
  ["apps/driver/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', 'label="Privacy notice (website)"'],
  ["apps/user/app/(tabs)/wallet.tsx", "Linking.openURL(checkout.toString())", 'label={busy ? "Starting secure checkout…" : "Continue to Flutterwave"}'],
  ["apps/user/app/(tabs)/wallet.tsx", "Linking.openURL(checkout.toString())", 'label="Open Flutterwave checkout"'],
  ["apps/user/app/(service)/settings.tsx", "Linking.openURL(officialDownloadsUrl)", 'nativeUpdateActionLabel = "Open official downloads"'],
  ["apps/user/app/(service)/settings.tsx", "WebBrowser.openBrowserAsync(officialDownloadsUrl)", 'nativeUpdateActionLabel = "Open official downloads"'],
];

const nativeInternalRoutes = [
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/events" as never)'],
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/stays" as never)'],
  ["apps/user/app/(tabs)/index.tsx", "router.push('/(service)/ride' as never)"],
  ["apps/user/app/(tabs)/index.tsx", "pathname: '/(service)/events'"],
  ["apps/user/app/(tabs)/index.tsx", "router.push('/(service)/stays' as never)"],
  ["apps/user/app/(tabs)/index.tsx", "router.push('/(tabs)/wallet' as never)"],
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/ride" as never)'],
  ["apps/user/app/(tabs)/activity.tsx", 'pathname: "/(service)/ride-status/[reference]"'],
  ["apps/user/app/(tabs)/account.tsx", 'router.push("/(service)/delete-account" as never)'],
  ["apps/user/app/login.tsx", 'router.push("/server-settings" as never)'],
  ["apps/user/app/server-settings.tsx", "export default function ServerSettingsScreen()"],
  ["apps/user/app/(service)/_layout.tsx", 'if (!user) return <Redirect href="/login" />;'],
  ["apps/user/app/(service)/_layout.tsx", 'return <Stack screenOptions={{ headerShown: false }} />;'],
  ["apps/user/app/(service)/events.tsx", "export default function Events()"],
  ["apps/user/app/(service)/stays.tsx", "export default function Stays()"],
  ["apps/user/app/(service)/ride.tsx", "export default function RideScreen()"],
  ["apps/user/app/(service)/ride-status/[reference].tsx", "export default function RideStatusScreen()"],
  ["apps/user/app/(service)/delete-account.tsx", "export default function DeleteAccountScreen()"],
  ["apps/user/app/(tabs)/account.tsx", 'router.push("/(service)/settings" as never)'],
  ["apps/user/app/(service)/settings.tsx", "export default function UserAppSettings()"],
];

const nativeResetRoutes = [
  ["apps/user/app/login.tsx", 'router.push("/forgot-password")'],
  ["apps/driver/app/login.tsx", 'router.push("/forgot-password")'],
  ["apps/user/app/forgot-password.tsx", "<PasswordResetFlow"],
  ["apps/driver/app/forgot-password.tsx", "<PasswordResetFlow"],
  ["packages/core/src/auth/mobile-auth-client.ts", "/api/mobile/v1/auth/password-reset/request"],
  ["packages/ui/src/auth.tsx", "export function PasswordResetFlow"],
];

const forbiddenUnprotectedRoutes = [
  "apps/user/app/ride.tsx",
  "apps/user/app/ride-status/[reference].tsx",
  "apps/user/app/delete-account.tsx",
];
for (const relative of forbiddenUnprotectedRoutes) {
  if (fs.existsSync(path.join(root, relative))) {
    throw new Error(`Authenticated User route must remain inside the guarded service stack: ${relative}`);
  }
}

// Root-level User routes are public entry points only. New authenticated pages
// must be placed in the guarded service Stack or the guarded tabs group.
const publicRootRouteFiles = new Set([
  "_layout.tsx",
  "index.tsx",
  "login.tsx",
  "register.tsx",
  "forgot-password.tsx",
  // Public preview-only route: users must be able to select the laptop API
  // before login when the installed preview APK initially targets loopback.
  "server-settings.tsx",
]);
const userRootRoutes = path.join(root, "apps/user/app");
for (const entry of fs.readdirSync(userRootRoutes, { withFileTypes: true })) {
  if (entry.isFile() && [".tsx", ".ts", ".jsx", ".js"].some((extension) => entry.name.endsWith(extension)) && !publicRootRouteFiles.has(entry.name)) {
    throw new Error(`Unclassified User root route ${entry.name}; private routes belong in a guarded route group.`);
  }
}

for (const [relative, snippet] of [...nativeInternalRoutes, ...nativeResetRoutes]) {
  const source = fs.readFileSync(path.join(root, relative), "utf8");
  if (!source.includes(snippet)) throw new Error(`Required native route or password-recovery flow is missing or changed: ${relative}`);
}

const requiredWebsiteHandoffLabels = [
  ["apps/user/app/(tabs)/index.tsx", "safeSameOriginUrl(path, SITE)"],
  ["apps/user/src/components/ServiceGrid.tsx", "accessibilityLabel: 'Adventure and tourism on Pamoja website'"],
  ["apps/user/src/components/MyEventsOverview.tsx", 'accessibilityLabel="Host an event on Pamoja website"'],
  ["apps/user/app/(tabs)/account.tsx", "Opens on Pamoja website"],
];
for (const [relative, visibleLabel] of requiredWebsiteHandoffLabels) {
  const source = fs.readFileSync(path.join(root, relative), "utf8");
  if (!source.includes(visibleLabel)) {
    throw new Error(`External website handoff must be visibly labelled: ${relative} — expected ${visibleLabel}`);
  }
}

const userAccountSource = fs.readFileSync(path.join(root, "apps/user/app/(tabs)/account.tsx"), "utf8");
const userSettingsSource = fs.readFileSync(path.join(root, "apps/user/app/(service)/settings.tsx"), "utf8");
if (userAccountSource.includes("AppUpdateControls") || userAccountSource.includes("Check for updates")) {
  throw new Error("App version and update controls belong in User Settings, not the Account page.");
}
if (!userSettingsSource.includes("<SectionTitle>Version & updates</SectionTitle>") || !userSettingsSource.includes("<AppUpdateControls />")) {
  throw new Error("User Settings must contain the Version & updates section and app update controls.");
}

const requiredAccountDestinations = [
  'openWebsite("/profile/me")',
  'openWebsite("/profile/edit")',
  'openWebsite("/account")',
  'openWebsite("/account/settings")',
  'openWebsite("/account/settings#password")',
  'openWebsite("/account/security")',
  'openWebsite("/preferences")',
  'openWebsite("/settings/interests")',
  'openWebsite("/dashboard")',
  'router.push("/(service)/settings" as never)',
];
for (const destination of requiredAccountDestinations) {
  if (!userAccountSource.includes(destination)) {
    throw new Error(`Account hub is missing a required destination: ${destination}`);
  }
}

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(directory, entry.name);
    if (entry.isDirectory()) return walk(full);
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

const expected = new Map();
for (const [relative, snippet, visibleLabel] of approved) {
  const key = path.join(root, relative);
  expected.set(key, (expected.get(key) ?? 0) + 1);
  const source = fs.readFileSync(key, "utf8");
  if (!source.includes(snippet)) throw new Error(`Approved external navigation changed or disappeared: ${relative}\nExpected: ${snippet}`);
  if (!source.includes(visibleLabel)) throw new Error(`External browser handoff must be visibly labelled as a website action: ${relative}\nExpected: ${visibleLabel}`);
}

const violations = [];
let actualTotal = 0;
for (const file of walk(path.join(root, "apps"))) {
  const source = fs.readFileSync(file, "utf8");
  const calls = source.match(/(?:WebBrowser\.openBrowserAsync|Linking\.openURL)\s*\(/g) ?? [];
  actualTotal += calls.length;
  const allowedCount = expected.get(file) ?? 0;
  if (calls.length !== allowedCount) violations.push(`${path.relative(root, file)}: found ${calls.length} browser/URL-opening call(s), approved ${allowedCount}`);
  if (source.includes("/apps/delete-account")) violations.push(`${path.relative(root, file)}: account deletion must stay in the native app`);
}

if (actualTotal !== approved.length) violations.push(`Total browser/URL-opening calls: ${actualTotal}; approved ${approved.length}`);
if (violations.length) {
  console.error("Native navigation contract FAILED:");
  for (const violation of violations) console.error(" - " + violation);
  process.exit(1);
}
console.log(`Native navigation contract passed: ${approved.length} explicitly labelled website handoffs; password recovery and account deletion remain native.`);
