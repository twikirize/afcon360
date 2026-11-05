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

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [codeRequested, setCodeRequested] = useState(false);
  const [busy, setBusy] = useState(false);

  const showError = (error: unknown, title: string) => {
    Alert.alert(
      title,
      error instanceof MobileAuthError
        ? error.message
        : "AFCON360 could not complete this request. Check your connection and try again."
    );
  };

  const requestCode = async () => {
    const value = identifier.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      await authClient.requestPasswordReset(value);
      setCodeRequested(true);
    } catch (error) {
      showError(error, "Could not request a reset code");
    } finally {
      setBusy(false);
    }
  };

  const confirmReset = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await authClient.confirmPasswordReset(
        identifier,
        code,
        newPassword,
        confirmPassword
      );
      Alert.alert(
        "Password updated",
        "Your AFCON360 password has been reset. Sign in with your new password.",
        [{ text: "Back to sign in", onPress: () => router.replace("/login") }]
      );
    } catch (error) {
      showError(error, "Password reset unsuccessful");
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
            eyebrow="Account recovery"
            title={codeRequested ? "Enter your reset code." : "Reset your password."}
            description={
              codeRequested
                ? "Use the six-digit code sent to your registered email address, then choose a new password."
                : "Request a one-time code using the username or email address on your AFCON360 account."
            }
          />
        </View>
        <Panel>
          {!codeRequested ? (
            <>
              <AuthNotice>
                For security, AFCON360 gives the same confirmation whether or not an account matches the details entered.
              </AuthNotice>
              <AuthField
                label="Username or email"
                value={identifier}
                onChangeText={setIdentifier}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                autoComplete="username"
                placeholder="Your AFCON360 username or email"
                returnKeyType="send"
              />
              <AuthSubmit
                label="Send reset code"
                loading={busy}
                disabled={!identifier.trim()}
                onPress={() => { void requestCode(); }}
              />
            </>
          ) : (
            <>
              <AuthNotice>
                If an active account has a registered email address, a code has been sent. The code expires in 10 minutes and can only be used once.
              </AuthNotice>
              <AuthField
                label="Username or email"
                value={identifier}
                onChangeText={setIdentifier}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                autoComplete="username"
                editable={false}
              />
              <AuthField
                label="Six-digit email code"
                value={code}
                onChangeText={setCode}
                keyboardType="number-pad"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="Enter the code from your email"
              />
              <AuthPasswordField
                label="New password"
                value={newPassword}
                onChangeText={setNewPassword}
                visible={showPassword}
                onToggle={() => setShowPassword(value => !value)}
                autoComplete="new-password"
                placeholder="Create a new password"
              />
              <AuthPasswordField
                label="Confirm new password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                visible={showPassword}
                onToggle={() => setShowPassword(value => !value)}
                autoComplete="new-password"
                placeholder="Enter the new password again"
              />
              <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18 }}>
                Use at least 10 characters and include at least three of these: uppercase, lowercase, number and symbol.
              </Text>
              <AuthSubmit
                label="Save new password"
                loading={busy}
                disabled={
                  code.trim().length !== 6 ||
                  !newPassword ||
                  !confirmPassword
                }
                onPress={() => { void confirmReset(); }}
              />
              <AuthLink
                label="Use a different username or email"
                onPress={() => {
                  setCodeRequested(false);
                  setCode("");
                  setNewPassword("");
                  setConfirmPassword("");
                }}
              />
            </>
          )}
          <AuthLink label="Back to sign in" onPress={() => router.replace("/login")} />
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          AFCON360 will never ask you to share your reset code with another person.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}
