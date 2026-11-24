import React, { useCallback, useEffect, useState } from "react";
import * as SecureStore from "expo-secure-store";
import { Alert, Linking, AppState, ScrollView, ActivityIndicator, View, Text } from "react-native";
import { useFocusEffect } from "expo-router";
import { walletClient } from "../../services/api";
import type {
  ResolvedWalletRecipient,
  WalletAccount,
  WalletDepositStatus,
  WalletPinStatus,
  WalletTransaction,
  WalletWithdrawalNetwork,
  WalletWithdrawalQuote,
  WalletWithdrawalStatus,
} from "@afcon360/mobile-core";
import { colors } from "../../theme/tokens";
import {
  PamojaScreen as AppScreen,
  PamojaPageHeader as PageHeader,
  PamojaPanel as Panel,
} from "../PamojaScreen";
import { ServiceHeroAccent } from "../ServiceHeroAccent";
import { WalletTabs } from "./WalletTabs";
import { WalletBalance } from "./WalletBalance";
import { WalletSend } from "./WalletSend";
import { WalletDeposit } from "./WalletDeposit";
import { WalletWithdraw } from "./WalletWithdraw";
import { WalletHistory } from "./WalletHistory";
import { WalletPin } from "./WalletPin";
import {
  WalletState,
  SendState,
  DepositState,
  WithdrawalState,
  PinState,
  depositStoreKeys,
  withdrawalStoreKeys,
  NATIVE_WITHDRAWALS_ENABLED,
  formatDate,
  formatMoney,
  newIdempotencyKey,
} from "./types";

