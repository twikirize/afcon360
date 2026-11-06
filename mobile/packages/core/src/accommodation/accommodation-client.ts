import type { RequestOptions } from "../api/client";

export type AccommodationRoomType = {
  room_token: string;
  name: string;
  description: string | null;
  max_guests: number;
  bedrooms: number;
  beds: number;
  bathrooms: number;
  base_price_per_night: string;
  currency: string;
  total_units: number;
};

export type AccommodationProperty = {
  public_id: string;
  title: string;
  summary: string | null;
  description?: string;
  city: string;
  state: string | null;
  country: string;
  address?: string;
  property_type: string;
  listing_type: string;
  currency: string;
  starting_price: string;
  max_guests: number;
  main_image: string | null;
  rating: number;
  review_count: number;
  featured: boolean;
  verified: boolean;
  room_types: AccommodationRoomType[];
  cancellation_policy?: string;
  house_rules?: string | null;
};

export type AccommodationPropertyList = {
  items: AccommodationProperty[];
  limit: number;
  offset: number;
  has_more: boolean;
};

export type AccommodationBookingQuote = {
  quote_id: string;
  quote_token: string;
  property: AccommodationProperty;
  check_in: string;
  check_out: string;
  num_guests: number;
  rooms_requested: number;
  nights: number;
  currency: string;
  nightly_rate: string;
  subtotal: string;
  cleaning_fee: string;
  service_fee: string;
  taxes: string;
  total: string;
  wallet_available_balance: string | null;
  wallet_payment_available: boolean;
  expires_at: string;
};

export type AccommodationBooking = {
  booking_reference: string;
  property: {
    public_id: string | null;
    title: string | null;
    city: string | null;
    country: string | null;
    image: string | null;
  };
  check_in: string | null;
  check_out: string | null;
  nights: number;
  num_guests: number;
  rooms_requested: number;
  amount: string;
  currency: string;
  payment_status: string;
  status: string;
  payment_method: string | null;
  cancellation_policy: string | null;
  created_at: string | null;
};

export type AccommodationBookingList = {
  items: AccommodationBooking[];
  limit: number;
  offset: number;
};

export type AccommodationCancelResult = {
  booking: AccommodationBooking;
  cancellation_message: string;
  refund: {
    status: "completed" | "needs_reconciliation";
    amount: string;
    currency: string;
    error: string | null;
  } | null;
};

type Envelope<T> = {
  success: boolean;
  code?: string;
  message?: string;
  data?: T;
};

export type AccommodationRequestClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>;
};

export class MobileAccommodationClient {
  constructor(private readonly api: AccommodationRequestClient) {}

  private async unwrap<T>(path: string, options?: RequestOptions): Promise<T> {
    const response = await this.api.request<Envelope<T>>(path, options);
    if (!response.success || response.data === undefined) {
      throw new Error(response.message ?? "AFCON360 could not complete the accommodation request.");
    }
    return response.data;
  }

  listProperties(input: { query?: string; city?: string; country?: string; limit?: number; offset?: number } = {}): Promise<AccommodationPropertyList> {
    const params = new URLSearchParams();
    if (input.query) params.set("q", input.query);
    if (input.city) params.set("city", input.city);
    if (input.country) params.set("country", input.country);
    params.set("limit", String(input.limit ?? 20));
    params.set("offset", String(input.offset ?? 0));
    return this.unwrap<AccommodationPropertyList>(`/api/mobile/v1/accommodation/properties?${params.toString()}`);
  }

  getProperty(publicId: string): Promise<AccommodationProperty> {
    return this.unwrap<AccommodationProperty>(
      `/api/mobile/v1/accommodation/properties/${encodeURIComponent(publicId)}`
    );
  }

  quoteBooking(input: {
    propertyPublicId: string;
    checkIn: string;
    checkOut: string;
    numGuests: number;
    roomsRequested: number;
    roomTypeToken?: string | null;
  }): Promise<AccommodationBookingQuote> {
    return this.unwrap<AccommodationBookingQuote>("/api/mobile/v1/accommodation/quotes", {
      method: "POST",
      body: {
        property_public_id: input.propertyPublicId,
        check_in: input.checkIn,
        check_out: input.checkOut,
        num_guests: input.numGuests,
        rooms_requested: input.roomsRequested,
        room_type_token: input.roomTypeToken ?? null,
      },
    });
  }

  createWalletBooking(input: { quoteToken: string; pin: string; specialRequests?: string }): Promise<AccommodationBooking> {
    return this.unwrap<AccommodationBooking>("/api/mobile/v1/accommodation/bookings", {
      method: "POST",
      body: {
        quote_token: input.quoteToken,
        pin: input.pin,
        special_requests: input.specialRequests ?? "",
      },
    });
  }

  listBookings(limit = 20, offset = 0): Promise<AccommodationBookingList> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    return this.unwrap<AccommodationBookingList>(`/api/mobile/v1/accommodation/bookings?${params.toString()}`);
  }

  getBooking(reference: string): Promise<AccommodationBooking> {
    return this.unwrap<AccommodationBooking>(
      `/api/mobile/v1/accommodation/bookings/${encodeURIComponent(reference)}`
    );
  }

  cancelBooking(input: { reference: string; idempotencyKey: string; reason?: string }): Promise<AccommodationCancelResult> {
    return this.unwrap<AccommodationCancelResult>(
      `/api/mobile/v1/accommodation/bookings/${encodeURIComponent(input.reference)}/cancel`,
      {
        method: "POST",
        headers: { "Idempotency-Key": input.idempotencyKey },
        body: { reason: input.reason ?? "Cancelled by guest" },
      }
    );
  }
}
