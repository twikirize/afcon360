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

export type WalletTab = "balance" | "deposit" | "send" | "withdraw" | "history" | "pin";

export type WalletState = {
  accounts: WalletAccount[];
  transactions: WalletTransaction[];
  pinStatus: WalletPinStatus | null;
  selectedCurrency: string;
  loading: boolean;
  busy: boolean;
  error: string | null;
  notice: string | null;
};

export type SendState = {
  recipientIdentifier: string;
  amount: string;
  transferNote: string;
  transferPin: string;
  resolvedRecipient: ResolvedWalletRecipient | null;
  transferRequestKey: string | null;
};

export type DepositState = {
  depositAmount: string;
  depositPaymentMethod: "mobilemoney" | "card";
  depositRequestKey: string | null;
  depositReference: string | null;
  depositCheckoutUrl: string | null;
  depositStatus: WalletDepositStatus | null;
};

export type WithdrawalState = {
  withdrawalAmount: string;
  withdrawalNetwork: WalletWithdrawalNetwork;
  withdrawalPhone: string;
  withdrawalBeneficiary: string;
  withdrawalPin: string;
  withdrawalQuote: WalletWithdrawalQuote | null;
  withdrawalReference: string | null;
  withdrawalStatus: WalletWithdrawalStatus | null;
};

export type PinState = {
  newPin: string;
  confirmPin: string;
  currentPin: string;
  accountPassword: string;
};

export const depositStoreKeys = {
  request: "afcon360.user.wallet.deposit.request",
  reference: "afcon360.user.wallet.deposit.reference",
  checkout: "afcon360.user.wallet.deposit.checkout",
  amount: "afcon360.user.wallet.deposit.amount",
  currency: "afcon360.user.wallet.deposit.currency",
  method: "afcon360.user.wallet.deposit.method",
} as const;

export const withdrawalStoreKeys = {
  quote: "afcon360.user.wallet.withdrawal.quote",
  reference: "afcon360.user.wallet.withdrawal.reference",
} as const;

export const NATIVE_WITHDRAWALS_ENABLED = false;

export function formatDate(value: string | null): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}

export function formatMoney(amount: number | string, currency: string): string {
  const code = (currency || "USD").toUpperCase();
  const digits = ["UGX", "RWF", "JPY", "KRW", "VND"].includes(code) ? 0 : 2;
  const num = Number(amount);
  if (!Number.isFinite(num)) return `${amount} ${code}`;
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: code,
      currencyDisplay: "code",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    }).format(num);
  } catch {
    return code + " " + num.toFixed(digits);
  }
}

export function newIdempotencyKey(): string {
  return "mobile-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
}