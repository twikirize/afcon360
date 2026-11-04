import * as SecureStore from "expo-secure-store";
import { ApiClient } from "@afcon360/mobile-core";
const ACCESS_TOKEN_KEY = "afcon360.driver.access-token";
export const api = new ApiClient({ readAccessToken: () => SecureStore.getItemAsync(ACCESS_TOKEN_KEY) });
// Do not write a token until the backend issues one through the approved native auth flow.
export const clearMobileSession = () => SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
