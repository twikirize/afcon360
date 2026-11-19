# Windows Android APK Build Investigation

**Date:** 2026-11-19  
**Branch:** `clean/apk-base-10d858ba`  
**Commit:** `10d858ba` (Fix user app component imports and ticket purchase types)  
**Goal:** Produce a standalone release APK (`assembleRelease`) for offline-first usage.

---

## 1. Environment Configuration

| Component | Version / Path |
|-----------|----------------|
| **JDK** | Microsoft OpenJDK 17.0.21.102 (LTS) — `C:\Program Files\Microsoft\jdk-17.0.21.102-hotspot` |
| **Android SDK** | `C:\Users\OBED\AppData\Local\Android\Sdk` (platform-tools, build-tools 37.0.0, platforms 37) |
| **NDK** | r27c (27.2.12479018) — `C:\Users\OBED\AppData\Local\Android\Sdk\ndk\27.1.12297006` |
| **CMake** | 3.22.1 — bundled with Android SDK |
| **Ninja** | 1.11.1 — bundled with Android SDK |
| **Gradle** | 9.4.1 (wrapper) |
| **Android Gradle Plugin (AGP)** | 9.2.1 |
| **Kotlin Gradle Plugin** | 2.2.10 (version catalog declares 2.2.0) |
| **Node.js** | v26.5.0 |
| **pnpm** | 10.12.4 |
| **Expo SDK** | 58.0.26 |
| **React Native** | 0.88.1 |

---

## 2. Gradle Build Command

```powershell
$env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.21.102-hotspot"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$env:AFCON360_PREVIEW_BUILD = "true"
$env:AFCON360_RELEASE_BUILD = "false"
$env:USE_SQLCIPHER = "false"
.\gradlew.bat --stop
.\gradlew.bat app:assembleRelease -x lint -x test --configure-on-demand --build-cache --no-daemon
```

**Working Directory:** `C:\afcon360-user-dev\mobile\apps\user\android` (short path copy)

---

## 3. Key Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `JAVA_HOME` | `C:\Program Files\Microsoft\jdk-17.0.21.102-hotspot` | JDK 17 for Gradle compatibility |
| `AFCON360_PREVIEW_BUILD` | `true` | Preview build flag |
| `AFCON360_RELEASE_BUILD` | `false` | Release build flag |
| `USE_SQLCIPHER` | `false` | **CRITICAL: Disables SQLCipher for build investigation only** |

> ⚠️ **SECURITY NOTE:** `USE_SQLCIPHER=false` was set **only for build investigation**. The intended production configuration **must retain SQLCipher** (`expo.sqlite.useSQLCipher=true`). This is not an approved production configuration.

---

## 4. Gradle Properties (Modified)

File: `mobile/apps/user/android/gradle.properties`

```properties
org.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=512m -Djava.net.preferIPv4Stack=true
org.gradle.parallel=false
android.cmake.buildArguments=-j1
android.cmake.configureArgs=-DCMAKE_BUILD_TYPE=Release -DCMAKE_CONFIGURATION_TYPES=Release
expo.sqlite.useSQLCipher=false
```

**Changes from defaults:**
- `-Djava.net.preferIPv4Stack=true` — Forces IPv4 for Gradle to avoid `dl.google.com` DNS issues
- `org.gradle.parallel=false` — Disables parallel execution to reduce CMake contention
- `android.cmake.buildArguments=-j1` — Single-threaded ninja to avoid Windows file locking
- `android.cmake.configureArgs` — Explicit Release configuration
- `expo.sqlite.useSQLCipher=false` — **Investigation only; disables SQLCipher/OpenSSL CMake complexity**

---

## 5. CMake Path Length Warning

```
C/C++: CMake Warning in C:/Users/OBED/Desktop/afcon360-user-dev/mobile/node_modules/.pnpm/react-native-worklets@0.13._94019be2676a3df6459ef95243c34939/node_modules/react-native-worklets/android/.cxx/RelWithDebInfo/.../CMakeFiles/CMakeTmp/CMakeLists.txt:
The object file directory has 257 characters. The maximum full path to an object file is 250 characters (see CMAKE_OBJECT_PATH_MAX). Object file CMakeCCompilerABI.c.o cannot be safely placed under this directory.
```

**Impact:** CMake object path exceeds 250-char limit → triggers CMake reconfiguration on each build step.

---

## 6. Build Failure: `build.ninja still dirty after 100 tries`

**Error:**
```
ninja: error: manifest 'build.ninja' still dirty after 100 tries
```

**Root Cause:** CMake `file(GLOB ... CONFIGURE_DEPENDS)` on Windows causes infinite reconfiguration loop. Each ninja run detects "dirty" manifest and re-runs CMake.

**Affected Modules:**
1. `react-native-worklets` (0.13.x)
2. `expo-sqlite` (58.0.17)

---

## 7. Workarounds Attempted

