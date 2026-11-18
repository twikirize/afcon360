import React from "react";
import { Text, View, Alert } from "react-native";
import { colors, spacing } from "../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";
import {
  WalletField,
  WalletButton,
} from "./WalletUI";

type WalletSendProps = {
  selectedCurrency: string;
  selectedAccount: { currency: string; is_frozen: boolean } | undefined;
  recipientIdentifier: string;
  amount: string;
  transferNote: string;
  transferPin: string;
  resolvedRecipient: { display_name: string; masked_identifier: string; recipient_currency: string } | null;
  busy: boolean;
  error: string | null;
  notice: string | null;
  onRecipientChange: (value: string) => void;
  onAmountChange: (value: string) => void;
  onNoteChange: (value: string) => void;
  onPinChange: (value: string) => void;
  onVerifyRecipient: () => void;
  onSend: () => void;
};

export function WalletSend({
  selectedCurrency,
  selectedAccount,
  recipientIdentifier,
  amount,
  transferNote,
  transferPin,
  resolvedRecipient,
  busy,
  error,
  notice,
  onRecipientChange,
  onAmountChange,
  onNoteChange,
  onPinChange,
  onVerifyRecipient,
  onSend,
}: WalletSendProps) {
  return (
    <Panel>
      <SectionTitle>Send money to an AFCON360 member</SectionTitle>
      <Text style={{ color: colors.text.muted, fontSize: 12 }}>
        Sending from {selectedCurrency}. Only verified AFCON360 payment identities can receive transfers.
      </Text>
      <WalletField
        label="AFCON360 ID, verified phone or email"
        value={recipientIdentifier}
        onChangeText={onRecipientChange}
        placeholder="Enter recipient details"
      />
      <WalletField
        label="Amount"
        value={amount}
        onChangeText={onAmountChange}
        placeholder="0.00"
        keyboardType="decimal-pad"
      />
      <WalletField
        label="Note (optional)"
        value={transferNote}
        onChangeText={onNoteChange}
        placeholder="What is this transfer for?"
        autoCapitalize="sentences"
      />
      <WalletField
        label="Transaction PIN"
        value={transferPin}
        onChangeText={onPinChange}
        placeholder="Enter your 4–6 digit PIN"
        secureTextEntry
        keyboardType="numeric"
      />
      <WalletButton
        label={busy ? "Checking recipient…" : "Verify recipient"}
        onPress={onVerifyRecipient}
        disabled={busy || !recipientIdentifier.trim() || !selectedAccount || selectedAccount.is_frozen}
        secondary
      />
      {resolvedRecipient ? (
        <View style={{ backgroundColor: "#F1F6F2", borderRadius: 12, padding: 14, gap: 5 }}>
          <Text style={{ color: colors.text.muted, fontSize: 11, fontWeight: "800" }}>VERIFIED RECIPIENT</Text>
          <Text style={{ color: colors.text.ink, fontSize: 17, fontWeight: "900" }}>
            {resolvedRecipient.display_name}
          </Text>
          <Text style={{ color: colors.text.muted, fontSize: 12 }}>
            {resolvedRecipient.masked_identifier} · {resolvedRecipient.recipient_currency}
          </Text>
          {resolvedRecipient.recipient_currency !== selectedCurrency ? (
            <Text style={{ color: "#9A3A2F", fontWeight: "700" }}>
              Currency differs. Cross-currency wallet transfers remain unavailable until AFCON360 has an approved executable FX provider and balanced clearing ledger. No debit will be made.
            </Text>
          ) : (
            <WalletButton
              label={busy ? "Sending…" : `Confirm and send ${amount || "0"} ${selectedCurrency}`}
              onPress={onSend}
              disabled={busy || !amount.trim() || !transferPin.trim() || !selectedAccount || selectedAccount.is_frozen}
            />
          )}
        </View>
      ) : null}
      <Text style={{ color: colors.text.muted, fontSize: 11, lineHeight: 17 }}>
        Transfers require your transaction PIN and a unique request key. If a connection fails after you submit, retrying the same request uses the same key so the ledger cannot create a second transfer.
      </Text>
    </Panel>
  );
}

export default WalletSend;