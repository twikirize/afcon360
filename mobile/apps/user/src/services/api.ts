import Constants from "expo-constants";
import * as SecureStore from "expo-secure-store";
import {
  MobileAuthClient,
  MobileWalletClient,
  MobileAccommodationClient,
  MobileEventClient,
  SecureTokenStore
} from "@afcon360/mobile-core";

const ACCESS_TOKEN_KEY = "afcon360.user.access-token";
const REFRESH_TOKEN_KEY = "afcon360.user.refresh-token";
const DEVICE_ID_KEY = "afcon360.user.device-id";
const API_BASE_URL_KEY = "afcon360.user.api-base-url";

const DEFAULT_API_BASE_URL =
  (Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ??
  process.env.EXPO_PUBLIC_API_BASE_URL ??
  "https://www.pamoja.space";

export const SERVER_SELECTION_ENABLED =
  Constants.expoConfig?.extra?.allowServerSelection === true;

const store: SecureTokenStore = {
  getAccessToken: () => SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
  setAccessToken: token => SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token),
  getRefreshToken: () => SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  setRefreshToken: token => SecureStore.setItemAsync(REFRESH_TOKEN_KEY),
  async getDeviceId() {
    let id = await SecureStore.getItemAsync(DEVICE_ID_KEY);
    if (!id) {
      id = "u-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
      await SecureStore.setItemAsync(DEVICE_ID_KEY, id);
    }
    return id;
  },
  async clearTokens() {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  }
};

export const authClient = new MobileAuthClient({
  client: "user",
  store,
  deviceName: "AFCON360 User",
  getBaseUrl: async () => (await SecureStore.getItemAsync(API_BASE_URL_KEY)) ?? undefined,
  allowPrivateHttp: SERVER_SELECTION_ENABLED
});

export const walletClient = new MobileWalletClient(authClient);
export const accommodationClient = new MobileAccommodationClient(authClient);
export const eventClient = new MobileEventClient(authClient);

function isPrivateIpv4(hostname: string): boolean {
  const parts = hostname.split(".");
  if (parts.length !== 4 || !parts.every(part => /^\d{1,3}$/.test(part))) return false;
  const octets = parts.map(Number);
  if (octets.some(value => value < 0 || value > 255)) return false;
  const [first, second] = octets;
  return first === 10 ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168);
}

export function normalizePreviewApiBaseUrl(value: string): string {
  if (!SERVER_SELECTION_ENABLED) {
    throw new Error("Server selection is available only in AFCON360 preview builds.");
  }
  const trimmed = value.trim();
  if (!trimmed) throw new Error("Enter an API server address.");
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    throw new Error("Enter a complete server address beginning with http:// or https://.");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash || (parsed.pathname && parsed.pathname !== "/")) {
    throw new Error("Enter only the server origin. Do not include a username, password, path, query or fragment.");
  }
  if (parsed.protocol === "http:") {
    if (!isPrivateIpv4(parsed.hostname) || parsed.port !== "5000") {
      throw new Error("For laptop staging, use a private Wi-Fi IPv4 address with port 5000, for example http://192.168.100.28:5000.");
    }
  } else if (parsed.protocol !== "https:") {
    throw new Error("Use HTTPS for public servers.");
  }
  return parsed.toString().replace(/\/$/, "");
}

export async function getSelectedApiBaseUrl(): Promise<string> {
  return (await SecureStore.getItemAsync(API_BASE_URL_KEY)) ?? DEFAULT_API_BASE_URL;
}

export async function changeApiServerBaseUrl(value: string): Promise<{
  baseUrl: string;
  changed: boolean;
  remoteLogoutConfirmed: boolean;
}> {
  const nextBaseUrl = normalizePreviewApiBaseUrl(value);
  const currentBaseUrl = await getSelectedApiBaseUrl();
  if (nextBaseUrl === currentBaseUrl) {
    return { baseUrl: currentBaseUrl, changed: false, remoteLogoutConfirmed: true };
  }

  let remoteLogoutConfirmed = true;
  const accessToken = await SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  if (accessToken || refreshToken) {
    try {
      // Revoke the old server/device session before switching origins.
      await authClient.logout();
    } catch {
      // The old server may be offline. Credentials are still erased locally,
      // and the UI tells the user that remote revocation could not be confirmed.
      remoteLogoutConfirmed = false;
      await authClient.clearLocalCredentials();
    }
  } else {
    await authClient.clearLocalCredentials();
  }

  await SecureStore.setItemAsync(API_BASE_URL_KEY, nextBaseUrl);
  return { baseUrl: nextBaseUrl, changed: true, remoteLogoutConfirmed };
}
