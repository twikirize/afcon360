import React, { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  AppScreen,
  PageHeader,
  Panel,
  SectionTitle,
  StatusPill,
  palette,
} from "@afcon360/mobile-ui";
import { walletClient } from "../../src/services/api";
import type {
  ResolvedWalletRecipient,
  WalletAccount,
  WalletPinStatus,
  WalletTransaction,
} from "@afcon360/mobile-core";

type WalletTab = "balance" | "send" | "history" | "pin";

function Button({
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
      style={{
        backgroundColor: secondary ? "#EEF3F0" : palette.green,
        borderRadius: 12,
        paddingVertical: 13,
        paddingHorizontal: 16,
        alignItems: "center",
        opacity: disabled ? 0.45 : 1,
      }}
    >
      <Text style={{ color: secondary ? palette.ink : "#FFFFFF", fontWeight: "800" }}>
        {label}
      </Text>
    </Pressable>
  );
}

function Field({
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
  keyboardType?: "default" | "numeric" | "decimal-pad" | "email-address";
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
}) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: palette.ink, fontWeight: "700", fontSize: 13 }}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#8A948F"
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        style={{
          backgroundColor: "#FFFFFF",
          borderWidth: 1,
          borderColor: "#DCE5DF",
          borderRadius: 10,
          paddingHorizontal: 12,
          paddingVertical: 12,
          color: palette.ink,
          fontSize: 15,
        }}
      />
    </View>
  );
}

function formatDate(value: string | null): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

