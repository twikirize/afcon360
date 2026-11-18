export interface SecureTokenStore {
  getAccessToken(): Promise<string | null>;
  setAccessToken(token: string): Promise<void>;
  getRefreshToken(): Promise<string | null>;
  setRefreshToken(token: string): Promise<void>;
  getDeviceId(): Promise<string>;
  clearTokens(): Promise<void>;
}

export type MobileClientKind = "user" | "driver";

export type MobileIdentity = {
  public_id: string;
  username: string;
  display_name?: string | null;
  email?: string | null;
  email_verified?: boolean;
  mfa_enabled?: boolean;
  client: MobileClientKind;
  contexts?: Array<{
    type: string;
    public_id?: string | null;
    label: string;
    role?: string | null;
  }>;
};

export type MobileLoginResult =
  | {
      mfaRequired: true;
      challengeToken: string;
      expiresIn: number;
      mfaType: "totp" | "sms";
      destinationHint?: string;
    }
  | { mfaRequired: false; user: MobileIdentity };

export type MobileAuthClientOptions = {
  client: MobileClientKind;
  store: SecureTokenStore;
  baseUrl?: string;
  getBaseUrl?: () => Promise<string | undefined>;
  allowPrivateHttp?: boolean;
  deviceName?: string;
};

export class MobileAuthError extends Error {
  readonly code: string;
  readonly status?: number;
  constructor(message: string, code = "mobile_auth_error", status?: number) {
    super(message);
    this.name = "MobileAuthError";
    this.code = code;
    this.status = status;
  }
}
