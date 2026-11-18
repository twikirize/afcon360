import React, { useState } from "react";
import { Alert, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { AppScreen, PageHeader, Panel, StatusPill, palette } from "@afcon360/mobile-ui";
import {
  AuthField,
  AuthLink,
  AuthNotice,
  AuthPasswordField,
  AuthShell,
  AuthSubmit
} from "@afcon360/mobile-ui/auth";
import { MobileAuthError } from "@afcon360/mobile-core";
import { authClient } from "../src/services/api";

export default function RegisterScreen() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [registrationToken, setRegistrationToken] = useState<string | null>(null);
  const [verificationEmail, setVerificationEmail] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const errorMessage = (error: unknown) =>
    error instanceof MobileAuthError
      ? error.message
      : "AFCON360 could not complete account creation. Check your connection and try again.";

  const createAccount = async () => {
    if (!username.trim() || !email.trim() || !password) {
      Alert.alert("Complete the form", "Enter a username, email address and password.");
      return;
    }
    setBusy(true);
    try {
      const result = await authClient.register({
        username: username.trim(),
        email: email.trim(),
        password
      });
      if (result.verificationRequired && result.registrationToken) {
        setRegistrationToken(result.registrationToken);
        setVerificationEmail(result.email);
        setNotice(result.message);
        return;
      }
      Alert.alert(
        "Account created",
        result.message || "Your AFCON360 account has been created. You can now sign in.",
        [{ text: "Continue to sign in", onPress: () => router.replace("/login") }]
      );
    } catch (error) {
      Alert.alert("Account creation unsuccessful", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const verifyEmail = async () => {
    if (!registrationToken || verificationCode.trim().length !== 6) {
      Alert.alert("Enter your code", "Enter the 6-digit code sent to your email address.");
      return;
    }
    setBusy(true);
    try {
      const message = await authClient.verifyRegistration(registrationToken, verificationCode);
      setRegistrationToken(null);
      setVerificationCode("");
      Alert.alert("Email verified", message, [
        { text: "Continue to sign in", onPress: () => router.replace("/login") }
      ]);
    } catch (error) {
      Alert.alert("Verification unsuccessful", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const resendCode = async () => {
    if (!registrationToken) return;
    setBusy(true);
    try {
      setNotice(await authClient.resendRegistrationCode(registrationToken));
    } catch (error) {
      Alert.alert("Could not resend code", errorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppScreen>
      <AuthShell>
        <View style={{ gap: 9 }}>
          <StatusPill>AFCON360 User</StatusPill>
          <PageHeader
            eyebrow="Create your account"
            title={registrationToken ? "Verify your email." : "Join AFCON360."}
            description={
              registrationToken
                ? "Enter the code sent to your email address to finish creating your account."
                : "Create one AFCON360 account for your journeys, wallet and activities."
            }
          />
        </View>
        <Panel>
          {registrationToken ? (
            <>
              <AuthNotice>
                {notice || `We sent a 6-digit verification code to ${verificationEmail}.`}
              </AuthNotice>
              <AuthField
                label="Email verification code"
                value={verificationCode}
                onChangeText={value => setVerificationCode(value.replace(/\D/g, "").slice(0, 6))}
                keyboardType="number-pad"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="Enter the 6-digit code"
              />
              <AuthSubmit
                label="Verify email and continue"
                loading={busy}
                disabled={verificationCode.trim().length !== 6}
                onPress={() => { void verifyEmail(); }}
              />
              <AuthLink label="Resend verification code" onPress={() => { void resendCode(); }} />
              <AuthLink
                label="Use a different email"
                onPress={() => {
                  setRegistrationToken(null);
                  setVerificationCode("");
                  setNotice("");
                }}
              />
            </>
          ) : (
            <>
              <AuthField
                label="Username"
                value={username}
                onChangeText={setUsername}
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="Choose a username"
                maxLength={30}
                returnKeyType="next"
              />
              <AuthField
                label="Email address"
                value={email}
                onChangeText={setEmail}
                keyboardType="email-address"
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                placeholder="you@example.com"
                returnKeyType="next"
              />
              <AuthPasswordField
                label="Password"
                value={password}
                onChangeText={setPassword}
                visible={showPassword}
                onToggle={() => setShowPassword(value => !value)}
                autoComplete="new-password"
                placeholder="Create a strong password"
                maxLength={128}
              />
              <AuthNotice>
                Use at least 10 characters and include at least 3 of these: uppercase letters, lowercase letters, numbers and symbols.
              </AuthNotice>
              <AuthSubmit
                label="Create account"
                loading={busy}
                disabled={!username.trim() || !email.trim() || !password}
                onPress={() => { void createAccount(); }}
              />
              <AuthLink label="Already have an account? Sign in" onPress={() => router.replace("/login")} />
            </>
          )}
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          Your password is sent only to AFCON360 over HTTPS. It is not stored on this device.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}
