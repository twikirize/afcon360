import React, { useEffect, useState } from "react";
import { Alert, Text, View } from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { AppScreen, PageHeader, Panel, StatusPill, palette } from "@afcon360/mobile-ui";
import { AuthField, AuthLink, AuthNotice, AuthPasswordField, AuthShell, AuthSubmit } from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "../src/auth/AuthProvider";
import { SERVER_SELECTION_ENABLED } from "../src/services/api";

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
    Alert.alert(
      "Sign-in unsuccessful",
      error instanceof MobileAuthError
        ? error.message
        : "AFCON360 could not sign you in. Check your connection and try again."
    );
  };

  return (
    <AppScreen>
      <AuthShell>
        <View style={{ gap: 9 }}>
          <StatusPill tone="gold">AFCON360 Driver</StatusPill>
          <PageHeader
            eyebrow="Driver access"
            title={mfaChallenge ? "Verify it’s you." : "Welcome to your driving workspace."}
            description={
              mfaChallenge
                ? (mfaType === "sms"
                    ? `We sent a sign-in code to ${mfaDestinationHint ?? "your verified phone"}. It expires in five minutes.`
                    : "Enter the current code from your authenticator app to finish signing in.")
                : "Use your approved AFCON360 driver account. Driver eligibility is rechecked by the platform."
            }
          />
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
              <AuthNotice>
                {mfaType === "sms"
                  ? "Enter the 6-digit code sent to your verified phone. It can only be used once; never share it."
                  : "This authenticator challenge expires shortly and can only be used once. Never share your code."}
              </AuthNotice>
              <AuthField
                label={mfaType === "sms" ? "SMS verification code" : "Authenticator code"}
                value={code}
                onChangeText={setCode}
                keyboardType={mfaType === "sms" ? "number-pad" : "default"}
                autoCapitalize="characters"
                autoCorrect={false}
                autoComplete="one-time-code"
                maxLength={mfaType === "sms" ? 6 : 8}
                placeholder={mfaType === "sms" ? "6-digit text message code" : "6-digit code or backup code"}
              />
              <AuthSubmit
                label="Verify and continue"
                loading={signingIn}
                disabled={code.trim().length < 6}
                onPress={() => verifyMfa(code).then(() => router.replace("/(tabs)")).catch(showError)}
              />
              <AuthLink
                label="Use a different account"
                onPress={() => {
                  cancelMfa();
                  setCode("");
                  setPassword("");
                  setShowPassword(false);
                }}
              />
            </>
          ) : (
            <>
              <AuthField
                testID="driver-login-username"
                label="Username or email"
                value={identifier}
                onChangeText={setIdentifier}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                placeholder="Your AFCON360 username or email"
                returnKeyType="next"
              />
              <AuthPasswordField
                testID="driver-login-password"
                label="Password"
                value={password}
                onChangeText={setPassword}
                visible={showPassword}
                onToggle={() => setShowPassword(value => !value)}
                autoComplete="password"
                placeholder="Your password"
              />
              <AuthSubmit
                label="Sign in to Driver"
                loading={signingIn}
                disabled={!identifier.trim() || !password}
                onPress={() =>
                  signIn(identifier, password)
                    .then(needsMfa => {
                      if (!needsMfa) router.replace("/(tabs)");
                    })
                    .catch(showError)
                }
              />
              <AuthLink
                label="Continue driver registration on website"
                onPress={() => WebBrowser.openBrowserAsync(SITE + "/transport/become-driver")}
              />
              <AuthLink
                label="Forgot your password?"
                onPress={() => router.push("/forgot-password")}
              />
              {SERVER_SELECTION_ENABLED ? (
                <AuthLink
                  label="Connection settings (preview)"
                  onPress={() => router.push("/server-settings" as never)}
                />
              ) : null}
            </>
          )}
          <AuthLink
            label="Back to AFCON360 website home"
            onPress={() => WebBrowser.openBrowserAsync(SITE)}
          />
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          Driver go-live, vehicle, compliance and trip permissions are always checked by AFCON360 servers.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}
