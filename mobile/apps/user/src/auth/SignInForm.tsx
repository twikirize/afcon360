import React, { useState } from "react";
import { Alert } from "react-native";
import { useRouter } from "expo-router";
import { AuthField, AuthLink, AuthNotice, AuthPasswordField, AuthSubmit } from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "./AuthProvider";

/**
 * The sign-in form shared by the standalone /login route and the Account tab.
 * It performs no navigation on success: signing in changes auth state, and the
 * caller re-renders whatever a session unlocks. That keeps the form usable
 * wherever a session is required instead of bouncing the whole app to /login.
 */
export function SignInForm() {
  const router = useRouter();
  const { signingIn, mfaChallenge, mfaType, mfaDestinationHint, signIn, verifyMfa, cancelMfa } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState("");

  const showError = (error: unknown) => {
    Alert.alert("Sign-in unsuccessful", error instanceof MobileAuthError ? error.message : "AFCON360 could not sign you in. Check your connection and try again.");
  };

  if (mfaChallenge) {
    return (
      <>
        <AuthNotice>{mfaType === "sms" ? "Enter the 6-digit code sent to your verified phone. It can only be used once; never share it." : "This authenticator challenge expires shortly and can only be used once. Do not share your code."}</AuthNotice>
        <AuthField label={mfaType === "sms" ? "SMS verification code" : "Authenticator code"} value={code} onChangeText={setCode} keyboardType={mfaType === "sms" ? "number-pad" : "default"} autoCapitalize="characters" autoCorrect={false} autoComplete="one-time-code" maxLength={mfaType === "sms" ? 6 : 8} placeholder={mfaType === "sms" ? "6-digit text message code" : "6-digit code or backup code"} />
        <AuthSubmit label="Verify and continue" loading={signingIn} disabled={code.trim().length < 6} onPress={() => { void verifyMfa(code).catch(showError); }} />
        <AuthLink label="Use a different account" onPress={() => { cancelMfa(); setCode(""); setPassword(""); }} />
      </>
    );
  }

  return (
    <>
      <AuthField label="Username or email" value={identifier} onChangeText={setIdentifier} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" placeholder="Your AFCON360 username or email" returnKeyType="next" />
      <AuthPasswordField label="Password" value={password} onChangeText={setPassword} visible={showPassword} onToggle={() => setShowPassword(value => !value)} autoComplete="password" placeholder="Your password" />
      <AuthSubmit label="Sign in securely" loading={signingIn} disabled={!identifier.trim() || !password} onPress={() => { void signIn(identifier, password).catch(showError); }} />
      <AuthLink label="Create an AFCON360 account" onPress={() => router.push("/register")} />
      <AuthLink label="Forgot your password?" onPress={() => router.push("/forgot-password")} />
    </>
  );
}

export default SignInForm;
