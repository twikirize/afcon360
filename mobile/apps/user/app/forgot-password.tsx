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
import { authClient } from "../src/services/api";

export default function ForgotPasswordScreen() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const requestCode = async () => {
    if (!identifier.trim()) {
      setError("Enter your AFCON360 username or email address.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await authClient.requestPasswordReset(identifier);
      setNotice(result.message);
      setCode("");
      setStep("confirm");
    } catch (value) {
      setError(value instanceof Error ? value.message : "AFCON360 could not request a reset code.");
    } finally {
      setLoading(false);
    }
  };

  const submitNewPassword = async () => {
    if (code.trim().length !== 6) {
      setError("Enter the six-digit code sent to your registered email address.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const message = await authClient.confirmPasswordReset(
        identifier,
        code,
        newPassword,
        confirmPassword
      );
      Alert.alert("Password reset", message, [
        { text: "Back to sign in", onPress: () => router.replace("/login") }
      ]);
    } catch (value) {
      setError(value instanceof Error ? value.message : "AFCON360 could not reset the password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppScreen>
      <AuthShell>
        <View style={{ gap: 9 }}>
          <StatusPill>AFCON360 User</StatusPill>
          <PageHeader
            eyebrow="Account recovery"
            title={step === "request" ? "Reset your password." : "Choose a new password."}
            description="We will keep you in this app while you verify your email and choose a new password."
          />
        </View>
        <Panel>
          {step === "request" ? (
            <>
              <AuthNotice>
                Enter the username or email on your AFCON360 account. If it has a registered email address, we will send a six-digit code that expires in 10 minutes.
              </AuthNotice>
              <AuthField
                label="Username or email"
                value={identifier}
                onChangeText={setIdentifier}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                autoComplete="email"
                placeholder="Your AFCON360 username or email"
              />
              {error ? <AuthNotice>{error}</AuthNotice> : null}
              <AuthSubmit
                label="Send reset code"
                loading={loading}
                disabled={!identifier.trim()}
                onPress={() => { void requestCode(); }}
              />
            </>
          ) : (
            <>
              <AuthNotice>{notice || "Enter the six-digit code sent to your registered email address."}</AuthNotice>
              <AuthField
                label="Username or email"
                value={identifier}
                onChangeText={setIdentifier}
                editable={false}
                autoCapitalize="none"
              />
              <AuthField
                label="Six-digit email code"
                value={code}
                onChangeText={value => setCode(value.replace(/\D/g, "").slice(0, 6))}
                keyboardType="number-pad"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="123456"
              />
              <AuthPasswordField
                label="New password"
                value={newPassword}
                onChangeText={setNewPassword}
                visible={showPassword}
                onToggle={() => setShowPassword(value => !value)}
                autoComplete="new-password"
                placeholder="At least 10 characters"
              />
              <AuthPasswordField
                label="Confirm new password"
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                visible={showConfirmation}
                onToggle={() => setShowConfirmation(value => !value)}
                autoComplete="new-password"
                placeholder="Enter the new password again"
              />
              {error ? <AuthNotice>{error}</AuthNotice> : null}
              <AuthSubmit
                label="Reset password securely"
                loading={loading}
                disabled={code.length !== 6 || !newPassword || !confirmPassword}
                onPress={() => { void submitNewPassword(); }}
              />
              <AuthLink label="Send a new code" onPress={() => { void requestCode(); }} />
              <AuthLink
                label="Use a different account"
                onPress={() => {
                  setStep("request");
                  setCode("");
                  setNewPassword("");
                  setConfirmPassword("");
                  setError(null);
                  setNotice(null);
                }}
              />
            </>
          )}
          <AuthLink label="Back to sign in" onPress={() => router.replace("/login")} />
        </Panel>
        <Text style={{ color: palette.muted, fontSize: 12, lineHeight: 18, textAlign: "center" }}>
          AFCON360 User uses AFCON360 Identity. Reset codes are one-time credentials and must never be shared with anyone.
        </Text>
      </AuthShell>
    </AppScreen>
  );
}
