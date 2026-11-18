import * as SecureStore from "expo-secure-store";
import { MobileAuthClient, SecureTokenStore } from "@afcon360/mobile-core";

const ACCESS_TOKEN_KEY = "afcon360.driver.access-token";
const REFRESH_TOKEN_KEY = "afcon360.driver.refresh-token";
const DEVICE_ID_KEY = "afcon360.driver.device-id";

const store: SecureTokenStore = {
  getAccessToken: () => SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
  setAccessToken: token => SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token),
  getRefreshToken: () => SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  setRefreshToken: token => SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token),
  async getDeviceId() {
    let id = await SecureStore.getItemAsync(DEVICE_ID_KEY);
    if (!id) {
      id = "d-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
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
  client: "driver",
  store,
  deviceName: "AFCON360 Driver"
});
