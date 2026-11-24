import React from "react";
import { Pressable, Text, TextInput, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../../theme/tokens";

export function WalletButton({
  label,
  onPress,
  disabled = false,
  secondary = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.button,
        secondary && styles.buttonSecondary,
        disabled && styles.buttonDisabled,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Text style={[styles.buttonText, secondary && styles.buttonTextSecondary]}>{label}</Text>
    </Pressable>
  );
}

export function WalletField({
  label,
  value,
  onChangeText,
  placeholder,
  secureTextEntry = false,
  keyboardType = "default",
  autoCapitalize = "none",
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  secureTextEntry?: boolean;
  keyboardType?: "default" | "numeric" | "decimal-pad" | "email-address" | "phone-pad";
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.text.muted}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        style={styles.input}
      />
    </View>
  );
}

export function WalletTabButton({
  key,
  label,
  active,
  onPress,
}: {
  key: string;
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      key={key}
      onPress={onPress}
      style={[
        styles.tabButton,
        active && styles.tabButtonActive,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Text style={[styles.tabButtonText, active && styles.tabButtonTextActive]}>{label}</Text>
    </Pressable>
  );
}

export function WalletAccountCard({
  account,
  selected,
  onPress,
}: {
  account: { currency: string; balance: string; is_frozen: boolean };
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.accountCard,
        selected && styles.accountCardSelected,
      ]}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={styles.accountHeader}>
        <Text style={[styles.accountCurrency, selected && styles.accountCurrencySelected]}>{account.currency}</Text>
        <View style={styles.statusPill}>
          <Text style={styles.statusPillText}>{account.is_frozen ? "Restricted" : "Active"}</Text>
        </View>
      </View>
      <Text style={[styles.accountBalance, selected && styles.accountBalanceSelected]}>
        {account.balance} {account.currency}
      </Text>
      <Text style={[styles.accountFootnote, selected && styles.accountFootnoteSelected]}>
        Balance read directly from the Wallet ledger
      </Text>
    </Pressable>
  );
}

export function WalletTransactionItem({ item }: {
  item: { reference: string; direction: string; type: string; amount: string; currency: string; status: string; created_at: string | null };
}) {
  return (
    <View style={styles.transactionItem}>
      <View style={styles.transactionHeader}>
        <Text style={styles.transactionType}>
          {item.direction === "received" ? "Received" : item.type}
        </Text>
        <Text style={styles.transactionAmount}>
          {item.direction === "received" ? "+" : "−"}{item.amount} {item.currency}
        </Text>
      </View>
      <Text style={styles.transactionMeta}>
        {item.status} · {formatDate(item.created_at)}
      </Text>
      <Text style={styles.transactionRef}>Ref: {item.reference}</Text>
    </View>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

const styles = StyleSheet.create({
  button: {
    minHeight: 48,
    backgroundColor: colors.brand.green,
    borderRadius: radii.md,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  buttonSecondary: { backgroundColor: colors.brand.greenSoft },
  buttonDisabled: { opacity: 0.45 },
  buttonText: { color: colors.surface.white, fontSize: 13, fontWeight: "800" },
  buttonTextSecondary: { color: colors.brand.green },
  field: { gap: spacing.xs },
  fieldLabel: { color: colors.text.ink, fontWeight: "700", fontSize: 13 },
  input: {
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    color: colors.text.ink,
    fontSize: 15,
  },
  tabButton: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radii.sm,
  },
  tabButtonActive: { backgroundColor: colors.brand.green },
  tabButtonText: { color: colors.text.ink, fontWeight: "800", fontSize: 12 },
  tabButtonTextActive: { color: colors.surface.white },
  accountCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    marginTop: spacing.sm,
    gap: spacing.sm,
    backgroundColor: colors.surface.white,
  },
  accountCardSelected: {
    borderColor: colors.brand.green,
    borderWidth: 2,
    backgroundColor: colors.brand.dark,
  },
  accountHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  accountCurrency: { color: colors.text.ink, fontWeight: "900" },
  accountCurrencySelected: { color: colors.surface.white },
  statusPill: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radii.pill },
  statusPillText: { fontSize: 10, fontWeight: "900" },
  accountBalance: { color: colors.text.ink, fontSize: 25, fontWeight: "900" },
  accountBalanceSelected: { color: colors.brand.gold },
  accountFootnote: { color: colors.text.muted, fontSize: 12 },
  accountFootnoteSelected: { color: "rgba(255,255,255,0.78)" },
  transactionItem: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.md, gap: spacing.xs },
  transactionHeader: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  transactionType: { color: colors.text.ink, fontWeight: "800", textTransform: "capitalize" },
  transactionAmount: { color: colors.text.ink, fontWeight: "900" },
  transactionMeta: { color: colors.text.muted, fontSize: 11 },
  transactionRef: { color: colors.text.muted, fontSize: 10 },
});

