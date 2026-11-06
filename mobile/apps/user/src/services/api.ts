import * as SecureStore from "expo-secure-store";
import { MobileAuthClient, MobileWalletClient, MobileAccommodationClient, SecureTokenStore } from "@afcon360/mobile-core";

const ACCESS_TOKEN_KEY = "afcon360.user.access-token";
const REFRESH_TOKEN_KEY = "afcon360.user.refresh-token";
const DEVICE_ID_KEY = "afcon360.user.device-id";

const store: SecureTokenStore = {
  getAccessToken: () => SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
  setAccessToken: token => SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token),
  getRefreshToken: () => SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  setRefreshToken: token => SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token),
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
  deviceName: "AFCON360 User"
});

export const walletClient = new MobileWalletClient(authClient);

export const accommodationClient = new MobileAccommodationClient(authClient);
