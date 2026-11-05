import React, { useEffect, useState } from "react";
import { Alert, Text, View } from "react-native";
import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { AppScreen, PageHeader, Panel, StatusPill, palette } from "@afcon360/mobile-ui";
import { AuthField, AuthLink, AuthNotice, AuthPasswordField, AuthShell, AuthSubmit } from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { useAuth } from "../src/auth/AuthProvider";

const SITE = "https://www.pamoja.space";

export default function LoginScreen() {
  const router = useRouter();
  const { user, loading, signingIn, mfaChallenge, signIn, verifyMfa, cancelMfa } = useAuth();
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
                ? "Enter the current code from your authenticator app to finish signing in."
                : "Use your approved AFCON360 driver account. Driver eligibility is rechecked by the platform."
            }
          />
        </View>
        <Panel>
          {mfaChallenge ? (
            <>
              <AuthNotice>
                This sign-in challenge expires shortly and can only be used once. Never share your authenticator code.
              </AuthNotice>
              <AuthField
                label="Authenticator code"
                value={code}
                onChangeText={setCode}
                keyboardType="default"
                autoCapitalize="characters"
                autoCorrect={false}
                autoComplete="one-time-code"
                maxLength={8}
                placeholder="6-digit code or backup code"
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
                label="Driver registration and verification"
                onPress={() => WebBrowser.openBrowserAsync(SITE + "/transport/become-driver")}
              />
              <AuthLink
                label="Forgot your password?"
                onPress={() => WebBrowser.openBrowserAsync(SITE + "/reset/request")}
              />
            </>
          )}
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          Driver go-live, vehicle, compliance and trip permissions are always checked by AFCON360 servers.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}
