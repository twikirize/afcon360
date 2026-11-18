import React, { useState, useEffect, useRef } from "react";
import { Alert, ActivityIndicator, Pressable, Text, TextInput, View, StyleSheet } from "react-native";
import { colors, spacing, radii, typography } from "../theme/tokens";
import {
  PamojaActionButton as ActionButton,
  PamojaPanel as Panel,
  PamojaSectionTitle as SectionTitle,
  PamojaStatusPill as StatusPill,
} from "../PamojaScreen";
import { walletClient, eventClient } from "../../src/services/api";
import type { NativeEventTicketType, NativeEventDetail } from "@afcon360/mobile-core";
import type { WalletAccount } from "@afcon360/mobile-core";

type TicketPurchaseProps = {
  event: NativeEventDetail;
  ticket: NativeEventTicketType;
  selectedAccount: WalletAccount | undefined;
  busy: boolean;
  onClose: () => void;
  onPurchase: (ticket: NativeEventTicketType) => void;
  onSetBusy: (busy: boolean) => void;
};

type PurchaseResponse =
  | { status: "completed"; registration_reference: string; ticket_number: string; qr_code: string; amount: string; currency: string; payment_reference: string; status: string }
  | { status: "pending"; message: string; reference: string; provider_reference: string; audit_transaction_id: string; expires_in: number };

