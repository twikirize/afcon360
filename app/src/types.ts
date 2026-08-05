export interface User {
  id: string;
  public_id: string;
  username: string;
  email: string;
  role: string;
  active_role: string;
  available_roles: string[];
  kyc_tier: number;
  kyc_status: 'unverified' | 'pending' | 'verified' | 'rejected';
  full_name: string;
  phone?: string;
  national_id?: string;
  created_at: string;
}

export interface WalletTransaction {
  id: string;
  public_id: string;
  type: 'deposit' | 'withdrawal' | 'transfer' | 'payment' | 'payout' | 'escrow_hold';
  amount: number;
  currency: string;
  status: 'pending' | 'completed' | 'failed' | 'reversed';
  reference: string;
  description: string;
  counterparty?: string;
  created_at: string;
}

export interface Wallet {
  user_id: string;
  balance_ugx: number;
  balance_usd: number;
  escrow_balance_ugx: number;
  transactions: WalletTransaction[];
}

export interface EventItem {
  id: string;
  public_id: string;
  title: string;
  category: 'Sports' | 'Conference' | 'Festival' | 'Religious' | 'Exhibition';
  location: string;
  venue: string;
  start_date: string;
  end_date: string;
  price_ugx: number;
  capacity: number;
  registered_count: number;
  image_url: string;
  organizer: string;
  description: string;
  featured: boolean;
}

export interface EventRegistration {
  id: string;
  event_id: string;
  user_id: string;
  ticket_type: string;
  quantity: number;
  total_ugx: number;
  qr_code: string;
  status: 'confirmed' | 'cancelled' | 'used';
  created_at: string;
}

export interface Property {
  id: string;
  public_id: string;
  title: string;
  property_type: 'Hotel' | 'Apartment' | 'Guest House' | 'Villa';
  location: string;
  address: string;
  price_per_night_ugx: number;
  rating: number;
  reviews_count: number;
  image_url: string;
  host_name: string;
  amenities: string[];
  bedrooms: number;
  bathrooms: number;
  status: 'approved' | 'pending' | 'rejected';
}

export interface PropertyBooking {
  id: string;
  property_id: string;
  user_id: string;
  check_in: string;
  check_out: string;
  guests: number;
  total_ugx: number;
  status: 'confirmed' | 'pending' | 'completed' | 'cancelled';
  created_at: string;
}

export interface Vehicle {
  id: string;
  public_id: string;
  name: string;
  type: 'Executive Sedan' | 'VIP Coaster Bus' | 'Airport Shuttle Van' | 'Executive Boda';
  capacity: number;
  rate_per_km_ugx: number;
  base_fare_ugx: number;
  driver_name: string;
  plate_number: string;
  status: 'available' | 'busy' | 'offline';
  location: string;
}

export interface TransportBooking {
  id: string;
  vehicle_id: string;
  user_id: string;
  pickup_location: string;
  dropoff_location: string;
  pickup_time: string;
  distance_km: number;
  total_ugx: number;
  status: 'requested' | 'accepted' | 'in_progress' | 'completed' | 'cancelled';
  created_at: string;
}

export interface KycSubmission {
  id: string;
  user_id: string;
  document_type: 'National ID' | 'Passport' | 'Driving License' | 'Proof of Residence';
  document_number: string;
  status: 'pending' | 'approved' | 'rejected';
  submitted_at: string;
  reviewed_at?: string;
  reviewer_notes?: string;
}
