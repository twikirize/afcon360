import React, { ReactNode, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View
} from "react-native";
import { PageHeader, Panel, StatusPill, palette } from "./index";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.inner}>{children}</View>
    </KeyboardAvoidingView>
  );
}

export function AuthField(props: TextInputProps & { label: string }) {
  const { label, ...inputProps } = props;
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        {...inputProps}
        accessibilityLabel={label}
        placeholderTextColor={palette.muted}
        style={[styles.input, inputProps.style]}
      />
    </View>
  );
}

export function AuthPasswordField({
  label,
  visible,
  onToggle,
  ...inputProps
}: TextInputProps & {
  label: string;
  visible: boolean;
  onToggle(): void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.passwordWrap}>
        <TextInput
          {...inputProps}
          accessibilityLabel={label}
          placeholderTextColor={palette.muted}
          secureTextEntry={!visible}
          style={[styles.input, styles.passwordInput, inputProps.style]}
        />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={visible ? "Hide password" : "Show password"}
          accessibilityState={{ selected: visible }}
          hitSlop={10}
          onPress={onToggle}
          style={styles.passwordToggle}
        >
          <Text style={styles.passwordToggleText}>{visible ? "Hide" : "Show"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

export function AuthSubmit({
  label,
  loading,
  disabled,
  onPress
}: {
  label: string;
  loading?: boolean;
  disabled?: boolean;
  onPress(): void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ busy: !!loading, disabled: !!disabled || !!loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [styles.submit, (disabled || loading) && styles.disabled, pressed && styles.pressed]}
    >
      {loading ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.submitText}>{label}</Text>}
    </Pressable>
  );
}

export function AuthLink({ label, onPress }: { label: string; onPress(): void }) {
  return <Pressable accessibilityRole="link" onPress={onPress} style={styles.link}><Text style={styles.linkText}>{label}</Text></Pressable>;
}

export function AuthNotice({ children }: { children: ReactNode }) {
  return <View style={styles.notice}><Text style={styles.noticeText}>{children}</Text></View>;
}


export type PasswordResetFlowProps = {
  appLabel: string;
  onRequestCode(identifier: string): Promise<{ message: string; expiresIn: number }>;
  onConfirmCode(input: {
    identifier: string;
    code: string;
    newPassword: string;
    confirmPassword: string;
  }): Promise<string>;
  onBack(): void;
  onComplete(): void;
};

