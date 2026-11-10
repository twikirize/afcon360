import { useEffect } from "react";
import { AppState, AppStateStatus } from "react-native";
import * as Location from "expo-location";
import { authClient } from "../services/api";

/**
 * Foreground-only location publisher for an online Driver.
 *
 * The server remains authoritative for dispatch eligibility and location
 * freshness. This publisher only sends device fixes; it never changes
 * Driver online state and does not request background-location permission.
 */
export function DriverLocationPublisher({ active }: { active: boolean }) {
  useEffect(() => {
    let mounted = true;
    let online = false;
    let publishInFlight = false;
    let permissionRequested = false;
    let watcher: Location.LocationSubscription | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;
    let lastPublishedAt = 0;
    let statusRequestInFlight = false;

    const stopWatcher = () => {
      if (watcher) {
        watcher.remove();
        watcher = null;
      }
    };

    const publish = async (location: Location.LocationObject) => {
      if (
        !mounted ||
        !online ||
        publishInFlight ||
        AppState.currentState !== "active"
      ) return;

      const now = Date.now();
      // Guard against duplicate device callbacks. The watcher is configured
      // for the website's 120-second reporting cadence; allow modest
      // scheduling jitter but never flood the mobile API.
      if (now - lastPublishedAt < 90_000) return;

      publishInFlight = true;
      try {
        await authClient.request("/api/mobile/v1/driver/location", {
          method: "POST",
          body: {
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
            accuracy: location.coords.accuracy,
            speed: location.coords.speed,
            heading: location.coords.heading,
            client_ts: location.timestamp
          }
        });
        lastPublishedAt = now;
      } catch {
        // A failed GPS publish must not take the Driver workspace offline.
        // The next fresh device fix can retry; stale coordinates are not
        // replayed from a local queue.
      } finally {
        publishInFlight = false;
      }
    };

    const startWatcher = async () => {
      if (
        !mounted ||
        !active ||
        !online ||
        AppState.currentState !== "active" ||
        watcher
      ) return;

      try {
        let permission = await Location.getForegroundPermissionsAsync();
        if (permission.status !== "granted" && !permissionRequested) {
          permissionRequested = true;
          permission = await Location.requestForegroundPermissionsAsync();
        }
        if (!mounted || permission.status !== "granted") return;

        watcher = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.Balanced,
            timeInterval: 120_000,
            distanceInterval: 50,
            mayShowUserSettingsDialog: true
          },
          location => {
            void publish(location);
          }
        );
        if (!mounted || AppState.currentState !== "active" || !online) {
          stopWatcher();
        }
      } catch {
        stopWatcher();
      }
    };

    const refreshStatus = async () => {
      if (!mounted || !active || statusRequestInFlight) return;
      if (AppState.currentState !== "active") {
        stopWatcher();
        return;
      }
      statusRequestInFlight = true;
      try {
        const response = await authClient.request<{ data: { is_online: boolean } }>(
          "/api/mobile/v1/driver/me"
        );
        if (!mounted) return;
        online = response.data.is_online === true;
        if (online) {
          await startWatcher();
        } else {
          stopWatcher();
        }
      } catch {
        // Fail closed for location publishing when Driver status cannot be
        // confirmed. A later foreground refresh can safely resume it.
        online = false;
        stopWatcher();
      } finally {
        statusRequestInFlight = false;
      }
    };

    void refreshStatus();
    pollTimer = setInterval(() => {
      if (AppState.currentState === "active") void refreshStatus();
    }, 30_000);

    const onAppState = (state: AppStateStatus) => {
      if (state === "active") {
        void refreshStatus();
      } else {
        stopWatcher();
      }
    };
    const subscription = AppState.addEventListener("change", onAppState);

    return () => {
      mounted = false;
      online = false;
      stopWatcher();
      subscription.remove();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [active]);

  return null;
}
