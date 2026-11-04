import { ApiClient, ApiError, RequestOptions } from "../api/client";
import {
  MobileAuthClientOptions,
  MobileAuthError,
  MobileClientKind,
  MobileIdentity,
  MobileLoginResult,
  SecureTokenStore
} from "./token-store";

type Envelope<T> = {
  success?: boolean;
  message?: string;
  code?: string;
  mfa_required?: boolean;
  challenge_token?: string;
  expires_in?: number;
  data?: T;
};

type TokenPayload = {
  token_type: "Bearer";
  access_token: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
  user?: MobileIdentity;
};

export class MobileAuthClient {
  private readonly client: MobileClientKind;
  private readonly store: SecureTokenStore;
  private readonly api: ApiClient;
  private readonly deviceName: string;
  private refreshInFlight: Promise<boolean> | null = null;

  constructor(options: MobileAuthClientOptions) {
    this.client = options.client;
    this.store = options.store;
    this.deviceName = options.deviceName ?? (options.client === "driver" ? "AFCON360 Driver" : "AFCON360 User");
    this.api = new ApiClient({
      baseUrl: options.baseUrl,
      readAccessToken: () => this.store.getAccessToken(),
      timeoutMs: 20000
    });
  }

  private async saveTokens(payload: TokenPayload): Promise<void> {
    if (!payload.access_token || !payload.refresh_token) {
      throw new MobileAuthError("The authentication service returned incomplete credentials.", "token_response_invalid");
    }
    await this.store.setAccessToken(payload.access_token);
    await this.store.setRefreshToken(payload.refresh_token);
  }

  private async envelopeError(error: unknown): Promise<MobileAuthError> {
    if (error instanceof ApiError) {
      const body = error.payload as { code?: string; message?: string } | null;
      return new MobileAuthError(
        body?.message ?? error.message,
        body?.code ?? "api_error",
        error.status
      );
    }
    if (error instanceof Error) return new MobileAuthError(error.message);
    return new MobileAuthError("AFCON360 could not complete that request.");
  }

  async signIn(identifier: string, password: string): Promise<MobileLoginResult> {
    try {
      const deviceId = await this.store.getDeviceId();
      const response = await this.api.post<Envelope<TokenPayload>>("/api/mobile/v1/auth/login", {
        identifier: identifier.trim(),
        password,
        client: this.client,
        device_id: deviceId,
        device_name: this.deviceName
      });
      if (response.mfa_required) {
        if (!response.challenge_token) {
          throw new MobileAuthError("The MFA challenge response was incomplete.", "mfa_challenge_invalid");
        }
        return {
          mfaRequired: true,
          challengeToken: response.challenge_token,
          expiresIn: response.expires_in ?? 300
        };
      }
      if (!response.data) {
        throw new MobileAuthError(response.message ?? "Sign-in response was incomplete.", response.code ?? "login_failed");
      }
      await this.saveTokens(response.data);
      const user = await this.getMe();
      return { mfaRequired: false, user };
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  async verifyMfa(challengeToken: string, code: string): Promise<MobileIdentity> {
    try {
      const response = await this.api.post<Envelope<TokenPayload>>("/api/mobile/v1/auth/mfa/verify", {
        challenge_token: challengeToken,
        code: code.trim()
      });
      if (!response.data) {
        throw new MobileAuthError(response.message ?? "Authenticator verification was incomplete.", response.code ?? "mfa_failed");
      }
      await this.saveTokens(response.data);
      return await this.getMe();
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  private async refresh(): Promise<boolean> {
    if (this.refreshInFlight) return this.refreshInFlight;
    this.refreshInFlight = (async () => {
      const refreshToken = await this.store.getRefreshToken();
      if (!refreshToken) return false;
      try {
        // Call the base client directly to prevent recursive 401 refresh loops.
        const response = await this.api.post<Envelope<TokenPayload>>("/api/mobile/v1/auth/refresh", {
          refresh_token: refreshToken
        });
        if (!response.data) {
          await this.store.clearTokens();
          return false;
        }
        await this.saveTokens(response.data);
        return true;
      } catch {
        await this.store.clearTokens();
        return false;
      } finally {
        this.refreshInFlight = null;
      }
    })();
    return this.refreshInFlight;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    try {
      return await this.api.request<T>(path, options);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401 && !path.endsWith("/auth/refresh")) {
        const refreshed = await this.refresh();
        if (refreshed) return this.api.request<T>(path, options);
      }
      throw await this.envelopeError(error);
    }
  }

  async getMe(): Promise<MobileIdentity> {
    const response = await this.request<Envelope<MobileIdentity>>("/api/mobile/v1/auth/me");
    if (!response.data) throw new MobileAuthError("Your account details could not be loaded.", "identity_response_invalid");
    return response.data;
  }

  async restoreSession(): Promise<MobileIdentity | null> {
    const access = await this.store.getAccessToken();
    const refresh = await this.store.getRefreshToken();
    if (!access && !refresh) return null;
    try {
      return await this.getMe();
    } catch {
      await this.store.clearTokens();
      return null;
    }
  }

  async logout(): Promise<void> {
    try {
      await this.request("/api/mobile/v1/auth/logout", { method: "POST" });
    } finally {
      await this.store.clearTokens();
    }
  }

  async deleteAccount(password: string, confirmation: string, mfaCode?: string): Promise<void> {
    await this.request("/api/mobile/v1/auth/account-deletion", {
      method: "POST",
      body: {
        password,
        confirmation,
        mfa_code: mfaCode
      }
    });
    await this.store.clearTokens();
  }

  async clearLocalCredentials(): Promise<void> {
    await this.store.clearTokens();
  }
}

export { MobileAuthError };
