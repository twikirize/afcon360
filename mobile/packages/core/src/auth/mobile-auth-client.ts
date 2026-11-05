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

type RegistrationEnvelope = Envelope<{
  registration_token?: string;
  email?: string;
  expires_in?: number;
  message?: string;
  username?: string;
}> & {
  registration_pending?: boolean;
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
      await this.store.clearTokens();
      throw new MobileAuthError("The authentication service returned incomplete credentials.", "token_response_invalid");
    }
    try {
      // SecureStore writes are separate OS operations, not one transaction.
      // If either write fails, remove any partial credential pair.
      await this.store.setAccessToken(payload.access_token);
      await this.store.setRefreshToken(payload.refresh_token);
    } catch (error) {
      try {
        await this.store.clearTokens();
      } catch {
        // Preserve the original secure-storage failure for the caller.
      }
      throw new MobileAuthError(
        error instanceof Error ? error.message : "AFCON360 could not securely store the sign-in credentials.",
        "secure_storage_failed"
      );
    }
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

  async register(input: {
    username: string;
    email: string;
    password: string;
    full_name?: string;
  }): Promise<{
    verificationRequired: boolean;
    registrationToken?: string;
    email: string;
    message: string;
    expiresIn?: number;
  }> {
    try {
      const response = await this.api.post<RegistrationEnvelope>("/api/mobile/v1/auth/register", input);
      if (!response.success) {
        throw new MobileAuthError(response.message ?? "AFCON360 could not create the account.", response.code ?? "registration_failed");
      }
      const data = response.data ?? {};
      if (response.registration_pending && !data.registration_token) {
        throw new MobileAuthError("The verification service returned an incomplete response. Please try again.", "registration_response_invalid");
      }
      return {
        verificationRequired: !!response.registration_pending,
        registrationToken: data.registration_token,
        email: data.email ?? input.email,
        message: data.message ?? response.message ?? "Your account request was accepted.",
        expiresIn: data.expires_in
      };
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  async verifyRegistration(registrationToken: string, code: string): Promise<string> {
    try {
      const response = await this.api.post<Envelope<{ message?: string }>>("/api/mobile/v1/auth/register/verify", {
        registration_token: registrationToken,
        code: code.trim()
      });
      if (!response.success) {
        throw new MobileAuthError(response.message ?? "We could not verify that code.", response.code ?? "registration_verification_failed");
      }
      return response.data?.message ?? response.message ?? "Your email is verified. You can sign in.";
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  async resendRegistrationCode(registrationToken: string): Promise<string> {
    try {
      const response = await this.api.post<Envelope<{ message?: string }>>("/api/mobile/v1/auth/register/resend", {
        registration_token: registrationToken
      });
      if (!response.success) {
        throw new MobileAuthError(response.message ?? "We could not resend the verification code.", response.code ?? "registration_resend_failed");
      }
      return response.data?.message ?? response.message ?? "A new verification code has been sent.";
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  async requestPasswordReset(identifier: string): Promise<{ message: string; expiresIn: number }> {
    const normalized = identifier.trim();
    if (!normalized) {
      throw new MobileAuthError("Enter your AFCON360 username or email address.", "password_reset_identifier_required");
    }
    try {
      const response = await this.api.post<Envelope<{ message?: string; expires_in?: number }>>(
        "/api/mobile/v1/auth/password-reset/request",
        { identifier: normalized }
      );
      if (!response.success || !response.data) {
        throw new MobileAuthError(
          response.message ?? "AFCON360 could not start the password reset.",
          response.code ?? "password_reset_request_failed"
        );
      }
      return {
        message: response.data.message ?? "If an active account has a registered email address, a reset code has been sent.",
        expiresIn: response.data.expires_in ?? 600
      };
    } catch (error) {
      throw await this.envelopeError(error);
    }
  }

  async confirmPasswordReset(input: {
    identifier: string;
    code: string;
    newPassword: string;
    confirmPassword: string;
  }): Promise<string> {
    try {
      const response = await this.api.post<Envelope<{ message?: string }>>(
        "/api/mobile/v1/auth/password-reset/confirm",
        {
          identifier: input.identifier.trim(),
          code: input.code.trim(),
          new_password: input.newPassword,
          confirm_password: input.confirmPassword
        }
      );
      if (!response.success || !response.data) {
        throw new MobileAuthError(
          response.message ?? "AFCON360 could not complete the password reset.",
          response.code ?? "password_reset_failed"
        );
      }
      return response.data.message ?? "Your password has been reset. Sign in with your new password.";
    } catch (error) {
      throw await this.envelopeError(error);
    }
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
      if (!refreshToken) {
        await this.store.clearTokens();
        return false;
      }
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
      } catch (error) {
        // A revoked or invalid refresh credential is terminal and must be
        // removed. Network errors, rate limiting and 5xx responses are
        // temporary: preserve the refresh credential so the user can retry
        // after connectivity/service recovery instead of being signed out.
        if (error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500 &&
            error.status !== 429) {
          await this.store.clearTokens();
        }
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
    } catch (error) {
      // A revoked/expired credential is cleared by the refresh path. Preserve
      // credentials after transient server/network failures so users are not
      // silently signed out during an outage.
      if (error instanceof MobileAuthError && error.status && error.status >= 500) {
        throw error;
      }
      if (!await this.store.getAccessToken() && !await this.store.getRefreshToken()) return null;
      throw error;
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