export function TicketPurchase({ event, ticket, selectedAccount, busy, onClose, onPurchase, onSetBusy }: TicketPurchaseProps) {
  const [paymentMethod, setPaymentMethod] = useState<string>("");
  const [loadingPaymentMethods, setLoadingPaymentMethods] = useState(false);
  const [paymentMethods, setPaymentMethods] = useState<Array<{ code: string; label: string; status: string; status_message?: string }>>([]);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const [mobileMoneyOperator, setMobileMoneyOperator] = useState<string>("");
  const [mobileMoneyPhone, setMobileMoneyPhone] = useState<string>("");
  const [pendingPayment, setPendingPayment] = useState<{ reference: string; expiresAt: number } | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!ticket.currency) return;
    loadPaymentMethods();
  }, [ticket.currency]);

  const loadPaymentMethods = async () => {
    setLoadingPaymentMethods(true);
    setPaymentError(null);
    try {
      const response = await walletClient.request<{ success: boolean; data?: { payment_methods?: Array<{ code: string; label: string; status: string; status_message?: string }> } }>(
        "/api/mobile/v1/transport/payment-methods/options",
        {
          method: "POST",
          body: {
            currency: ticket.currency,
            amount: Number(ticket.price),
          },
        }
      );
      setPaymentMethods(response.data?.payment_methods ?? []);
      if (!(response.data?.payment_methods ?? []).some((m) => m.status === "ready")) {
        setPaymentError("No payment method is currently certified and ready for this exact fare. Return to your Wallet setup or choose another available method.");
      }
    } catch (e) {
      setPaymentError(e instanceof Error ? e.message : "AFCON360 could not check payment readiness.");
    } finally {
      setLoadingPaymentMethods(false);
    }
  };

  const clearPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    setPendingPayment(null);
  };

  const pollForRegistration = async (reference: string, expiresAt: number) => {
    const checkRegistration = async () => {
      if (Date.now() > expiresAt) {
        clearPolling();
        setError("Payment timed out. Please try again.");
        return;
      }
      try {
        const result = await eventClient.listRegistrations(5, 0);
        const registration = result.items?.find((r) => r.registration_reference === reference);
        if (registration) {
          clearPolling();
          setNotice(`Your paid ticket is confirmed. Reference: ${registration.registration_reference}.`);
          setVisibleTicket(registration.registration_reference);
          onPurchase(ticket);
        }
      } catch (e) {
        // Continue polling on error
      }
    };

    // Check immediately
    await checkRegistration();

    // Poll every 3 seconds
    pollIntervalRef.current = setInterval(checkRegistration, 3000);
  };

  const handlePurchase = async () => {
    if (!paymentMethod || !pin.trim()) return;
    onSetBusy(true);
    try {
      const idempotencyKey = "native-event-purchase-" + Date.now().toString(36);
      const result = await eventClient.purchaseTicket({
        eventPublicId: event.public_id,
        ticketToken: ticket.ticket_token,
        paymentMethod,
        mobileMoneyOperator: paymentMethod === "mobile_money" ? mobileMoneyOperator : undefined,
        mobileMoneyPhone: paymentMethod === "mobile_money" ? mobileMoneyPhone : undefined,
        idempotencyKey,
      });

      // Handle pending status (mobile money)
      if ("status" in result && result.status === "pending") {
        onSetBusy(false);
        const expiresAt = Date.now() + (result.expires_in || 300) * 1000;
        setPendingPayment({ reference: result.reference, expiresAt });
        setNotice(result.message);
        await pollForRegistration(result.reference, Date.now() + (result.expires_in || 300) * 1000);
        return;
      }

      // Completed (wallet payment)
      onSetBusy(false);
      setNotice(`Your paid ticket is confirmed. Reference: ${result.registration_reference}.`);
      setVisibleTicket(result.registration_reference);
      onPurchase(ticket);
    } catch (e) {
      onSetBusy(false);
      setError(serviceErrorMessage(e, "Events"));
    }
  };

  useEffect(() => {
    return () => clearPolling();
  }, []);

  const isFree = Number(ticket.price) <= 0;
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [visibleTicket, setVisibleTicket] = useState<string | null>(null);

  return (
    <Panel>
      <SectionTitle>Purchase Ticket</SectionTitle>
      <Text style={{ color: colors.text.ink, fontWeight: "900", fontSize: 18 }}>{ticket.name}</Text>
      <Text style={{ color: colors.text.muted }}>{event.name}</Text>
      <Text style={{ color: colors.text.ink, fontWeight: "800", fontSize: 16 }}>{isFree ? "Free" : ticketPrice(ticket)}</Text>

      {error && <Text style={styles.errorText}>{error}</Text>}
      {notice && <Text style={{ color: colors.brand.green, fontWeight: "700" }}>{notice}</Text>}

      {!isFree && (
        <>
          <Text style={styles.label}>Wallet balance: {selectedAccount ? selectedAccount.balance + " " + selectedAccount.currency : "No matching Wallet"}</Text>
          <StatusPill tone={selectedAccount && !selectedAccount.is_frozen ? "green" : "gold"}>
            {selectedAccount && !selectedAccount.is_frozen ? "Wallet available" : "Wallet not available"}
          </StatusPill>

          <Text style={styles.label}>Select payment method</Text>
          {loadingPaymentMethods ? <ActivityIndicator color={colors.brand.green} /> : null}
          {paymentError && <Text style={styles.errorText}>{paymentError}</Text>}
          {paymentMethods.map((method) => {
            const ready = method.status === "ready";
            const selected = paymentMethod === method.code;
            return (
              <Pressable
                key={method.code}
                accessibilityRole="radio"
                accessibilityState={{ checked: selected, disabled: !ready }}
                disabled={!ready}
                onPress={() => setPaymentMethod(method.code)}
                style={[
                  styles.paymentChoice,
                  selected && styles.paymentSelected,
                  !ready && styles.disabled,
                ]}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <View style={[styles.radio, selected && styles.radioSelected]} />
                <View style={styles.paymentCopy}>
                  <Text style={styles.paymentName}>{method.label}</Text>
                  <Text style={styles.helperText}>
                    {ready ? "Ready for this fare" : method.status_message ?? method.status.replace(/_/g, " ")}
                  </Text>
                </View>
              </Pressable>
            );
          })}
          {!loadingPaymentMethods && paymentMethods.length === 0 && !paymentError && (
            <Text style={styles.helperText}>No payment methods were returned for this fare.</Text>
          )}

          {paymentMethod === "mobile_money" && (
            <>
              <Text style={styles.label}>Mobile money operator</Text>
              <TextInput
                value={mobileMoneyOperator}
                onChangeText={setMobileMoneyOperator}
                placeholder="MTN, Airtel, etc."
                style={styles.input}
              />
              <Text style={styles.label}>Mobile money phone</Text>
              <TextInput
                value={mobileMoneyPhone}
                onChangeText={setMobileMoneyPhone}
                placeholder="07XXXXXXXX"
                keyboardType="phone-pad"
                style={styles.input}
              />
            </>
          )}

          <Text style={styles.label}>Transaction PIN</Text>
          <TextInput
            value={pin}
            onChangeText={setPin}
            placeholder="Enter your 4–6 digit PIN"
            secureTextEntry
            keyboardType="numeric"
            style={styles.pinInput}
          />

          <ActionButton
            label={busy ? "Processing…" : `Confirm and pay ${ticketPrice(ticket)}`}
            disabled={busy || !paymentMethod || !pin.trim() || !selectedAccount || selectedAccount.is_frozen}
            onPress={handlePurchase}
          />
        </>
      )}

      {isFree && (
        <ActionButton
          label={busy ? "Registering…" : "Register for free"}
          disabled={busy}
          onPress={() => onPurchase(ticket)}
        />
      )}

      <Pressable onPress={onClose} style={styles.secondaryButton} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
        <Text style={styles.secondaryButtonText}>Cancel</Text>
      </Pressable>
    </Panel>
  );
}

