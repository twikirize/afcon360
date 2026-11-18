import type { RequestOptions } from "../api/client";

export type NativeEventSummary = {
  public_id: string;
  slug: string;
  name: string;
  description: string;
  category: string;
  city: string;
  country: string;
  venue: string | null;
  start_date: string | null;
  end_date: string | null;
  currency: string;
  featured: boolean;
  registration_required: boolean;
  registration_fee: string;
  website: string | null;
};

export type NativeEventTicketType = {
  ticket_token: string;
  name: string;
  description: string;
  price: string;
  currency: string;
  capacity_limited: boolean;
  remaining: number | null;
  available_from: string | null;
  available_until: string | null;
  is_available_now: boolean;
};

export type NativeEventDetail = NativeEventSummary & {
  ticket_availability: NativeEventTicketType[];
  registration: {
    state: string;
    message: string;
    opens_at: string | null;
    closes_at: string | null;
    remaining_capacity: number | null;
  };
};

export type NativeEventList = {
  items: NativeEventSummary[];
  limit: number;
  offset: number;
  has_more: boolean;
};

export type NativeEventRegistration = {
  registration_reference: string;
  ticket_number: string;
  qr_code: string;
  event: {
    public_id: string | null;
    name: string | null;
    city: string | null;
    country: string | null;
    start_date: string | null;
    end_date: string | null;
  };
  ticket_type: string;
  attendee_name: string;
  status: string;
  payment_status: string;
  amount: string;
  currency: string;
  created_at: string | null;
};

export type NativeEventRegistrationList = {
  items: NativeEventRegistration[];
  limit: number;
  offset: number;
};

type Envelope<T> = {
  success: boolean;
  code?: string;
  message?: string;
  data?: T;
};

export type NativeEventRequestClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
};

export class MobileEventClient {
  constructor(private readonly api: NativeEventRequestClient) {}

  private async unwrap<T>(path: string, options?: RequestOptions): Promise<T> {
    const response = await this.api.request<Envelope<T>>(path, options);
    if (!response.success || response.data === undefined) {
      const error = new Error(response.message ?? "AFCON360 could not complete the event request.");
      Object.assign(error, { code: response.code });
      throw error;
    }
    return response.data;
  }

  listEvents(input: { query?: string; city?: string; country?: string; category?: string; limit?: number; offset?: number } = {}): Promise<NativeEventList> {
    const params = new URLSearchParams();
    if (input.query) params.set("q", input.query);
    if (input.city) params.set("city", input.city);
    if (input.country) params.set("country", input.country);
    if (input.category) params.set("category", input.category);
    params.set("limit", String(input.limit ?? 20));
    params.set("offset", String(input.offset ?? 0));
    return this.unwrap<NativeEventList>(`/api/mobile/v1/events?${params.toString()}`);
  }

  getEvent(publicId: string): Promise<NativeEventDetail> {
    return this.unwrap<NativeEventDetail>(
      `/api/mobile/v1/events/${encodeURIComponent(publicId)}`
    );
  }

  registerFreeTicket(eventPublicId: string, ticketToken: string): Promise<NativeEventRegistration> {
    return this.unwrap<NativeEventRegistration>(
      `/api/mobile/v1/events/${encodeURIComponent(eventPublicId)}/registrations`,
      {
        method: "POST",
        body: { ticket_token: ticketToken },
      }
    );
  }

  listRegistrations(limit = 20, offset = 0): Promise<NativeEventRegistrationList> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return this.unwrap<NativeEventRegistrationList>(`/api/mobile/v1/events/registrations?${params.toString()}`);
  }

  getRegistration(reference: string): Promise<NativeEventRegistration> {
    return this.unwrap<NativeEventRegistration>(
      `/api/mobile/v1/events/registrations/${encodeURIComponent(reference)}`
    );
  }
}
