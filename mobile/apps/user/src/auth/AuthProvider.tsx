import React, { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AppState } from "react-native";
import { MobileAuthError, MobileIdentity } from "@afcon360/mobile-core";
import { authClient, changeApiServerBaseUrl, getSelectedApiBaseUrl } from "../services/api";
import { clearAllOfflineData, clearOfflineAccount, readOfflineIdentity, saveOfflineIdentity } from "../offline/storage";

type ApiServerChangeResult = {
  baseUrl: string;
  changed: boolean;
  remoteLogoutConfirmed: boolean;
};

type AuthContextValue = {
  user: MobileIdentity | null;
  loading: boolean;
  restoreError: string | null;
  isOffline: boolean;
  lastVerifiedAt: number | null;
  offlineStorageError: string | null;
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
  const [isOffline, setIsOffline] = useState(false);
  const [lastVerifiedAt, setLastVerifiedAt] = useState<number | null>(null);
  const [offlineStorageError, setOfflineStorageError] = useState<string | null>(null);
  const [signingIn, setSigningIn] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);
  const [mfaType, setMfaType] = useState<"totp" | "sms" | null>(null);
  const [mfaDestinationHint, setMfaDestinationHint] = useState<string | null>(null);

  const persistVerifiedIdentity = useCallback(async (identity: MobileIdentity) => {
    try {
      await saveOfflineIdentity(identity, await getSelectedApiBaseUrl());
      setOfflineStorageError(null);
    } catch {
      setOfflineStorageError(
        "Secure offline storage could not be prepared. AFCON360 remains available while online."
      );
    }
  }, []);

  const retryRestoreSession = useCallback(async () => {
    setLoading(true);
    setRestoreError(null);
    try {
      const restored = await authClient.restoreSession();
      authClient.setOfflineReadOnly(false);
      setUser(restored);
      setIsOffline(false);
      setLastVerifiedAt(restored ? Date.now() : null);
      if (restored) await persistVerifiedIdentity(restored);
    } catch (error) {
      const credentialsPresent = await authClient.hasStoredCredentials().catch(() => false);
      const transient = error instanceof MobileAuthError &&
        (error.status == null || error.status >= 500 || [408, 425, 429].includes(error.status));
      if (credentialsPresent && transient) {
        authClient.setOfflineReadOnly(true);
        try {
          const cached = await readOfflineIdentity(await getSelectedApiBaseUrl());
          if (cached) {
            setUser(cached.user);
            setIsOffline(true);
            setLastVerifiedAt(cached.lastVerifiedAt);
            setRestoreError(
              "Connection unavailable. Showing saved information until AFCON360 verifies your account again."
            );
          } else {
            setUser(null);
            setIsOffline(true);
            setLastVerifiedAt(null);
            setRestoreError(
              "Connection unavailable and no saved account snapshot exists. Reconnect to sign in."
            );
          }
        } catch {
          setUser(null);
          setIsOffline(true);
          setLastVerifiedAt(null);
          setOfflineStorageError(
            "Protected offline storage could not be opened. Reconnect to AFCON360 to continue."
          );
          setRestoreError(
            error instanceof Error ? error.message : "AFCON360 could not verify your saved session."
          );
        }
      } else {
        authClient.setOfflineReadOnly(false);
        setUser(null);
        setIsOffline(false);
        setLastVerifiedAt(null);
        setRestoreError(
          error instanceof Error ? error.message : "AFCON360 could not verify your saved session."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [persistVerifiedIdentity]);

  useEffect(() => {
    authClient.setOfflineStateListener(offline => {
      setIsOffline(offline);
      if (!offline) setRestoreError(null);
    });
    return () => authClient.setOfflineStateListener(null);
  }, []);

  useEffect(() => {
    void retryRestoreSession();
  }, [retryRestoreSession]);

  useEffect(() => {
    const subscription = AppState.addEventListener("change", state => {
      if (state === "active") void retryRestoreSession();
    });
    return () => subscription.remove();
  }, [retryRestoreSession]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    restoreError,
    isOffline,
    lastVerifiedAt,
    offlineStorageError,
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
        authClient.setOfflineReadOnly(false);
        setUser(result.user);
        setIsOffline(false);
        setLastVerifiedAt(Date.now());
        await persistVerifiedIdentity(result.user);
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
        authClient.setOfflineReadOnly(false);
        setUser(identity);
        setIsOffline(false);
        setLastVerifiedAt(Date.now());
        await persistVerifiedIdentity(identity);
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
        await clearAllOfflineData().catch(() => undefined);
        authClient.setOfflineReadOnly(false);
        setUser(null);
        setIsOffline(false);
        setLastVerifiedAt(null);
        setOfflineStorageError(null);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
        setRestoreError(null);
      }
      return result;
    },
    async logout() {
      const accountId = user?.public_id;
      setRestoreError(null);
      try { await authClient.logout(); } finally {
        if (accountId) {
          try {
            await clearOfflineAccount(accountId, await getSelectedApiBaseUrl());
          } catch {
            await clearAllOfflineData().catch(() => undefined);
          }
        } else {
          await clearAllOfflineData().catch(() => undefined);
        }
        authClient.setOfflineReadOnly(false);
        setUser(null);
        setIsOffline(false);
        setLastVerifiedAt(null);
        setOfflineStorageError(null);
        setMfaChallenge(null);
        setMfaType(null);
        setMfaDestinationHint(null);
      }
    },
    async deleteAccount(password, confirmation, mfaCode) {
      setRestoreError(null);
      await authClient.deleteAccount(password, confirmation, mfaCode);
      await clearAllOfflineData().catch(() => undefined);
      authClient.setOfflineReadOnly(false);
      setUser(null);
      setIsOffline(false);
      setLastVerifiedAt(null);
      setOfflineStorageError(null);
      setMfaChallenge(null);
      setMfaType(null);
      setMfaDestinationHint(null);
    }
  }), [user, loading, restoreError, isOffline, lastVerifiedAt, offlineStorageError, retryRestoreSession, signingIn, mfaChallenge, mfaType, mfaDestinationHint, persistVerifiedIdentity]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
