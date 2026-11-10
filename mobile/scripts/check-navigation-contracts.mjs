import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");

// Every external website handoff must be reviewed and visibly labelled.
const approved = [
  ["apps/user/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', 'label="Privacy notice (website)"'],
  ["apps/user/app/(tabs)/explore.tsx", 'WebBrowser.openBrowserAsync(SITE + "/tourism")', 'label="Explore tourism on website"'],
  ["apps/driver/app/login.tsx", 'WebBrowser.openBrowserAsync(SITE + "/transport/become-driver")', 'label="Continue driver registration on website"'],
  ["apps/user/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", 'label="Back to AFCON360 website home"'],
  ["apps/driver/app/login.tsx", "WebBrowser.openBrowserAsync(SITE)", 'label="Back to AFCON360 website home"'],
  ["apps/driver/app/(tabs)/account.tsx", 'WebBrowser.openBrowserAsync("https://www.pamoja.space/apps/privacy")', 'label="Privacy notice (working draft)"'],
  ["apps/driver/app/(tabs)/account.tsx", 'Linking.openURL("mailto:support@afcon360.com?subject=AFCON360%20Driver%20Support")', 'label="Email AFCON360 support"'],
  ["apps/user/app/(tabs)/wallet.tsx", "Linking.openURL(checkout.toString())", 'label={busy ? "Starting secure checkout…" : "Continue to Flutterwave"}'],
  ["apps/user/app/(tabs)/wallet.tsx", "Linking.openURL(checkout.toString())", 'label="Open Flutterwave checkout"'],
];

const nativeInternalRoutes = [
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(tabs)/events" as never)'],
  ["apps/user/app/(tabs)/_layout.tsx", 'name="events" options={{ href: null }}'],
  ["apps/user/app/(tabs)/explore.tsx", 'router.push("/(tabs)/stays" as never)'],
  ["apps/user/app/(tabs)/_layout.tsx", 'name="stays" options={{ href: null }}'],
];

const nativeResetRoutes = [
  ["apps/user/app/login.tsx", 'router.push("/forgot-password")'],
  ["apps/driver/app/login.tsx", 'router.push("/forgot-password")'],
  ["apps/user/app/forgot-password.tsx", "<PasswordResetFlow"],
  ["apps/driver/app/forgot-password.tsx", "<PasswordResetFlow"],
  ["packages/core/src/auth/mobile-auth-client.ts", "/api/mobile/v1/auth/password-reset/request"],
  ["packages/ui/src/auth.tsx", "export function PasswordResetFlow"],
];

for (const [relative, snippet] of [...nativeInternalRoutes, ...nativeResetRoutes]) {
  const source = fs.readFileSync(path.join(root, relative), "utf8");
  if (!source.includes(snippet)) throw new Error(`Required native route or password-recovery flow is missing or changed: ${relative}`);
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
