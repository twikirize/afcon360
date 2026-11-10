import React, { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { MobileAuthError, MobileIdentity } from "@afcon360/mobile-core";
import { authClient, changeApiServerBaseUrl } from "../services/api";

type ApiServerChangeResult = {
  baseUrl: string;
  changed: boolean;
  remoteLogoutConfirmed: boolean;
};

type AuthContextValue = {
  user: MobileIdentity | null;
  loading: boolean;
  restoreError: string | null;
  retryRestoreSession(): Promise<void>;
  signingIn: boolean;
  mfaChallenge: string | null;
  mfaType: "totp" | "sms" | null;
  mfaDestinationHint: string | null;
  signIn(identifier: string, password: string): Promise<boolean>;
  verifyMfa(code: string): Promise<void>;
  cancelMfa(): void;
  changeApiServer(url: string): Promise<ApiServerChangeResult>;
  logout(): Promise<void>;
  deleteAccount(password: string, confirmation: string, mfaCode?: string): Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MobileIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);
  const [mfaType, setMfaType] = useState<"totp" | "sms" | null>(null);
  const [mfaDestinationHint, setMfaDestinationHint] = useState<string | null>(null);

  const retryRestoreSession = useCallback(async () => {
    setLoading(true);
    setRestoreError(null);
    try {
      setUser(await authClient.restoreSession());
    } catch (error) {
      // Keep the saved credentials intact. A transient server/network failure
      // must not be presented as a successful sign-out or force a new login.
      setUser(null);
      setRestoreError(error instanceof Error
        ? error.message
        : "AFCON360 could not verify your saved session. Check your connection and retry.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void retryRestoreSession();
  }, [retryRestoreSession]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    restoreError,
    retryRestoreSession,
    signingIn,
    mfaChallenge,
    mfaType,
    mfaDestinationHint,
    async signIn(identifier, password) {
      setSigningIn(true);
      setRestoreError(null);
      try {
        const result = await authClient.signIn(identifier, password);
        if (result.mfaRequired) {
          setMfaChallenge(result.challengeToken);
          setMfaType(result.mfaType);
          setMfaDestinationHint(result.destinationHint ?? null);
          return true;
        }
        setUser(result.user);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
        return false;
      } finally {
        setSigningIn(false);
      }
    },
    async verifyMfa(code) {
      if (!mfaChallenge) throw new MobileAuthError("The sign-in challenge has expired. Start again.", "mfa_challenge_missing");
      setSigningIn(true);
      try {
        const identity = await authClient.verifyMfa(mfaChallenge, code);
        setUser(identity);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
      } finally {
        setSigningIn(false);
      }
    },
    cancelMfa() {
      setMfaChallenge(null);
      setMfaType(null);
      setMfaDestinationHint(null);
    },
    async changeApiServer(url) {
      const result = await changeApiServerBaseUrl(url);
      if (result.changed) {
        setUser(null);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
        setRestoreError(null);
      }
      return result;
    },
    async logout() {
      setRestoreError(null);
      try { await authClient.logout(); } finally {
        setUser(null);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
      }
    },
    async deleteAccount(password, confirmation, mfaCode) {
      setRestoreError(null);
      await authClient.deleteAccount(password, confirmation, mfaCode);
      setUser(null);
      setMfaChallenge(null);
      setMfaType(null);
      setMfaDestinationHint(null);
    }
  }), [user, loading, restoreError, retryRestoreSession, signingIn, mfaChallenge, mfaType, mfaDestinationHint]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
