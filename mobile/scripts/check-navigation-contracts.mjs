import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

// Every external website handoff and intentional native deep link must be reviewed and visibly labelled.
const approved = [
  ["apps/user/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', "Privacy notice"],
  ["apps/user/app/(tabs)/account.tsx", "WebBrowser.openBrowserAsync(target.toString())", "Opens on Pamoja website"],
  ["apps/driver/app/login.tsx", 'WebBrowser.openBrowserAsync(SITE + "/transport/become-driver")', "Continue driver registration on website"],
  ["apps/user/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", "Back to AFCON360 website home"],
  ["apps/driver/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", "Back to AFCON360 website home"],
  ["apps/driver/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', "Privacy notice"],
  ["apps/user/src/components/wallet/WalletScreen.tsx", "Linking.openURL(checkout.toString())", "Starting secure checkout…"],
  ["apps/user/src/components/wallet/WalletScreen.tsx", "Linking.openURL(checkout.toString())", "Open Flutterwave checkout"],
  ["apps/user/app/(service)/settings.tsx", "Linking.openURL(officialDownloadsUrl)", "Open official downloads"],
  ["apps/user/app/(service)/settings.tsx", "WebBrowser.openBrowserAsync(officialDownloadsUrl)", "Open official downloads"],
  ["apps/user/app/(tabs)/explore.tsx", 'WebBrowser.openBrowserAsync(SITE + "/tourism")', "Explore tourism on website"],
  ["apps/user/app/server-settings.tsx", "Linking.openURL(deepLink)", "Save & Connect to Metro"],
  ["apps/user/app/connection.tsx", "Linking.openURL(deepLink)", "Save & Connect to Metro"],
];

// Check navigation where it is actually implemented.
// HomeServiceGrid owns the service destinations and their common router handler.
// WalletCard owns wallet navigation.
// Explore owns its native service links.
const nativeInternalRoutes = [
  // Explore screen native routes
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/events" as never)'],
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/stays" as never)'],
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(service)/ride" as never)'],

  // Home service grid destinations
  ["apps/user/src/components/home/HomeServiceGrid.tsx", "destination: '/(service)/ride'"],
  ["apps/user/src/components/home/HomeServiceGrid.tsx", "destination: '/(service)/stays'"],
  ["apps/user/src/components/home/HomeServiceGrid.tsx", "destination: '/(service)/events'"],
  ["apps/user/src/components/home/HomeServiceGrid.tsx", "destination: '/(service)/adventure'"],
  ["apps/user/src/components/home/HomeServiceGrid.tsx", "router.push(service.destination as any)"],

  // Home wallet navigation
  ["apps/user/src/components/home/WalletCard.tsx", "router.push('/(tabs)/wallet' as any)"],

  // Existing protected routes and account flows
  ["apps/user/app/(tabs)/activity.tsx", 'pathname: "/(service)/ride-status/[reference]"'],
  ["apps/user/app/(tabs)/account.tsx", 'router.push("/(service)/delete-account" as never)'],
  ["apps/user/app/login.tsx", 'router.push("/server-settings" as never)'],
  ["apps/user/app/server-settings.tsx", "export default function ServerSettingsScreen()"],
  ["apps/user/app/(service)/_layout.tsx", 'if (!user) return <Redirect href="/login" />;'],
  ["apps/user/app/(service)/_layout.tsx", 'return <Stack screenOptions={{ headerShown: false }} />;'],
  ["apps/user/app/(service)/events.tsx", "export default function Events()"],
  ["apps/user/app/(service)/stays.tsx", "export default function Stays()"],
  ["apps/user/src/components/ride/RideScreen.tsx", "export function RideScreen()"],
  ["apps/user/app/(service)/ride-status/[reference].tsx", "export default function RideStatusScreen()"],
  ["apps/user/app/(service)/delete-account.tsx", "export default function DeleteAccountScreen()"],
  ["apps/user/app/(service)/adventure.tsx", "export default function Adventure()"],
];

const nativeResetRoutes = [
  // Sign-in is shared by the /login route and the Account tab, so the contract
  // follows the form: login must render it, and it must keep recovery native.
  ["apps/user/app/login.tsx", "<SignInForm />"],
  ["apps/user/src/auth/SignInForm.tsx", 'router.push("/forgot-password")'],
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
    throw new Error(
      `Authenticated User route must remain inside the guarded service stack: ${relative}`
    );
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
  // Hidden developer-only preview route, launched from the five-tap Account menu.
  "connection.tsx",
]);

const userRootRoutes = path.join(root, "apps/user/app");

for (const entry of fs.readdirSync(userRootRoutes, { withFileTypes: true })) {
  if (
    entry.isFile() &&
    [".tsx", ".ts", ".jsx", ".js"].some((extension) =>
      entry.name.endsWith(extension)
    ) &&
    !publicRootRouteFiles.has(entry.name)
  ) {
    throw new Error(
      `Unclassified User root route ${entry.name}; private routes belong in a guarded route group.`
    );
  }
}

// Verify that required native routes and password-recovery flows still exist.
for (const [relative, snippet] of [
  ...nativeInternalRoutes,
  ...nativeResetRoutes,
]) {
  const sourcePath = path.join(root, relative);

  if (!fs.existsSync(sourcePath)) {
    throw new Error(`Required navigation source file is missing: ${relative}`);
  }

  const source = fs.readFileSync(sourcePath, "utf8");

  if (!source.includes(snippet)) {
    throw new Error(
      `Required native route or password-recovery flow is missing or changed: ${relative}\nExpected: ${snippet}`
    );
  }
}

function walk(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    if (
      entry.name === "node_modules" ||
      entry.name === ".expo" ||
      entry.name === "dist" ||
      entry.name === ".dist-check"
    ) {
      return [];
    }

    const full = path.join(directory, entry.name);

    if (entry.isDirectory()) {
      return walk(full);
    }

    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

// Build the approved count per source file.
// A file may deliberately contain more than one approved handoff.
const expected = new Map();

for (const [relative, snippet, visibleLabel] of approved) {
  const key = path.join(root, relative);

  expected.set(key, (expected.get(key) ?? 0) + 1);

  if (!fs.existsSync(key)) {
    throw new Error(`Approved external navigation source is missing: ${relative}`);
  }

  const source = fs.readFileSync(key, "utf8");

  if (!source.includes(snippet)) {
    throw new Error(
      `Approved external navigation changed or disappeared: ${relative}\nExpected: ${snippet}`
    );
  }

  if (visibleLabel && !source.includes(visibleLabel)) {
    throw new Error(
      `External browser handoff must be visibly labelled as a website action: ${relative}\nExpected: ${visibleLabel}`
    );
  }
}

// Reject any unapproved browser or external URL-opening calls.
const violations = [];
let actualTotal = 0;

for (const file of walk(path.join(root, "apps"))) {
  const source = fs.readFileSync(file, "utf8");

  const calls =
    source.match(/(?:WebBrowser\.openBrowserAsync|Linking\.openURL)\s*\(/g) ?? [];

  actualTotal += calls.length;

  const allowedCount = expected.get(file) ?? 0;

  if (calls.length !== allowedCount) {
    violations.push(
      `${path.relative(root, file)}: found ${calls.length} browser/URL-opening call(s), approved ${allowedCount}`
    );
  }

  if (source.includes("/apps/delete-account")) {
    violations.push(
      `${path.relative(root, file)}: account deletion must stay in the native app`
    );
  }
}

if (actualTotal !== approved.length) {
  violations.push(
    `Total browser/URL-opening calls: ${actualTotal}; approved ${approved.length}`
  );
}

if (violations.length) {
  console.error("Native navigation contract FAILED:");

  for (const violation of violations) {
    console.error(" - " + violation);
  }

  process.exit(1);
}

console.log(
  `Native navigation contract passed: ${approved.length} explicitly labelled website handoffs; password recovery and account deletion remain native.`
);