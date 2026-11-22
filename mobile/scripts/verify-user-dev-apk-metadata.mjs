import fs from "node:fs";

export function parseAaptBadging(output) {
  if (typeof output !== "string" || !output.trim()) {
    throw new Error("aapt dump badging returned empty output.");
  }

  const packageLine = output.match(
    /^package:\s+name='([^']+)'\s+versionCode='([^']+)'\s+versionName='([^']+)'/m
  );
  const minSdkLine = output.match(/^sdkVersion:'(\d+)'\s*$/m);
  const targetSdkLine = output.match(/^targetSdkVersion:'(\d+)'\s*$/m);

  if (!packageLine) {
    throw new Error("Could not parse package name, versionCode and versionName from aapt output.");
  }
  if (!minSdkLine) {
    throw new Error("Could not parse the standalone sdkVersion entry from aapt output.");
  }
  if (!targetSdkLine) {
    throw new Error("Could not parse the standalone targetSdkVersion entry from aapt output.");
  }

  return {
    packageName: packageLine[1],
    versionCode: Number(packageLine[2]),
    versionName: packageLine[3],
    minSdk: Number(minSdkLine[1]),
    targetSdk: Number(targetSdkLine[1]),
  };
}

export function validateUserDevelopmentApkMetadata(metadata, expectedVersionName) {
  const problems = [];
  if (metadata.packageName !== "space.pamoja.afcon360.user.preview.dev") {
    problems.push("package mismatch: " + metadata.packageName);
  }
  if (metadata.versionName !== expectedVersionName) {
    problems.push("versionName mismatch: expected " + expectedVersionName + ", received " + metadata.versionName);
  }
  if (!Number.isInteger(metadata.versionCode) || metadata.versionCode < 1) {
    problems.push("invalid versionCode: " + metadata.versionCode);
  }
  if (metadata.minSdk !== 24) {
    problems.push("minSdk must be 24, received " + metadata.minSdk);
  }
  if (!Number.isInteger(metadata.targetSdk) || metadata.targetSdk < 36) {
    problems.push("targetSdk must be at least 36, received " + metadata.targetSdk);
  }
  if (problems.length) throw new Error(problems.join("; "));
}

function selfTest() {
  const fixture = [
    "package: name='space.pamoja.afcon360.user.preview.dev' versionCode='3' versionName='1.0.2' platformBuildVersionName='17' platformBuildVersionCode='37' compileSdkVersion='37' compileSdkVersionCodename='17'",
    "sdkVersion:'24'",
    "targetSdkVersion:'36'",
    "uses-permission: name='android.permission.INTERNET'",
  ].join("\n");
  const parsed = parseAaptBadging(fixture);
  validateUserDevelopmentApkMetadata(parsed, "1.0.2");

  let rejected = false;
  try {
    validateUserDevelopmentApkMetadata({ ...parsed, packageName: "space.pamoja.afcon360.driver" }, "1.0.2");
  } catch {
    rejected = true;
  }
  if (!rejected) throw new Error("Self-test failed: unexpected package identity was accepted.");

  rejected = false;
  try {
    parseAaptBadging("package: name='incomplete'");
  } catch {
    rejected = true;
  }
  if (!rejected) throw new Error("Self-test failed: incomplete aapt metadata was accepted.");

  process.stdout.write("PASS APK metadata parser fixture, identity rejection and malformed-input rejection.\n");
}

function main() {
  const [badgingPath, expectedVersionName] = process.argv.slice(2);
  if (badgingPath === "--self-test") {
    selfTest();
    return;
  }
  if (!badgingPath || !expectedVersionName) {
    throw new Error("Usage: node verify-user-dev-apk-metadata.mjs <aapt-badging-file> <expected-version-name>");
  }

  const metadata = parseAaptBadging(fs.readFileSync(badgingPath, "utf8"));
  validateUserDevelopmentApkMetadata(metadata, expectedVersionName);

  if (process.env.GITHUB_OUTPUT) {
    fs.appendFileSync(
      process.env.GITHUB_OUTPUT,
      [
        "apk_package=" + metadata.packageName,
        "apk_version_name=" + metadata.versionName,
        "apk_version_code=" + metadata.versionCode,
        "apk_min_sdk=" + metadata.minSdk,
        "apk_target_sdk=" + metadata.targetSdk,
        "",
      ].join("\n"),
      "utf8",
    );
  }

  process.stdout.write([
    metadata.packageName,
    metadata.versionCode,
    metadata.versionName,
    metadata.minSdk,
    metadata.targetSdk,
  ].join("\t") + "\n");
}

try {
  main();
} catch (error) {
  process.stderr.write("APK metadata verification failed: " + error.message + "\n");
  process.exitCode = 1;
}
