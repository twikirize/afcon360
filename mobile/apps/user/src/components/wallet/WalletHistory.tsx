import React from "react";
import { Text, View } from "react-native";
import { colors, spacing } from "../../theme/tokens";
import {
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
} from "../PamojaScreen";
import {
  WalletButton,
  WalletTransactionItem,
} from "./WalletUI";
import { formatDate } from "./types";

type WalletHistoryProps = {
  transactions: { reference: string; direction: string; type: string; amount: string; currency: string; status: string; created_at: string | null }[];
  busy: boolean;
  loading: boolean;
  onRefresh: () => void;
};

export function WalletHistory({ transactions, busy, loading, onRefresh }: WalletHistoryProps) {
  return (
    <Panel>
      <SectionTitle>Recent transactions</SectionTitle>
      {transactions.length === 0 ? (
        <Text style={{ color: colors.text.muted }}>No transactions to display.</Text>
      ) : (
        transactions.map((item) => (
          <WalletTransactionItem key={item.reference} item={item} />
        ))
      )}
      <WalletButton label="Refresh history" onPress={onRefresh} disabled={busy || loading} secondary />
    </Panel>
  );
}

export default WalletHistory;