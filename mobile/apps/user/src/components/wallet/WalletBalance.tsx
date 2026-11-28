import React from "react";
import { Text, View } from "react-native";
import * as WebBrowser from "expo-web-browser";
import { colors, spacing } from "../../theme/tokens";
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

// The wallet-create form is web-only: there is no native create screen, so the
// prompt hands off to the page the dashboard banner links to (wallet.wallet_create_page).
const SITE = "https://www.pamoja.space";

export function WalletBalance({ accounts, selectedCurrency, onCurrencySelect, loading, onStartDeposit }: WalletBalanceProps) {
  const selectedAccount = accounts.find((a) => a.currency === selectedCurrency);

  return (
    <>
      <Panel>
        <SectionTitle>Wallet accounts</SectionTitle>
        {loading ? null : accounts.length === 0 ? (
          // templates/wallet/wallet_dashboard.html renders this prompt when the
          // signed-in user has no wallet: a heading, one sentence and a
          // "Create Wallet" action. Reproduced here with the same words.
          <View style={{ gap: spacing.sm, padding: spacing.lg, borderRadius: 12, backgroundColor: colors.brand.greenSoft }}>
            <Text style={{ color: colors.text.ink, fontSize: 15, fontWeight: "800" }}>Welcome to Your Wallet</Text>
            <Text style={{ color: colors.text.muted, lineHeight: 20 }}>
              You don't have a wallet yet. Create one to start sending and receiving money.
            </Text>
            <WalletButton label="Create Wallet" onPress={() => void WebBrowser.openBrowserAsync(SITE + "/wallet/create")} />
            <Text style={{ color: colors.text.muted, fontSize: 12, lineHeight: 18 }}>
              Create your wallet on the Pamoja website.
            </Text>
          </View>
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