function ticketPrice(ticket: NativeEventTicketType): string {
  const amount = Number(ticket.price);
  if (Number.isFinite(amount) && amount <= 0) return "Free";
  if (!Number.isFinite(amount)) return `${ticket.price} ${ticket.currency}`;
  return `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${ticket.currency}`;
}

const styles = StyleSheet.create({
  label: { color: colors.text.ink, fontWeight: "700", fontSize: 13, marginTop: spacing.lg },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
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
  paymentChoice: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
  },
  paymentSelected: { borderColor: colors.brand.green, borderWidth: 2, backgroundColor: colors.brand.greenSoft },
  disabled: { opacity: 0.5, backgroundColor: colors.surface.canvas },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface.white },
  radioSelected: { borderColor: colors.brand.green, backgroundColor: colors.brand.green },
  paymentCopy: { flex: 1, gap: 2 },
  paymentName: { color: colors.text.ink, fontSize: 15, fontWeight: "800" },
  pinInput: {
    backgroundColor: colors.surface.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  pinField: { color: colors.text.ink, fontSize: 15 },
  secondaryButton: { alignSelf: "center", marginTop: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg },
  secondaryButtonText: { color: colors.brand.green, fontSize: 13, fontWeight: "800" },
});

export default TicketPurchase;

function ticketPrice(ticket: NativeEventTicketType): string {
  const amount = Number(ticket.price);
  if (Number.isFinite(amount) && amount <= 0) return "Free";
  if (!Number.isFinite(amount)) return `${ticket.price} ${ticket.currency}`;
  return `${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${ticket.currency}`;
}

const styles = StyleSheet.create({
  label: { color: colors.text.ink, fontWeight: "700", fontSize: 13, marginTop: spacing.lg },
  errorText: { color: colors.status.error, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  helperText: { color: colors.text.muted, fontSize: typography.caption.fontSize, lineHeight: typography.caption.lineHeight },
  paymentChoice: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    backgroundColor: colors.surface.white,
  },
  paymentSelected: { borderColor: colors.brand.green, borderWidth: 2, backgroundColor: colors.brand.greenSoft },
  disabled: { opacity: 0.5, backgroundColor: colors.surface.canvas },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface.white },
  radioSelected: { borderColor: colors.brand.green, backgroundColor: colors.brand.green },
  paymentCopy: { flex: 1, gap: 2 },
  paymentName: { color: colors.text.ink, fontSize: 15, fontWeight: "800" },
  pinInput: { backgroundColor: colors.surface.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, padding: spacing.md },
  pinField: { color: colors.text.ink, fontSize: 15 },
  secondaryButton: { alignSelf: "center", marginTop: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg },
  secondaryButtonText: { color: colors.brand.green, fontSize: 13, fontWeight: "800" },
});

export default TicketPurchase;