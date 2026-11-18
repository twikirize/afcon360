import React from "react";
import { Text, View, Alert, Linking } from "react-native";
import { colors, spacing, radii } from "../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../PamojaScreen";
import {
  WalletField,
  WalletButton,
} from "./WalletUI";
import { formatDate, formatMoney } from "./types";

type WalletDepositProps = {
  selectedCurrency: string;
  selectedAccount: { currency: string; is_frozen: boolean } | undefined;
  depositAmount: string;
  depositPaymentMethod: "mobilemoney" | "card";
  depositReference: string | null;
  depositCheckoutUrl: string | null;
  depositStatus: { reference: string; status: string; amount: string; currency: string; payment_provider: string; message: string | null } | null;
  busy: boolean;
  error: string | null;
  notice: string | null;
  onAmountChange: (value: string) => void;
  onPaymentMethodChange: (method: "mobilemoney" | "card") => void;
  onStartDeposit: () => void;
  onRefreshDeposit: () => void;
  onOpenCheckout: () => void;
};

export function WalletDeposit({
  selectedCurrency,
  selectedAccount,
  depositAmount,
  depositPaymentMethod,
  depositReference,
  depositCheckoutUrl,
  depositStatus,
  busy,
  error,
  notice,
  onAmountChange,
  onPaymentMethodChange,
  onStartDeposit,
  onRefreshDeposit,
  onOpenCheckout,
}: WalletDepositProps) {
  return (
    <Panel>
      <SectionTitle>Deposit to your AFCON360 Wallet</SectionTitle>
      <Text style={{ color: colors.text.muted, lineHeight: 19 }}>
        The amount and currency are sent to the AFCON360 server and Flutterwave. The app does not credit your balance. Provider verification is required first.
      </Text>
      <Text style={{ color: colors.text.ink, fontWeight: "800" }}>Wallet currency: {selectedCurrency}</Text>
      <WalletField
        label="Amount"
        value={depositAmount}
        onChangeText={onAmountChange}
        placeholder="0.00"
        keyboardType="decimal-pad"
      />
      <Text style={{ color: colors.text.ink, fontWeight: "700", fontSize: 13 }}>Payment method</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {(["mobilemoney", "card"] as const).map((method) => (
          <Pressable
            key={method}
            onPress={() => onPaymentMethodChange(method)}
            style={{
              backgroundColor: depositPaymentMethod === method ? colors.brand.green : "#EEF3F0",
              borderRadius: radii.sm,
              paddingVertical: 10,
              paddingHorizontal: 14,
            }}
            hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          >
            <Text style={{ color: depositPaymentMethod === method ? "#FFFFFF" : colors.text.ink, fontWeight: "800" }}>
              {method === "mobilemoney" ? "Mobile money" : "Bank card"}
            </Text>
          </Pressable>
        ))}
      </View>
      <WalletButton
        label={busy ? "Starting secure checkout…" : "Continue to Flutterwave"}
        onPress={onStartDeposit}
        disabled={busy || !depositAmount.trim() || !selectedAccount || selectedAccount.is_frozen || !!depositReference}
      />
      {depositStatus ? (
        <View style={{ backgroundColor: "#F1F6F2", borderRadius: 12, padding: 14, gap: 8 }}>
          <StatusPill tone={depositStatus.status === "completed" ? "green" : depositStatus.status === "failed" ? "gold" : "gold"}>
            Deposit {depositStatus.status}
          </StatusPill>
          <Text style={{ color: colors.text.ink, fontWeight: "900" }}>
            {formatMoney(Number(depositStatus.amount), depositStatus.currency)}
          </Text>
          <Text style={{ color: colors.text.muted, fontSize: 11 }}>Reference: {depositStatus.reference}</Text>
          {depositStatus.status === "pending" && depositCheckoutUrl ? (
            <WalletButton label="Open Flutterwave checkout" onPress={onOpenCheckout} secondary />
          ) : null}
          {depositStatus.status === "pending" ? (
            <WalletButton label={busy ? "Checking provider…" : "Refresh payment status"} onPress={onRefreshDeposit} disabled={busy} />
          ) : null}
          <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 17 }}>
            {depositStatus.message ?? "AFCON360 updates your balance only after Flutterwave confirms settlement."}
          </Text>
        </View>
      ) : null}
      <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 17 }}>
        If the payment page or your network closes unexpectedly, keep this request and refresh its status before starting another deposit. The same request key is reused to prevent duplicate payment initiation.
      </Text>
    </Panel>
  );
}

export default WalletDeposit;