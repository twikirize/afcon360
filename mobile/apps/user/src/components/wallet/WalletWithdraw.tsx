import React from "react";
import { Text, View, Alert } from "react-native";
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
import { NATIVE_WITHDRAWALS_ENABLED } from "./types";

type WalletWithdrawProps = {
  selectedCurrency: string;
  selectedAccount: { currency: string; is_frozen: boolean } | undefined;
  withdrawalAmount: string;
  withdrawalNetwork: "MTN" | "AIRTEL" | "MPS";
  withdrawalPhone: string;
  withdrawalBeneficiary: string;
  withdrawalPin: string;
  withdrawalQuote: { quote_token: string; amount: string; currency: string; beneficiary_name: string; masked_phone: string; network: string; platform_fee: string; total_wallet_debit: string; available_balance: string; fee_percent: string; provider_fee: string; expires_at: string } | null;
  withdrawalReference: string | null;
  withdrawalStatus: { reference: string; status: string; amount: string; currency: string; failure_reason?: string; manual_review_required?: boolean } | null;
  busy: boolean;
  error: string | null;
  notice: string | null;
  onAmountChange: (value: string) => void;
  onNetworkChange: (network: "MTN" | "AIRTEL" | "MPS") => void;
  onPhoneChange: (value: string) => void;
  onBeneficiaryChange: (value: string) => void;
  onPinChange: (value: string) => void;
  onRequestQuote: () => void;
  onConfirmWithdrawal: () => void;
  onRefreshWithdrawal: () => void;
};

