import React from "react";
import { Text, View } from "react-native";
import { colors, spacing } from "../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../PamojaScreen";
import {
  WalletAccountCard,
  WalletButton,
} from "./WalletUI";

type WalletBalanceProps = {
  accounts: { currency: string; balance: string; is_frozen: boolean }[];
  selectedCurrency: string;
  onCurrencySelect: (currency: string) => void;
  loading: boolean;
  onStartDeposit: () => void;
};

export function WalletBalance({ accounts, selectedCurrency, onCurrencySelect, loading, onStartDeposit }: WalletBalanceProps) {
  const selectedAccount = accounts.find((a) => a.currency === selectedCurrency);

  return (
    <>
      <Panel>
        <SectionTitle>Wallet accounts</SectionTitle>
        {loading ? null : accounts.length === 0 ? (
          <Text style={{ color: colors.text.muted }}>
            No Wallet account is active yet. Create or activate a Wallet through AFCON360 before sending money.
          </Text>
        ) : null}
        {accounts.map((account) => (
          <WalletAccountCard
            key={account.currency}
            account={account}
            selected={selectedCurrency === account.currency}
            onPress={() => onCurrencySelect(account.currency)}
          />
        ))}
      </Panel>
      <Panel>
        <SectionTitle>Deposits</SectionTitle>
        <Text style={{ color: colors.text.muted, lineHeight: 20 }}>
          Deposits use a Flutterwave hosted checkout. Your Wallet is credited only after the payment provider confirms the deposit.
        </Text>
        <WalletButton label="Start a deposit" onPress={onStartDeposit} disabled={!selectedAccount || selectedAccount.is_frozen} />
        <Text style={{ color: colors.text.muted, fontSize: 12, lineHeight: 18 }}>
          Wallet withdrawals are temporarily unavailable while AFCON360 completes balanced settlement accounting and provider reconciliation checks. Your balance, deposits, transfers and transaction history remain available.
        </Text>
      </Panel>
    </>
  );
}

export default WalletBalance;