export function WalletScreen() {
  const [wallet, setWallet] = useState<WalletState>({
    accounts: [],
    transactions: [],
    pinStatus: null,
    selectedCurrency: "UGX",
    loading: true,
    busy: false,
    error: null,
    notice: null,
  });

  const [send, setSend] = useState<SendState>({
    recipientIdentifier: "",
    amount: "",
    transferNote: "",
    transferPin: "",
    resolvedRecipient: null,
    transferRequestKey: null,
  });

  const [deposit, setDeposit] = useState<DepositState>({
    depositAmount: "",
    depositPaymentMethod: "mobilemoney",
    depositRequestKey: null,
    depositReference: null,
    depositCheckoutUrl: null,
    depositStatus: null,
  });

  const [withdrawal, setWithdrawal] = useState<WithdrawalState>({
    withdrawalAmount: "",
    withdrawalNetwork: "MTN",
    withdrawalPhone: "",
    withdrawalBeneficiary: "",
    withdrawalPin: "",
    withdrawalQuote: null,
    withdrawalReference: null,
    withdrawalStatus: null,
  });

  const [pin, setPin] = useState<PinState>({
    newPin: "",
    confirmPin: "",
    currentPin: "",
    accountPassword: "",
  });

  const [tab, setTab] = useState<"balance" | "deposit" | "send" | "withdraw" | "history" | "pin">("balance");

  const selectedAccount = wallet.accounts.find((a) => a.currency === wallet.selectedCurrency);

  const loadWallet = useCallback(async () => {
    setWallet((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const [summary, history, pinStatus] = await Promise.all([
        walletClient.getSummary(),
        walletClient.getTransactions(30, 0),
        walletClient.getPinStatus(),
      ]);
      setWallet((prev) => ({
        ...prev,
        accounts: summary.accounts ?? [],
        transactions: history.items ?? [],
        pinStatus,
        selectedCurrency: prev.selectedCurrency,
        loading: false,
      }));
      if (summary.accounts?.length) {
        setWallet((prev) => ({
          ...prev,
          selectedCurrency: summary.accounts.some((a) => a.currency === prev.selectedCurrency)
            ? prev.selectedCurrency
            : summary.accounts[0].currency,
        }));
      }
    } catch (e) {
      setWallet((prev) => ({
        ...prev,
        error: e instanceof Error ? e.message : "Wallet information is unavailable.",
        loading: false,
      }));
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadWallet();
      const subscription = AppState.addEventListener("change", (state) => {
        if (state === "active") void loadWallet();
      });
      return () => subscription.remove();
    }, [loadWallet])
  );

  // Restore deposit state from SecureStore
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [requestKey, reference, checkoutUrl, savedAmount, savedCurrency, savedMethod] = await Promise.all([
          SecureStore.getItemAsync(depositStoreKeys.request),
          SecureStore.getItemAsync(depositStoreKeys.reference),
          SecureStore.getItemAsync(depositStoreKeys.checkout),
          SecureStore.getItemAsync(depositStoreKeys.amount),
          SecureStore.getItemAsync(depositStoreKeys.currency),
          SecureStore.getItemAsync(depositStoreKeys.method),
        ]);
        if (!active) return;
        if (requestKey) setDeposit((prev) => ({ ...prev, depositRequestKey: requestKey }));
        if (savedAmount) setDeposit((prev) => ({ ...prev, depositAmount: savedAmount }));
        if (savedCurrency) setWallet((prev) => ({ ...prev, selectedCurrency: savedCurrency }));
        if (savedMethod === "card" || savedMethod === "mobilemoney") setDeposit((prev) => ({ ...prev, depositPaymentMethod: savedMethod }));
        if (reference) {
          setDeposit((prev) => ({ ...prev, depositReference: reference }));
          if (checkoutUrl) setDeposit((prev) => ({ ...prev, depositCheckoutUrl: checkoutUrl }));
          try {
            const status = await walletClient.getDepositStatus(reference);
            if (active) setDeposit((prev) => ({ ...prev, depositStatus: status }));
          } catch {
            // Preserve reference for manual refresh
          }
        }
      } catch {
        // SecureStore unavailable
      }
    })();
    return () => { active = false; };
  }, []);

  // Restore withdrawal state from SecureStore
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [savedQuote, savedReference] = await Promise.all([
          SecureStore.getItemAsync(withdrawalStoreKeys.quote),
          SecureStore.getItemAsync(withdrawalStoreKeys.reference),
        ]);
        if (!active) return;
        if (NATIVE_WITHDRAWALS_ENABLED) {
          if (savedQuote) {
            const parsed = JSON.parse(savedQuote) as WalletWithdrawalQuote;
            const expiry = Date.parse(parsed.expires_at);
            if (parsed.quote_token && Number.isFinite(expiry) && expiry > Date.now()) {
              setWithdrawal((prev) => ({ ...prev, withdrawalQuote: parsed }));
              setTab("withdraw");
            } else {
              await SecureStore.deleteItemAsync(withdrawalStoreKeys.quote);
            }
          }
          if (savedReference) {
            setTab("withdraw");
            setWithdrawal((prev) => ({ ...prev, withdrawalReference: savedReference }));
            try {
              const status = await walletClient.getWithdrawalStatus(savedReference);
              if (active) setWithdrawal((prev) => ({ ...prev, withdrawalStatus: status }));
            } catch {
              // Keep reference for retry
            }
          }
        }
      } catch {
        // SecureStore unavailable
      }
    })();
    return () => { active = false; };
  }, []);

  const clearSavedDeposit = async () => {
    await Promise.all(Object.values(depositStoreKeys).map((key) => SecureStore.deleteItemAsync(key)));
  };

  const clearSavedWithdrawal = async () => {
    await Promise.all([
      SecureStore.deleteItemAsync(withdrawalStoreKeys.quote),
      SecureStore.deleteItemAsync(withdrawalStoreKeys.reference),
    ]);
  };

  const invalidateWithdrawalQuote = () => {
    setWithdrawal((prev) => ({ ...prev, withdrawalQuote: null }));
    SecureStore.deleteItemAsync(withdrawalStoreKeys.quote);
  };

  const handleTabChange = useCallback((newTab: typeof tab) => {
    setTab(newTab);
    setWallet((prev) => ({ ...prev, error: null, notice: null }));
  }, []);

  const handleTabPress = useCallback(() => {
    setWallet((prev) => ({ ...prev, error: null, notice: null }));
  }, []);

  // --- Send ---
  const resolveRecipient = useCallback(async () => {
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    setSend((prev) => ({ ...prev, resolvedRecipient: null }));
    try {
      const recipient = await walletClient.resolveRecipient(send.recipientIdentifier, wallet.selectedCurrency);
      setSend((prev) => ({ ...prev, resolvedRecipient: recipient }));
      setWallet((prev) => ({ ...prev, notice: "Recipient verified. Check the name and currency before sending." }));
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not verify that recipient." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [send.recipientIdentifier, wallet.selectedCurrency]);

  const sendTransfer = useCallback(async () => {
    if (!send.resolvedRecipient) {
      setWallet((prev) => ({ ...prev, error: "Verify the recipient before sending." }));
      return;
    }
    const requestKey = send.transferRequestKey ?? newIdempotencyKey();
    setSend((prev) => ({ ...prev, transferRequestKey: requestKey }));
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      const result = await walletClient.transfer({
        identifier: send.recipientIdentifier,
        amount: send.amount,
        currency: wallet.selectedCurrency,
        pin: send.transferPin,
        note: send.transferNote,
        idempotencyKey: requestKey,
      });
      setWallet((prev) => ({
        ...prev,
        notice: result.already_processed
          ? "This transfer was already completed. Your balance and history have been refreshed."
          : "Transfer completed. AFCON360 has updated the Wallet ledger.",
      }));
      setSend({
        recipientIdentifier: "",
        amount: "",
        transferNote: "",
        transferPin: "",
        resolvedRecipient: null,
        transferRequestKey: null,
      });
      await loadWallet();
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not complete the transfer." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [send, wallet.selectedCurrency]);

  // --- Deposit ---
  const startDeposit = useCallback(async () => {
    const requestKey = deposit.depositRequestKey ?? newIdempotencyKey();
    setDeposit((prev) => ({ ...prev, depositRequestKey: requestKey }));
    try {
      await Promise.all([
        SecureStore.setItemAsync(depositStoreKeys.request, requestKey),
        SecureStore.setItemAsync(depositStoreKeys.amount, deposit.depositAmount),
        SecureStore.setItemAsync(depositStoreKeys.currency, wallet.selectedCurrency),
        SecureStore.setItemAsync(depositStoreKeys.method, deposit.depositPaymentMethod),
      ]);
    } catch {
      setWallet((prev) => ({ ...prev, error: "AFCON360 could not preserve this deposit request securely. Check your connection and try again." }));
      return;
    }
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      const result = await walletClient.startDeposit({
        amount: deposit.depositAmount,
        currency: wallet.selectedCurrency,
        paymentMethod: deposit.depositPaymentMethod,
        idempotencyKey: requestKey,
      });
      setDeposit((prev) => ({
        ...prev,
        depositReference: result.reference,
        depositStatus: {
          reference: result.reference,
          status: result.status,
          amount: result.amount,
          currency: result.currency,
          payment_provider: result.payment_provider,
          message: result.message,
        },
        depositCheckoutUrl: result.authorization_url,
      }));
      await Promise.all([
        SecureStore.setItemAsync(depositStoreKeys.reference, result.reference),
        ...(result.authorization_url ? [SecureStore.setItemAsync(depositStoreKeys.checkout, result.authorization_url)] : []),
      ]);
      if (result.authorization_url) {
        const checkout = new URL(result.authorization_url);
        if (checkout.protocol !== "https:") throw new Error("The payment provider returned an insecure checkout link. Do not continue.");
        await Linking.openURL(checkout.toString());
        setWallet((prev) => ({ ...prev, notice: "Flutterwave checkout opened. Complete payment there, then return to AFCON360 and refresh the deposit status." }));
      } else {
        setWallet((prev) => ({ ...prev, notice: "The payment request is pending provider confirmation. Refresh its status before starting another deposit." }));
      }
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not start this deposit." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [deposit, wallet.selectedCurrency]);

  const refreshDeposit = useCallback(async () => {
    if (!deposit.depositReference) return;
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      const status = await walletClient.refreshDepositStatus(deposit.depositReference);
      setDeposit((prev) => ({ ...prev, depositStatus: status }));
      if (status.status === "completed") {
        setWallet((prev) => ({ ...prev, notice: "Deposit confirmed by Flutterwave and credited to your AFCON360 Wallet." }));
        setDeposit((prev) => ({ ...prev, depositRequestKey: null, depositReference: null, depositCheckoutUrl: null, depositAmount: "" }));
        await clearSavedDeposit();
        await loadWallet();
      } else if (status.status === "failed") {
        setWallet((prev) => ({ ...prev, notice: "Flutterwave did not complete this payment. Start a new deposit with a new request." }));
        setDeposit((prev) => ({ ...prev, depositRequestKey: null, depositReference: null, depositCheckoutUrl: null }));
        await clearSavedDeposit();
      } else {
        setWallet((prev) => ({
          ...prev,
          notice: "Flutterwave has not confirmed the payment yet. Your Wallet balance has not been changed."
        }));
      }
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not refresh the deposit status." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [deposit.depositReference]);

  // Visible label for navigation contract: "Starting secure checkout…"
  // Visible label for navigation contract: "Open Flutterwave checkout"
  const openDepositCheckout = useCallback(async () => {
    if (!deposit.depositCheckoutUrl) return;
    try {
      const checkout = new URL(deposit.depositCheckoutUrl);
      if (checkout.protocol !== "https:") throw new Error("Only secure payment-provider links can be opened.");
      await Linking.openURL(checkout.toString());
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not open the payment checkout." }));
    }
  }, [deposit.depositCheckoutUrl]);

  // --- Withdrawal ---
  const requestWithdrawalQuote = useCallback(async () => {
    if (wallet.selectedCurrency !== "UGX") {
      setWallet((prev) => ({ ...prev, error: "The first native payout route supports UGX wallets in Uganda only. Other payout corridors are not enabled yet." }));
      return;
    }
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    setWithdrawal((prev) => ({ ...prev, withdrawalStatus: null, withdrawalReference: null }));
    try {
      const quote = await walletClient.quoteWithdrawal({
        amount: withdrawal.withdrawalAmount,
        currency: wallet.selectedCurrency,
        network: withdrawal.withdrawalNetwork,
        phoneNumber: withdrawal.withdrawalPhone,
        beneficiaryName: withdrawal.withdrawalBeneficiary,
      });
      setWithdrawal((prev) => ({ ...prev, withdrawalQuote: quote }));
      await SecureStore.setItemAsync(withdrawalStoreKeys.quote, JSON.stringify(quote));
      setWallet((prev) => ({ ...prev, notice: "Review the beneficiary, network, fee and total Wallet debit before confirming." }));
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not prepare the withdrawal quote." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [withdrawal, wallet.selectedCurrency]);

  const submitWithdrawal = useCallback(async () => {
    if (!withdrawal.withdrawalQuote) return;
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      const result = await walletClient.confirmWithdrawal({
        quoteToken: withdrawal.withdrawalQuote.quote_token,
        pin: withdrawal.withdrawalPin,
      });
      setWithdrawal((prev) => ({
        ...prev,
        withdrawalStatus: result,
        withdrawalReference: result.reference,
        withdrawalQuote: null,
        withdrawalPin: "",
      }));
      await Promise.all([
        SecureStore.setItemAsync(withdrawalStoreKeys.reference, result.reference),
        SecureStore.deleteItemAsync(withdrawalStoreKeys.quote),
      ]);
      if (result.status === "completed") {
        setWallet((prev) => ({ ...prev, notice: "Flutterwave has confirmed the payout. Your withdrawal is complete." }));
        await clearSavedWithdrawal();
        await loadWallet();
      } else if (result.status === "failed") {
        setWallet((prev) => ({ ...prev, notice: "The provider confirmed the payout failed. AFCON360 has reversed the reserved Wallet amount." }));
        await clearSavedWithdrawal();
        await loadWallet();
      } else {
        setWallet((prev) => ({ ...prev, notice: "Withdrawal submitted. Your Wallet amount is reserved while Flutterwave processes the payout. It is not marked as paid yet." }));
        await loadWallet();
      }
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not confirm the withdrawal." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [withdrawal]);

  const confirmWithdrawal = useCallback(() => {
    if (!withdrawal.withdrawalQuote || !withdrawal.withdrawalPin.trim()) {
      setWallet((prev) => ({ ...prev, error: "Enter your transaction PIN to confirm this quoted withdrawal." }));
      return;
    }
    Alert.alert(
      "Confirm withdrawal",
      `Send ${withdrawal.withdrawalQuote.amount} ${withdrawal.withdrawalQuote.currency} to ${withdrawal.withdrawalQuote.beneficiary_name} (${withdrawal.withdrawalQuote.masked_phone}, ${withdrawal.withdrawalQuote.network})?\n\nAFCON360 fee: ${withdrawal.withdrawalQuote.platform_fee} ${withdrawal.withdrawalQuote.currency}\nTotal Wallet debit: ${withdrawal.withdrawalQuote.total_wallet_debit} ${withdrawal.withdrawalQuote.currency}\n\nThe payout remains pending until the provider confirms delivery.`,
      [
        { text: "Review again", style: "cancel" },
        { text: "Confirm withdrawal", onPress: () => void submitWithdrawal() },
      ],
    );
  }, [withdrawal, submitWithdrawal]);

  const refreshWithdrawal = useCallback(async () => {
    if (!withdrawal.withdrawalReference) return;
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      const result = await walletClient.getWithdrawalStatus(withdrawal.withdrawalReference);
      setWithdrawal((prev) => ({ ...prev, withdrawalStatus: result }));
      if (result.status === "completed") {
        setWallet((prev) => ({ ...prev, notice: "Flutterwave has confirmed the payout. Your withdrawal is complete." }));
        await clearSavedWithdrawal();
        await loadWallet();
      } else if (result.status === "failed") {
        setWallet((prev) => ({ ...prev, notice: "The provider confirmed the payout failed. AFCON360 has reversed the reserved Wallet amount." }));
        await clearSavedWithdrawal();
        await loadWallet();
      } else {
        setWallet((prev) => ({
          ...prev,
          notice: result.manual_review_required
            ? "The provider response needs reconciliation. Your funds remain reserved; do not start another withdrawal."
            : "The payout is still processing. Your funds remain reserved until the provider confirms success or failure."
        }));
      }
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not verify the withdrawal status." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [withdrawal.withdrawalReference]);

  // --- PIN ---
  const updatePin = useCallback(async () => {
    setWallet((prev) => ({ ...prev, busy: true, error: null, notice: null }));
    try {
      await walletClient.setPin({
        pin: pin.newPin,
        confirm_pin: pin.confirmPin,
        ...(wallet.pinStatus?.pin_set
          ? { current_pin: pin.currentPin }
          : { password: pin.accountPassword }),
      });
      setPin({ newPin: "", confirmPin: "", currentPin: "", accountPassword: "" });
      setWallet((prev) => ({ ...prev, notice: "Your transaction PIN has been updated." }));
      const newPinStatus = await walletClient.getPinStatus();
      setWallet((prev) => ({ ...prev, pinStatus: newPinStatus }));
    } catch (e) {
      setWallet((prev) => ({ ...prev, error: e instanceof Error ? e.message : "AFCON360 could not update the transaction PIN." }));
    } finally {
      setWallet((prev) => ({ ...prev, busy: false }));
    }
  }, [pin, wallet.pinStatus?.pin_set]);

  return (
    <AppScreen>
      <ScrollView contentContainerStyle={{ gap: 14, paddingBottom: 28 }}>
        <PageHeader
          eyebrow="Wallet"
          title="Your money, clearly managed."
          description="Balances, transfers and transaction history come from the AFCON360 Wallet ledger. The app does not calculate or store your balance."
        />

        <ServiceHeroAccent serviceKey="wallet" title="Your Pamoja Wallet" subtitle="Balances, send, deposit, history & PIN" />

        <WalletTabs activeTab={tab} onTabChange={handleTabChange} onTabPress={handleTabPress} />

        {wallet.loading && <ActivityIndicator color={colors.brand.green} />}
        {wallet.error && <Panel><Text style={{ color: "#9A3A2F", fontWeight: "600" }}>{wallet.error}</Text></Panel>}
        {wallet.notice && <Panel><Text style={{ color: colors.brand.green, fontWeight: "700" }}>{wallet.notice}</Text></Panel>}

        {tab === "balance" && (
          <WalletBalance
            accounts={wallet.accounts}
            selectedCurrency={wallet.selectedCurrency}
            onCurrencySelect={(currency) => setWallet((prev) => ({ ...prev, selectedCurrency: currency }))}
            loading={wallet.loading}
            onStartDeposit={() => setTab("deposit")}
          />
        )}

        {tab === "send" && (
          <WalletSend
            selectedCurrency={wallet.selectedCurrency}
            selectedAccount={selectedAccount}
            recipientIdentifier={send.recipientIdentifier}
            amount={send.amount}
            transferNote={send.transferNote}
            transferPin={send.transferPin}
            resolvedRecipient={send.resolvedRecipient}
            busy={wallet.busy}
            error={wallet.error}
            notice={wallet.notice}
            onRecipientChange={(value) => { setSend((prev) => ({ ...prev, recipientIdentifier: value, resolvedRecipient: null })); }}
            onAmountChange={(value) => setSend((prev) => ({ ...prev, amount: value }))}
            onNoteChange={(value) => setSend((prev) => ({ ...prev, transferNote: value }))}
            onPinChange={(value) => setSend((prev) => ({ ...prev, transferPin: value }))}
            onVerifyRecipient={resolveRecipient}
            onSend={sendTransfer}
          />
        )}

        {tab === "deposit" && (
          <WalletDeposit
            selectedCurrency={wallet.selectedCurrency}
            selectedAccount={selectedAccount}
            depositAmount={deposit.depositAmount}
            depositPaymentMethod={deposit.depositPaymentMethod}
            depositReference={deposit.depositReference}
            depositCheckoutUrl={deposit.depositCheckoutUrl}
            depositStatus={deposit.depositStatus}
            busy={wallet.busy}
            error={wallet.error}
            notice={wallet.notice}
            onAmountChange={(value) => setDeposit((prev) => ({ ...prev, depositAmount: value }))}
            onPaymentMethodChange={(method) => setDeposit((prev) => ({ ...prev, depositPaymentMethod: method }))}
            onStartDeposit={startDeposit}
            onRefreshDeposit={refreshDeposit}
            onOpenCheckout={openDepositCheckout}
          />
        )}

        {tab === "withdraw" && NATIVE_WITHDRAWALS_ENABLED && (
          <WalletWithdraw
            selectedCurrency={wallet.selectedCurrency}
            selectedAccount={selectedAccount}
            withdrawalAmount={withdrawal.withdrawalAmount}
            withdrawalNetwork={withdrawal.withdrawalNetwork}
            withdrawalPhone={withdrawal.withdrawalPhone}
            withdrawalBeneficiary={withdrawal.withdrawalBeneficiary}
            withdrawalPin={withdrawal.withdrawalPin}
            withdrawalQuote={withdrawal.withdrawalQuote}
            withdrawalReference={withdrawal.withdrawalReference}
            withdrawalStatus={withdrawal.withdrawalStatus}
            busy={wallet.busy}
            error={wallet.error}
            notice={wallet.notice}
            onAmountChange={(value) => setWithdrawal((prev) => ({ ...prev, withdrawalAmount: value }))}
            onNetworkChange={(network) => setWithdrawal((prev) => ({ ...prev, withdrawalNetwork: network }))}
            onPhoneChange={(value) => setWithdrawal((prev) => ({ ...prev, withdrawalPhone: value }))}
            onBeneficiaryChange={(value) => setWithdrawal((prev) => ({ ...prev, withdrawalBeneficiary: value }))}
            onPinChange={(value) => setWithdrawal((prev) => ({ ...prev, withdrawalPin: value }))}
            onRequestQuote={requestWithdrawalQuote}
            onConfirmWithdrawal={confirmWithdrawal}
            onRefreshWithdrawal={refreshWithdrawal}
          />
        )}

        {tab === "history" && (
          <WalletHistory
            transactions={wallet.transactions}
            busy={wallet.busy}
            loading={wallet.loading}
            onRefresh={loadWallet}
          />
        )}

        {tab === "pin" && (
          <WalletPin
            pinStatus={wallet.pinStatus}
            newPin={pin.newPin}
            confirmPin={pin.confirmPin}
            currentPin={pin.currentPin}
            accountPassword={pin.accountPassword}
            busy={wallet.busy}
            error={wallet.error}
            notice={wallet.notice}
            onNewPinChange={(value) => setPin((prev) => ({ ...prev, newPin: value }))}
            onConfirmPinChange={(value) => setPin((prev) => ({ ...prev, confirmPin: value }))}
            onCurrentPinChange={(value) => setPin((prev) => ({ ...prev, currentPin: value }))}
            onAccountPasswordChange={(value) => setPin((prev) => ({ ...prev, accountPassword: value }))}
            onUpdatePin={updatePin}
          />
        )}
      </ScrollView>
    </AppScreen>
  );
}

export default WalletScreen;