export default function Wallet() {
  const [accounts, setAccounts] = useState<WalletAccount[]>([]);
  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);
  const [pinStatus, setPinStatus] = useState<WalletPinStatus | null>(null);
  const [selectedCurrency, setSelectedCurrency] = useState("UGX");
  const [tab, setTab] = useState<WalletTab>("balance");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [recipientIdentifier, setRecipientIdentifier] = useState("");
  const [amount, setAmount] = useState("");
  const [transferNote, setTransferNote] = useState("");
  const [transferPin, setTransferPin] = useState("");
  const [resolvedRecipient, setResolvedRecipient] = useState<ResolvedWalletRecipient | null>(null);
  const [transferRequestKey, setTransferRequestKey] = useState<string | null>(null);

  const [newPin, setNewPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [currentPin, setCurrentPin] = useState("");
  const [accountPassword, setAccountPassword] = useState("");

  const loadWallet = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summary, history, pin] = await Promise.all([
        walletClient.getSummary(),
        walletClient.getTransactions(30, 0),
        walletClient.getPinStatus(),
      ]);
      setAccounts(summary.accounts ?? []);
      setTransactions(history.items ?? []);
      setPinStatus(pin);
      if (summary.accounts?.length) {
        setSelectedCurrency((current) =>
          summary.accounts.some((item) => item.currency === current)
            ? current
            : summary.accounts[0].currency
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Wallet information is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWallet();
  }, [loadWallet]);

  const selectedAccount = accounts.find((item) => item.currency === selectedCurrency);

  const resolveRecipient = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    setResolvedRecipient(null);
    try {
      const recipient = await walletClient.resolveRecipient(recipientIdentifier, selectedCurrency);
      setResolvedRecipient(recipient);
      setNotice("Recipient verified. Check the name and currency before sending.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "AFCON360 could not verify that recipient.");
    } finally {
      setBusy(false);
    }
  };

  const sendTransfer = async () => {
    if (!resolvedRecipient) {
      setError("Verify the recipient before sending.");
      return;
    }
    const requestKey =
      transferRequestKey ??
      "native-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 18);
    setTransferRequestKey(requestKey);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await walletClient.transfer({
        identifier: recipientIdentifier,
        amount,
        currency: selectedCurrency,
        pin: transferPin,
        note: transferNote,
        idempotencyKey: requestKey,
      });
      setNotice(
        result.already_processed
          ? "This transfer was already completed. Your balance and history have been refreshed."
          : "Transfer completed. AFCON360 has updated the Wallet ledger."
      );
      setRecipientIdentifier("");
      setAmount("");
      setTransferNote("");
      setTransferPin("");
      setResolvedRecipient(null);
      setTransferRequestKey(null);
      await loadWallet();
    } catch (e) {
      // Preserve the idempotency key after an uncertain network/server response.
      // Retrying the same request must not create a second money movement.
      setError(e instanceof Error ? e.message : "AFCON360 could not complete the transfer.");
    } finally {
      setBusy(false);
    }
  };

  const updatePin = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await walletClient.setPin({
        pin: newPin,
        confirm_pin: confirmPin,
        ...(pinStatus?.pin_set
          ? { current_pin: currentPin }
          : { password: accountPassword }),
      });
      setNewPin("");
      setConfirmPin("");
      setCurrentPin("");
      setAccountPassword("");
      setNotice("Your transaction PIN has been updated.");
      setPinStatus(await walletClient.getPinStatus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "AFCON360 could not update the transaction PIN.");
    } finally {
      setBusy(false);
    }
  };

  const tabButton = (key: WalletTab, label: string) => (
    <Pressable
      key={key}
      onPress={() => {
        setTab(key);
        setError(null);
        setNotice(null);
      }}
      style={{
        backgroundColor: tab === key ? palette.green : "#EEF3F0",
        paddingVertical: 10,
        paddingHorizontal: 12,
        borderRadius: 10,
      }}
    >
      <Text style={{ color: tab === key ? "#FFFFFF" : palette.ink, fontWeight: "800", fontSize: 12 }}>
        {label}
      </Text>
    </Pressable>
  );

  return (
    <AppScreen>
      <ScrollView contentContainerStyle={{ gap: 14, paddingBottom: 28 }}>
        <PageHeader
          eyebrow="Wallet"
          title="Your money, clearly managed."
          description="Balances, transfers and transaction history come from the AFCON360 Wallet ledger. The app does not calculate or store your balance."
        />

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {tabButton("balance", "Balance")}
          {tabButton("send", "Send")}
          {tabButton("history", "History")}
          {tabButton("pin", "Transaction PIN")}
        </View>

        {loading ? <ActivityIndicator color={palette.green} /> : null}
        {error ? (
          <Panel>
            <Text style={{ color: "#9A3A2F", fontWeight: "600" }}>{error}</Text>
          </Panel>
        ) : null}
        {notice ? (
          <Panel>
            <Text style={{ color: palette.green, fontWeight: "700" }}>{notice}</Text>
          </Panel>
        ) : null}

        {tab === "balance" ? (
          <>
            <Panel>
              <SectionTitle>Wallet accounts</SectionTitle>
              {!loading && accounts.length === 0 ? (
                <Text style={{ color: palette.muted }}>
                  No Wallet account is active yet. Create or activate a Wallet through AFCON360 before sending money.
                </Text>
              ) : null}
              {accounts.map((account) => (
                <Pressable
                  key={account.currency}
                  onPress={() => setSelectedCurrency(account.currency)}
                  style={{
                    borderWidth: selectedCurrency === account.currency ? 2 : 1,
                    borderColor: selectedCurrency === account.currency ? palette.green : "#E1E8E3",
                    borderRadius: 12,
                    padding: 14,
                    marginTop: 8,
                    gap: 7,
                  }}
                >
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                    <Text style={{ color: palette.ink, fontWeight: "900" }}>{account.currency}</Text>
                    <StatusPill tone={account.is_frozen ? "gold" : "green"}>
                      {account.is_frozen ? "Restricted" : "Active"}
                    </StatusPill>
                  </View>
                  <Text style={{ color: palette.ink, fontSize: 25, fontWeight: "900" }}>
                    {account.balance} {account.currency}
                  </Text>
                  <Text style={{ color: palette.muted, fontSize: 12 }}>
                    Balance read directly from the Wallet ledger
                  </Text>
                </Pressable>
              ))}
            </Panel>
            <Panel>
              <SectionTitle>Deposits and withdrawals</SectionTitle>
              <Text style={{ color: palette.muted, lineHeight: 20 }}>
                Native deposits are not enabled until provider-confirmed deposit initiation and webhook reconciliation are available. Native withdrawals are not enabled until the server can confirm the actual bank or mobile-money payout. The app will not report either operation as successful before the provider confirms it.
              </Text>
            </Panel>
          </>
        ) : null}

        {tab === "send" ? (
          <Panel>
            <SectionTitle>Send money to an AFCON360 member</SectionTitle>
            <Text style={{ color: palette.muted, fontSize: 12 }}>
              Sending from {selectedCurrency}. Only verified AFCON360 payment identities can receive transfers.
            </Text>
            <Field
              label="AFCON360 ID, verified phone or email"
              value={recipientIdentifier}
              onChangeText={(value) => {
                setRecipientIdentifier(value);
                setResolvedRecipient(null);
              }}
              placeholder="Enter recipient details"
            />
            <Field
              label="Amount"
              value={amount}
              onChangeText={setAmount}
              placeholder="0.00"
              keyboardType="decimal-pad"
            />
            <Field
              label="Note (optional)"
              value={transferNote}
              onChangeText={setTransferNote}
              placeholder="What is this transfer for?"
              autoCapitalize="sentences"
            />
            <Field
              label="Transaction PIN"
              value={transferPin}
              onChangeText={setTransferPin}
              placeholder="Enter your 4–6 digit PIN"
              secureTextEntry
              keyboardType="numeric"
            />
            <Button
              label={busy ? "Checking recipient…" : "Verify recipient"}
              onPress={() => void resolveRecipient()}
              disabled={busy || !recipientIdentifier.trim() || !selectedAccount || selectedAccount.is_frozen}
              secondary
            />
            {resolvedRecipient ? (
              <View style={{ backgroundColor: "#F1F6F2", borderRadius: 12, padding: 14, gap: 5 }}>
                <Text style={{ color: palette.muted, fontSize: 11, fontWeight: "800" }}>VERIFIED RECIPIENT</Text>
                <Text style={{ color: palette.ink, fontSize: 17, fontWeight: "900" }}>
                  {resolvedRecipient.display_name}
                </Text>
                <Text style={{ color: palette.muted, fontSize: 12 }}>
                  {resolvedRecipient.masked_identifier} · {resolvedRecipient.recipient_currency}
                </Text>
                {resolvedRecipient.recipient_currency !== selectedCurrency ? (
                  <Text style={{ color: "#9A3A2F", fontWeight: "700" }}>
                    Currency differs. A confirmed FX quote is required before transfer.
                  </Text>
                ) : (
                  <Button
                    label={busy ? "Sending…" : `Confirm and send ${amount || "0"} ${selectedCurrency}`}
                    onPress={() => void sendTransfer()}
                    disabled={
                      busy ||
                      !amount.trim() ||
                      !transferPin.trim() ||
                      !selectedAccount ||
                      selectedAccount.is_frozen
                    }
                  />
                )}
              </View>
            ) : null}
            <Text style={{ color: palette.muted, fontSize: 11, lineHeight: 17 }}>
              Transfers require your transaction PIN and a unique request key. If a connection fails after you submit, retrying the same request uses the same key so the ledger cannot create a second transfer.
            </Text>
          </Panel>
        ) : null}

        {tab === "history" ? (
          <Panel>
            <SectionTitle>Recent transactions</SectionTitle>
            {transactions.length === 0 ? (
              <Text style={{ color: palette.muted }}>No transactions to display.</Text>
            ) : (
              transactions.map((item) => (
                <View
                  key={item.reference}
                  style={{ borderBottomWidth: 1, borderBottomColor: "#E7ECE8", paddingVertical: 11, gap: 4 }}
                >
                  <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
                    <Text style={{ color: palette.ink, fontWeight: "800", textTransform: "capitalize" }}>
                      {item.direction === "received" ? "Received" : item.type}
                    </Text>
                    <Text style={{ color: palette.ink, fontWeight: "900" }}>
                      {item.direction === "received" ? "+" : "−"}{item.amount} {item.currency}
                    </Text>
                  </View>
                  <Text style={{ color: palette.muted, fontSize: 11 }}>
                    {item.status} · {formatDate(item.created_at)}
                  </Text>
                  <Text style={{ color: palette.muted, fontSize: 10 }}>
                    Ref: {item.reference}
                  </Text>
                </View>
              ))
            )}
            <Button label="Refresh history" onPress={() => void loadWallet()} disabled={busy || loading} secondary />
          </Panel>
        ) : null}

        {tab === "pin" ? (
          <Panel>
            <SectionTitle>Transaction PIN</SectionTitle>
            <StatusPill tone={pinStatus?.locked ? "gold" : pinStatus?.pin_set ? "green" : "gold"}>
              {pinStatus?.locked ? "PIN locked" : pinStatus?.pin_set ? "PIN set" : "PIN not set"}
            </StatusPill>
            <Text style={{ color: palette.muted, lineHeight: 19 }}>
              {pinStatus?.pin_set
                ? "To change your PIN, enter your current PIN and choose a new one."
                : "To set your first PIN, re-enter your AFCON360 account password and choose a new PIN."}
            </Text>
            {pinStatus?.pin_set ? (
              <Field
                label="Current PIN"
                value={currentPin}
                onChangeText={setCurrentPin}
                placeholder="Current 4–6 digit PIN"
                secureTextEntry
                keyboardType="numeric"
              />
            ) : (
              <Field
                label="AFCON360 account password"
                value={accountPassword}
                onChangeText={setAccountPassword}
                placeholder="Current account password"
                secureTextEntry
              />
            )}
            <Field
              label="New PIN"
              value={newPin}
              onChangeText={setNewPin}
              placeholder="Choose 4–6 digits"
              secureTextEntry
              keyboardType="numeric"
            />
            <Field
              label="Confirm new PIN"
              value={confirmPin}
              onChangeText={setConfirmPin}
              placeholder="Enter the new PIN again"
              secureTextEntry
              keyboardType="numeric"
            />
            <Button
              label={busy ? "Updating PIN…" : pinStatus?.pin_set ? "Change transaction PIN" : "Set transaction PIN"}
              onPress={() => void updatePin()}
              disabled={
                busy ||
                !newPin.trim() ||
                !confirmPin.trim() ||
                (pinStatus?.pin_set ? !currentPin.trim() : !accountPassword.trim())
              }
            />
          </Panel>
        ) : null}
      </ScrollView>
    </AppScreen>
  );
}
