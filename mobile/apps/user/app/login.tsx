import React, { useEffect, useState } from "react";
import { Alert, Text, View } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, StatusPill, palette } from "@afcon360/mobile-ui";
import { AuthField, AuthLink, AuthNotice, AuthPasswordField, AuthShell, AuthSubmit } from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "../src/auth/AuthProvider";

const SITE = "https://www.pamoja.space";

export default function LoginScreen() {
  const router = useRouter();
  const { user, loading, restoreError, retryRestoreSession, signingIn, mfaChallenge, mfaType, mfaDestinationHint, signIn, verifyMfa, cancelMfa } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [code, setCode] = useState("");

  useEffect(() => {
    if (!loading && user) router.replace("/(tabs)");
  }, [loading, user, router]);

  const showError = (error: unknown) => {
    Alert.alert("Sign-in unsuccessful", error instanceof MobileAuthError ? error.message : "AFCON360 could not sign you in. Check your connection and try again.");
  };

  return (
    <AppScreen>
      <AuthShell>
        <View style={{ gap: 9 }}>
          <StatusPill>AFCON360 User</StatusPill>
          <PageHeader eyebrow="Welcome back" title={mfaChallenge ? "Verify it’s you." : "Your journey starts here."} description={mfaChallenge ? (mfaType === "sms" ? `We sent a sign-in code to ${mfaDestinationHint ?? "your verified phone"}. It expires in five minutes.` : "Enter the current code from your authenticator app to finish signing in.") : "Sign in with your existing AFCON360 account. Your website account works here too."} />
        </View>
        <Panel>
          {restoreError ? (
            <>
              <AuthNotice>{restoreError} Your saved credentials have not been deleted. Check your connection and retry the session check.</AuthNotice>
              <AuthLink label="Retry saved session" onPress={() => { void retryRestoreSession(); }} />
            </>
          ) : null}
          {mfaChallenge ? (
            <>
              <AuthNotice>{mfaType === "sms" ? "Enter the 6-digit code sent to your verified phone. It can only be used once; never share it." : "This authenticator challenge expires shortly and can only be used once. Do not share your code."}</AuthNotice>
              <AuthField label={mfaType === "sms" ? "SMS verification code" : "Authenticator code"} value={code} onChangeText={setCode} keyboardType={mfaType === "sms" ? "number-pad" : "default"} autoCapitalize="characters" autoCorrect={false} autoComplete="one-time-code" maxLength={mfaType === "sms" ? 6 : 8} placeholder={mfaType === "sms" ? "6-digit text message code" : "6-digit code or backup code"} />
              <AuthSubmit label="Verify and continue" loading={signingIn} disabled={code.trim().length < 6} onPress={() => verifyMfa(code).then(() => router.replace("/(tabs)")).catch(showError)} />
              <AuthLink label="Use a different account" onPress={() => { cancelMfa(); setCode(""); setPassword(""); }} />
            </>
          ) : (
            <>
              <AuthField label="Username or email" value={identifier} onChangeText={setIdentifier} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" placeholder="Your AFCON360 username or email" returnKeyType="next" />
              <AuthPasswordField label="Password" value={password} onChangeText={setPassword} visible={showPassword} onToggle={() => setShowPassword(value => !value)} autoComplete="password" placeholder="Your password" />
              <AuthSubmit label="Sign in securely" loading={signingIn} disabled={!identifier.trim() || !password} onPress={() => signIn(identifier, password).then(needsMfa => { if (!needsMfa) router.replace("/(tabs)"); }).catch(showError)} />
              <AuthLink label="Create an AFCON360 account" onPress={() => router.push("/register")} />
              <AuthLink label="Forgot your password?" onPress={() => router.push("/forgot-password")} />
            </>
          )}
          <AuthLink label="Back to AFCON360 website home" onPress={() => WebBrowser.openBrowserAsync(SITE)} />
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>Protected by AFCON360 Identity. Your password and authenticator codes are sent only over HTTPS and are never stored on this device.</Text>
      </AuthShell>
    </AppScreen>
  );
}
