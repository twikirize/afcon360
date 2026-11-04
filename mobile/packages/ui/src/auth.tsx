import React, { ReactNode } from "react";
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
import { palette } from "./index";

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
  noticeText: { color: palette.ink, fontSize: 13, lineHeight: 19 }
});
