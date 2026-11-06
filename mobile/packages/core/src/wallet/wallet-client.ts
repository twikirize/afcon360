import type { RequestOptions } from "../api/client";

export type WalletAccount = {
  currency: string;
  balance: string;
  is_frozen: boolean;
  status: string;
};

export type WalletSummary = {
  exists: boolean;
  accounts: WalletAccount[];
};

export type WalletTransaction = {
  reference: string;
  type: string;
  direction: "sent" | "received";
  amount: string;
  currency: string;
  status: string;
  created_at: string | null;
};

export type WalletTransactions = {
  items: WalletTransaction[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type WalletPinStatus = {
  pin_set: boolean;
  locked: boolean;
};

export type ResolvedWalletRecipient = {
  display_name: string;
  masked_identifier: string;
  recipient_currency: string;
};

export type WalletDepositStartResult = {
  reference: string;
  status: "pending" | "completed" | "failed";
  amount: string;
  currency: string;
  payment_provider?: string;
  authorization_url: string | null;
  message?: string;
};

export type WalletDepositStatus = {
  reference: string;
  status: "pending" | "completed" | "failed";
  amount: string;
  currency: string;
  payment_provider?: string;
  message?: string;
};

export type WalletTransferResult = {
  reference: string;
  amount: string;
  currency: string;
  received_amount: string;
  received_currency: string;
  recipient_display_name: string;
  new_balance: string;
  already_processed: boolean;
};

type Envelope<T> = {
  success: boolean;
  code?: string;
  message?: string;
  data?: T;
};

export type WalletRequestClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
};

export class MobileWalletClient {
  constructor(private readonly api: WalletRequestClient) {}

  private async unwrap<T>(path: string, options?: RequestOptions): Promise<T> {
    const response = await this.api.request<Envelope<T>>(path, options);
    if (!response.success || response.data === undefined) {
      throw new Error(response.message ?? "AFCON360 could not complete the wallet request.");
    }
    return response.data;
  }

  getSummary(): Promise<WalletSummary> {
    return this.unwrap<WalletSummary>("/api/mobile/v1/wallet");
  }

  getTransactions(limit = 30, offset = 0): Promise<WalletTransactions> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    return this.unwrap<WalletTransactions>(`/api/mobile/v1/wallet/transactions?${params.toString()}`);
  }

  getPinStatus(): Promise<WalletPinStatus> {
    return this.unwrap<WalletPinStatus>("/api/mobile/v1/wallet/pin");
  }

  setPin(input: {
    pin: string;
    confirm_pin: string;
    current_pin?: string;
    password?: string;
  }): Promise<{ pin_set: boolean }> {
    return this.unwrap<{ pin_set: boolean }>("/api/mobile/v1/wallet/pin", {
      method: "POST",
      body: input,
    });
  }


  startDeposit(input: {
    amount: string;
    currency: string;
    paymentMethod: "mobilemoney" | "card" | "banktransfer" | "ussd";
    idempotencyKey: string;
  }): Promise<WalletDepositStartResult> {
    return this.unwrap<WalletDepositStartResult>("/api/mobile/v1/wallet/deposits", {
      method: "POST",
      headers: { "X-Idempotency-Key": input.idempotencyKey },
      body: {
        amount: input.amount,
        currency: input.currency.toUpperCase(),
        payment_method: input.paymentMethod,
      },
    });
  }

  getDepositStatus(reference: string): Promise<WalletDepositStatus> {
    return this.unwrap<WalletDepositStatus>(
      `/api/mobile/v1/wallet/deposits/${encodeURIComponent(reference)}`
    );
  }

  refreshDepositStatus(reference: string): Promise<WalletDepositStatus> {
    return this.unwrap<WalletDepositStatus>(
      `/api/mobile/v1/wallet/deposits/${encodeURIComponent(reference)}/refresh`,
      { method: "POST" }
    );
  }

  resolveRecipient(identifier: string, currency: string): Promise<ResolvedWalletRecipient> {
    return this.unwrap<ResolvedWalletRecipient>("/api/mobile/v1/wallet/recipients/resolve", {
      method: "POST",
      body: { identifier: identifier.trim(), currency: currency.toUpperCase() },
    });
  }

  transfer(input: {
    identifier: string;
    amount: string;
    currency: string;
    pin: string;
    note?: string;
    idempotencyKey: string;
  }): Promise<WalletTransferResult> {
    return this.unwrap<WalletTransferResult>("/api/mobile/v1/wallet/transfers", {
      method: "POST",
      headers: { "X-Idempotency-Key": input.idempotencyKey },
      body: {
        identifier: input.identifier.trim(),
        amount: input.amount,
        currency: input.currency.toUpperCase(),
        pin: input.pin,
        note: input.note?.trim() ?? "",
      },
    });
  }
}