export function PasswordResetFlow({
  appLabel,
  onRequestCode,
  onConfirmCode,
  onBack,
  onComplete
}: PasswordResetFlowProps) {
  const [step, setStep] = useState<"request" | "confirm">("request");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);

  const requestCode = async () => {
    const normalized = identifier.trim();
    if (!normalized) {
      setError("Enter your AFCON360 username or email address.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await onRequestCode(normalized);
      setMessage(result.message);
      setCode("");
      setStep("confirm");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AFCON360 could not send a reset code. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const confirmReset = async () => {
    if (!/^\d{6}$/.test(code.trim())) {
      setError("Enter the 6-digit code sent to your registered email address.");
      return;
    }
    if (newPassword.length < 10) {
      setError("Your new password must be at least 10 characters long.");
      return;
    }
    const categories = [
      /[A-Z]/.test(newPassword),
      /[a-z]/.test(newPassword),
      /\d/.test(newPassword),
      /[^A-Za-z0-9]/.test(newPassword)
    ].filter(Boolean).length;
    if (categories < 3) {
      setError("Use at least three of these: uppercase, lowercase, number and symbol.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The two passwords do not match.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const result = await onConfirmCode({
        identifier: identifier.trim(),
        code: code.trim(),
        newPassword,
        confirmPassword
      });
      setMessage(result);
      setComplete(true);
      setNewPassword("");
      setConfirmPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "AFCON360 could not reset your password. Check the code and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell>
      <View style={{ gap: 9 }}>
        <StatusPill>{appLabel}</StatusPill>
        <PageHeader
          eyebrow="Account recovery"
          title={complete ? "Password updated." : step === "request" ? "Reset your password." : "Choose a new password."}
          description={
            complete
              ? "Your previous sign-in sessions have been revoked. Sign in again with your new password."
              : step === "request"
                ? "We will send a one-time code to the email address registered to your AFCON360 account."
                : "Enter the 6-digit code from your email and choose a new password."
          }
        />
      </View>
      <Panel>
        {!complete && step === "request" ? (
          <>
            <AuthNotice>
              Enter the username or email address for your AFCON360 account. For privacy, the app gives the same response whether or not an account matches.
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
              editable={!busy}
              returnKeyType="done"
              onSubmitEditing={() => { void requestCode(); }}
            />
            {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
            <AuthSubmit
              label="Send reset code"
              loading={busy}
              disabled={!identifier.trim()}
              onPress={() => { void requestCode(); }}
            />
          </>
        ) : null}

        {!complete && step === "confirm" ? (
          <>
            <AuthNotice>{message || "If an active account has a registered email address, a reset code has been sent."}</AuthNotice>
            <AuthField
              label="Account username or email"
              value={identifier}
              editable={false}
              autoCapitalize="none"
            />
            <AuthField
              label="6-digit email code"
              value={code}
              onChangeText={value => setCode(value.replace(/[^0-9]/g, "").slice(0, 6))}
              keyboardType="number-pad"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="Enter the code from your email"
              editable={!busy}
            />
            <AuthPasswordField
              label="New password"
              value={newPassword}
              onChangeText={setNewPassword}
              visible={showNewPassword}
              onToggle={() => setShowNewPassword(value => !value)}
              autoComplete="new-password"
              placeholder="At least 10 characters"
              editable={!busy}
            />
            <AuthPasswordField
              label="Confirm new password"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              visible={showConfirmPassword}
              onToggle={() => setShowConfirmPassword(value => !value)}
              autoComplete="new-password"
              placeholder="Enter the new password again"
              editable={!busy}
            />
            <Text style={styles.helpText}>Use at least 10 characters and include at least three of: uppercase, lowercase, number and symbol.</Text>
            {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
            <AuthSubmit
              label="Reset password"
              loading={busy}
              disabled={!identifier.trim() || code.trim().length !== 6 || !newPassword || !confirmPassword}
              onPress={() => { void confirmReset(); }}
            />
            <AuthLink
              label="Send another code"
              onPress={() => { void requestCode(); }}
            />
          </>
        ) : null}

        {complete ? (
          <>
            <AuthNotice>{message}</AuthNotice>
            <AuthSubmit label="Return to sign in" onPress={onComplete} />
          </>
        ) : null}
        <AuthLink label="Back to sign in" onPress={onBack} />
      </Panel>
    </AuthShell>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: "center", backgroundColor: palette.canvas },
  inner: { width: "100%", maxWidth: 520, alignSelf: "center", padding: 22, gap: 18 },
  field: { gap: 7 },
  label: { color: palette.ink, fontSize: 13, fontWeight: "800" },
  input: {
    minHeight: 52, borderWidth: 1, borderColor: palette.border, borderRadius: 13,
    backgroundColor: palette.surface, paddingHorizontal: 14, color: palette.ink, fontSize: 15
  },
  passwordWrap: { position: "relative", justifyContent: "center" },
  passwordInput: { paddingRight: 76 },
  passwordToggle: { position: "absolute", right: 13, minHeight: 42, justifyContent: "center", paddingHorizontal: 5 },
  passwordToggleText: { color: palette.greenDark, fontSize: 13, fontWeight: "800" },
  submit: { minHeight: 52, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: palette.green, paddingHorizontal: 18 },
  disabled: { backgroundColor: "#9AA9A0" },
  pressed: { opacity: 0.85 },
  submitText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  link: { paddingVertical: 7, alignSelf: "flex-start" },
  linkText: { color: palette.greenDark, fontSize: 13, fontWeight: "800" },
  notice: { padding: 13, borderRadius: 13, backgroundColor: palette.warningSoft },
  noticeText: { color: palette.ink, fontSize: 13, lineHeight: 19 },
  helpText: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  error: { color: "#B42318", fontSize: 12, lineHeight: 18 }
});