| # | Workaround | Result |
|---|------------|--------|
| 1 | Installed Microsoft OpenJDK 17 | ✅ Success |
| 2 | Manual NDK r27c download + extract | ✅ Success (placed at correct path with `source.properties`) |
| 2b | Added `-Djava.net.preferIPv4Stack=true` | ✅ Fixed `dl.google.com` DNS resolution |
| 3 | `org.gradle.parallel=false` + `android.cmake.buildArguments=-j1` | ⚠️ Reduced but didn't eliminate contention |
| 4 | Patched `file(GLOB CONFIGURE_DEPENDS)` → explicit source lists in both CMakeLists.txt | ⚠️ Eliminated GLOB but path length still triggers reconfig |
| 5 | Disabled SQLCipher (`USE_SQLCIPHER=false`, `expo.sqlite.useSQLCipher=false`) | ✅ Simplified expo-sqlite CMake, removed OpenSSL dependency |
| 6 | Copied project to short path `C:\afcon360-user-dev` | ⚠️ Path length reduced but `.cxx` dir still created under original long path |
| 7 | `subst` drive mapping (`Z:`) | ⚠️ Build still referenced original `C:\Users\OBED\Desktop\...` paths |

---

## 8. Workarounds Not Yet Verified

| Workaround | Status |
|------------|--------|
| `set(CMAKE_OBJECT_PATH_MAX 500)` in CMakeLists.txt | Not tried |
| `expo prebuild --clean && npx expo run:android --variant release` | Not tried |
| EAS Build (cloud macOS/Linux runners) | Not tried — would bypass Windows path limits entirely |
| Symlink/junction for `.cxx` directory to short path | Not tried |

---

## 9. APK Production Status

**No APK was successfully produced.**

The build consistently fails at `:react-native-worklets:buildCMakeRelWithDebInfo[arm64-v8a][worklets]` with the ninja manifest error.

---

## 10. Vendor Override Evidence (Preserved in `mobile/build-diagnostics/vendor-overrides/`)

### react-native-worklets
- **Package:** `react-native-worklets@0.13._94019be2676a3df6459ef95243c34939`
- **Original path:** `C:\Users\OBED\Desktop\afcon360-user-dev\mobile\node_modules\.pnpm\react-native-worklets@0.13._94019be2676a3df6459ef95243c34939\node_modules\react-native-worklets\android\CMakeLists.txt`
- **Change:** Replaced `file(GLOB RECURSE ... CONFIGURE_DEPENDS)` with explicit `set(WORKLETS_COMMON_CPP_SOURCES ...)` and `set(WORKLETS_ANDROID_CPP_SOURCES ...)` listing all 57 `.cpp` files.
- **Preserved copy:** `mobile/build-diagnostics/vendor-overrides/react-native-worklets/CMakeLists.txt`
- **Verified:** Source lists match actual files in `Common/cpp/worklets/` and `android/src/main/cpp/worklets/`

### expo-sqlite
- **Package:** `expo-sqlite@58.0.17_expo@58_6e3d44863803edba6643fb4b103999c1`
- **Original path:** `C:\Users\OBED\Desktop\afcon360-user-dev\mobile\node_modules\.pnpm\expo-sqlite@58.0.17_expo@58_6e3d44863803edba6643fb4b103999c1\node_modules\expo-sqlite\android\CMakeLists.txt`
- **Change:** Replaced `file(GLOB SOURCES "${SRC_DIR}/*.cpp")` with explicit `set(SOURCES ...)` listing 4 `.cpp` files.
- **Preserved copy:** `mobile/build-diagnostics/vendor-overrides/expo-sqlite/CMakeLists.txt`
- **Verified:** Source list matches actual files in `android/src/main/cpp/`

---

## 11. Files Changed in This Investigation (Tracked)

| File | Status |
|------|--------|
| `mobile/apps/user/android/gradle.properties` | Modified (new file) |
| `mobile/build-diagnostics/vendor-overrides/react-native-worklets/CMakeLists.txt` | New (evidence) |
| `mobile/build-diagnostics/vendor-overrides/expo-sqlite/CMakeLists.txt` | New (evidence) |
| `mobile/build-diagnostics/BUILD_INVESTIGATION.md` | New (this document) |

---

## 12. Conclusion

The Windows native build fails due to **fundamental CMake/ninja path length and file monitoring limitations on Windows**, not due to application code or configuration errors.

**Recommended path forward:**
1. Use **EAS Build** (cloud runners) for production APKs — avoids Windows CMake issues entirely.
2. For local development, use **Expo dev-client over WiFi** (already working) rather than standalone APK.
3. If standalone APK is required locally, investigate `CMAKE_OBJECT_PATH_MAX` override or CMake 4.x (when available) which may handle long paths better.

**SQLCipher must remain enabled (`expo.sqlite.useSQLCipher=true`) for any production release.** The `USE_SQLCIPHER=false` setting was strictly a diagnostic step to isolate the CMake failure.