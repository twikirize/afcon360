import React, { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { MobileAuthError, MobileIdentity } from "@afcon360/mobile-core";
import { authClient } from "../services/api";

type AuthContextValue = {
  user: MobileIdentity | null;
  loading: boolean;
  signingIn: boolean;
  mfaChallenge: string | null;
  signIn(identifier: string, password: string): Promise<void>;
  verifyMfa(code: string): Promise<void>;
  cancelMfa(): void;
  logout(): Promise<void>;
  deleteAccount(password: string, confirmation: string, mfaCode?: string): Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MobileIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    authClient.restoreSession()
      .then(value => { if (active) setUser(value); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    signingIn,
    mfaChallenge,
    async signIn(identifier, password) {
      setSigningIn(true);
      try {
        const result = await authClient.signIn(identifier, password);
        if (result.mfaRequired) {
          setMfaChallenge(result.challengeToken);
          return;
        }
        setUser(result.user);
        setMfaChallenge(null);
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
      } finally {
        setSigningIn(false);
      }
    },
    cancelMfa() { setMfaChallenge(null); },
    async logout() {
      try { await authClient.logout(); } finally { setUser(null); setMfaChallenge(null); }
    },
    async deleteAccount(password, confirmation, mfaCode) {
      await authClient.deleteAccount(password, confirmation, mfaCode);
      setUser(null);
      setMfaChallenge(null);
    }
  }), [user, loading, signingIn, mfaChallenge]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