export function WalletWithdraw({
  selectedCurrency,
  selectedAccount,
  withdrawalAmount,
  withdrawalNetwork,
  withdrawalPhone,
  withdrawalBeneficiary,
  withdrawalPin,
  withdrawalQuote,
  withdrawalReference,
  withdrawalStatus,
  busy,
  error,
  notice,
  onAmountChange,
  onNetworkChange,
  onPhoneChange,
  onBeneficiaryChange,
  onPinChange,
  onRequestQuote,
  onConfirmWithdrawal,
  onRefreshWithdrawal,
}: WalletWithdrawProps) {
  if (!NATIVE_WITHDRAWALS_ENABLED) return null;

  return (
    <Panel>
      <SectionTitle>Withdraw from your AFCON360 Wallet</SectionTitle>
      <Text style={{ color: colors.text.muted, lineHeight: 19 }}>
        The first native payout corridor supports Uganda UGX mobile money. AFCON360 checks your wallet and configured withdrawal fee before showing a quote. No money is reserved until you confirm with your transaction PIN.
      </Text>
      {selectedCurrency !== "UGX" ? (
        <Text style={{ color: "#9A3A2F", fontWeight: "700" }}>
          This wallet is {selectedCurrency}. The Uganda UGX payout route is not available for this currency.
        </Text>
      ) : null}
      <Text style={{ color: colors.text.ink, fontWeight: "800" }}>Wallet currency: {selectedCurrency}</Text>
      <WalletField
        label="Withdrawal amount"
        value={withdrawalAmount}
        onChangeText={onAmountChange}
        placeholder="Whole UGX amount"
        keyboardType="numeric"
      />
      <Text style={{ color: colors.text.ink, fontWeight: "700", fontSize: 13 }}>Mobile money network</Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {([
          ["MTN", "MTN"],
          ["AIRTEL", "Airtel"],
          ["MPS", "MPS"],
        ] as const).map(([network, label]) => (
          <Pressable
            key={network}
            onPress={() => onNetworkChange(network as "MTN" | "AIRTEL" | "MPS")}
            style={{
              backgroundColor: withdrawalNetwork === network ? colors.brand.green : "#EEF3F0",
              borderRadius: radii.sm,
              paddingVertical: 10,
              paddingHorizontal: 14,
            }}
            hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          >
            <Text style={{ color: withdrawalNetwork === network ? "#FFFFFF" : colors.text.ink, fontWeight: "800" }}>
              {label}
            </Text>
          </Pressable>
        ))}
      </View>
      <WalletField
        label="Beneficiary's Ugandan mobile number"
        value={withdrawalPhone}
        onChangeText={onPhoneChange}
        placeholder="07XXXXXXXX or +2567XXXXXXXX"
        keyboardType="phone-pad"
      />
      <WalletField
        label="Beneficiary full name"
        value={withdrawalBeneficiary}
        onChangeText={onBeneficiaryChange}
        placeholder="Name registered to the mobile money account"
        autoCapitalize="words"
      />
      <WalletButton
        label={busy ? "Preparing quote…" : withdrawalQuote ? "Request a fresh quote" : "Get withdrawal quote"}
        onPress={onRequestQuote}
        disabled={busy || selectedCurrency !== "UGX" || !selectedAccount || selectedAccount.is_frozen || !withdrawalAmount.trim() || !withdrawalPhone.trim() || !withdrawalBeneficiary.trim()}
        secondary
      />
      {withdrawalQuote ? (
        <View style={{ backgroundColor: "#F1F6F2", borderRadius: 12, padding: 14, gap: 8 }}>
          <Text style={{ color: colors.text.muted, fontSize: 11, fontWeight: "800" }}>REVIEW THIS WITHDRAWAL</Text>
          <Text style={{ color: colors.text.ink, fontSize: 20, fontWeight: "900" }}>
            {withdrawalQuote.amount} {withdrawalQuote.currency}
          </Text>
          <Text style={{ color: colors.text.ink, fontWeight: "700" }}>
            {withdrawalQuote.beneficiary_name} · {withdrawalQuote.masked_phone} · {withdrawalQuote.network}
          </Text>
          <View style={{ gap: 4 }}>
            <Text style={{ color: colors.text.muted }}>AFCON360 withdrawal fee ({withdrawalQuote.fee_percent}%): {withdrawalQuote.platform_fee} {withdrawalQuote.currency}</Text>
            <Text style={{ color: colors.text.ink, fontWeight: "900" }}>Total Wallet debit: {withdrawalQuote.total_wallet_debit} {withdrawalQuote.currency}</Text>
            <Text style={{ color: colors.text.muted }}>Available before confirmation: {withdrawalQuote.available_balance} {withdrawalQuote.currency}</Text>
            <Text style={{ color: colors.text.muted, fontSize: 11 }}>{withdrawalQuote.provider_fee}</Text>
            <Text style={{ color: colors.text.muted, fontSize: 11 }}>Quote expires: {formatDate(withdrawalQuote.expires_at)}</Text>
          </View>
          <WalletField
            label="Transaction PIN"
            value={withdrawalPin}
            onChangeText={onPinChange}
            placeholder="Enter your 4–6 digit PIN"
            secureTextEntry
            keyboardType="numeric"
          />
          <WalletButton label={busy ? "Confirming withdrawal…" : "Review and confirm withdrawal"} onPress={onConfirmWithdrawal} disabled={busy || !withdrawalPin.trim()} />
          <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 17 }}>
            Confirming reserves the total amount in your Wallet. The payout will remain pending until Flutterwave confirms delivery.
          </Text>
        </View>
      ) : null}
      {withdrawalStatus ? (
        <View style={{ backgroundColor: "#F1F6F2", borderRadius: 12, padding: 14, gap: 8 }}>
          <StatusPill tone={withdrawalStatus.status === "completed" ? "green" : withdrawalStatus.status === "failed" ? "gold" : "gold"}>
            Withdrawal {withdrawalStatus.status}
          </StatusPill>
          <Text style={{ color: colors.text.ink, fontWeight: "900" }}>
            {formatMoney(Number(withdrawalStatus.amount), withdrawalStatus.currency)}
          </Text>
          <Text style={{ color: colors.text.muted, fontSize: 11 }}>Reference: {withdrawalStatus.reference}</Text>
          {withdrawalStatus.status === "pending" ? (
            <WalletButton label={busy ? "Verifying provider…" : "Refresh withdrawal status"} onPress={onRefreshWithdrawal} disabled={busy} secondary />
          ) : null}
          {withdrawalStatus.failure_reason && <Text style={{ color: "#9A3A2F", fontSize: 12 }}>{withdrawalStatus.failure_reason}</Text>}
          <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 17 }}>
            {withdrawalStatus.status === "completed"
              ? "Provider confirmation received. The payout is complete."
              : withdrawalStatus.status === "failed"
              ? "Provider confirmed the failure. The reserved Wallet amount has been reversed."
              : withdrawalStatus.manual_review_required
              ? "The provider response needs reconciliation. Your Wallet funds remain reserved; do not submit another withdrawal."
              : "The payout is still being processed. Your Wallet funds remain reserved until the provider confirms success or failure."}
          </Text>
        </View>
      ) : null}
    </Panel>
  );
}

export default WalletWithdraw;