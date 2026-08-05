import {
  User,
  Wallet,
  EventItem,
  EventRegistration,
  Property,
  PropertyBooking,
  Vehicle,
  TransportBooking,
  KycSubmission
} from '../types.js';

export const mockUsers: User[] = [
  {
    id: 'usr_fan1',
    public_id: 'pub_usr_fan_001',
    username: 'afcon_fan_ug',
    email: 'fan@afcon360.com',
    role: 'fan',
    active_role: 'fan',
    available_roles: ['fan', 'organizer', 'host'],
    kyc_tier: 2,
    kyc_status: 'verified',
    full_name: 'David Mukasa',
    phone: '+256771234567',
    national_id: 'CM98012345ABCD',
    created_at: '2026-01-15T10:00:00Z'
  },
  {
    id: 'usr_host1',
    public_id: 'pub_usr_host_001',
    username: 'serena_hospitality',
    email: 'host@afcon360.com',
    role: 'host',
    active_role: 'host',
    available_roles: ['host', 'fan'],
    kyc_tier: 3,
    kyc_status: 'verified',
    full_name: 'Grace Akello',
    phone: '+256782999888',
    national_id: 'CF92098765XYZ',
    created_at: '2026-01-10T09:00:00Z'
  },
  {
    id: 'usr_driver1',
    public_id: 'pub_usr_driver_001',
    username: 'vip_transporter',
    email: 'driver@afcon360.com',
    role: 'driver',
    active_role: 'driver',
    available_roles: ['driver', 'fan'],
    kyc_tier: 3,
    kyc_status: 'verified',
    full_name: 'John Kato',
    phone: '+256701112233',
    national_id: 'CM90044455QWE',
    created_at: '2026-02-01T12:00:00Z'
  },
  {
    id: 'usr_admin1',
    public_id: 'pub_usr_admin_001',
    username: 'afcon_owner_admin',
    email: 'admin@afcon360.com',
    role: 'super_admin',
    active_role: 'super_admin',
    available_roles: ['super_admin', 'moderator', 'compliance_officer', 'fan'],
    kyc_tier: 4,
    kyc_status: 'verified',
    full_name: 'Super Admin Control',
    phone: '+256700000000',
    created_at: '2025-12-01T08:00:00Z'
  }
];

export const mockWallets: Record<string, Wallet> = {
  usr_fan1: {
    user_id: 'usr_fan1',
    balance_ugx: 1850000,
    balance_usd: 500.0,
    escrow_balance_ugx: 350000,
    transactions: [
      {
        id: 'tx_001',
        public_id: 'pub_tx_001',
        type: 'deposit',
        amount: 2000000,
        currency: 'UGX',
        status: 'completed',
        reference: 'MTN_MOMO_982341',
        description: 'MTN Mobile Money Deposit',
        created_at: '2026-03-01T14:30:00Z'
      },
      {
        id: 'tx_002',
        public_id: 'pub_tx_002',
        type: 'payment',
        amount: 150000,
        currency: 'UGX',
        status: 'completed',
        reference: 'TKT_AFCON_2027_01',
        description: 'VIP Pass - Uganda vs Kenya Match',
        created_at: '2026-03-02T10:15:00Z'
      }
    ]
  },
  usr_host1: {
    user_id: 'usr_host1',
    balance_ugx: 8400000,
    balance_usd: 2200.0,
    escrow_balance_ugx: 1200000,
    transactions: [
      {
        id: 'tx_003',
        public_id: 'pub_tx_003',
        type: 'payout',
        amount: 3200000,
        currency: 'UGX',
        status: 'completed',
        reference: 'BANK_SETTLEMENT_441',
        description: 'Stanbic Bank Accommodation Earnings Payout',
        created_at: '2026-02-28T16:00:00Z'
      }
    ]
  },
  usr_driver1: {
    user_id: 'usr_driver1',
    balance_ugx: 650000,
    balance_usd: 150.0,
    escrow_balance_ugx: 0,
    transactions: [
      {
        id: 'tx_004',
        public_id: 'pub_tx_004',
        type: 'deposit',
        amount: 300000,
        currency: 'UGX',
        status: 'completed',
        reference: 'AIRTEL_MONEY_5511',
        description: 'Airtel Money Shuttle Deposit',
        created_at: '2026-03-03T08:00:00Z'
      }
    ]
  }
};

export const mockEvents: EventItem[] = [
  {
    id: 'evt_001',
    public_id: 'pub_evt_afcon2027',
    title: 'AFCON 2027 Opener: Uganda Cranes vs Kenya Harambee Stars',
    category: 'Sports',
    location: 'Kampala, Uganda',
    venue: 'Mandela National Stadium, Namboole',
    start_date: '2027-06-12T16:00:00Z',
    end_date: '2027-06-12T19:00:00Z',
    price_ugx: 75000,
    capacity: 45000,
    registered_count: 31200,
    image_url: 'https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=800&auto=format&fit=crop',
    organizer: 'CAF & FUFA Local Organizing Committee',
    description: 'The opening blockbuster match of the 2027 Africa Cup of Nations East Africa Pamoja Bid edition in Kampala!',
    featured: true
  },
  {
    id: 'evt_002',
    public_id: 'pub_evt_crusade2026',
    title: 'Great East Africa Crusade & Unity Festival 2026',
    category: 'Religious',
    location: 'Kololo Ceremonial Grounds, Kampala',
    venue: 'Kololo Grounds Main Arena',
    start_date: '2026-09-20T08:00:00Z',
    end_date: '2026-09-22T20:00:00Z',
    price_ugx: 0,
    capacity: 60000,
    registered_count: 42100,
    image_url: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=800&auto=format&fit=crop',
    organizer: 'East Africa Inter-Religious Council',
    description: 'A grand multi-nation festival celebrating peace, unity, and fan brotherhood leading into AFCON 2027.',
    featured: true
  },
  {
    id: 'evt_003',
    public_id: 'pub_evt_worldcup2026',
    title: 'FIFA World Cup 2026 Fan Park & Live Screening',
    category: 'Festival',
    location: 'Lugogo Cricket Oval, Kampala',
    venue: 'Lugogo Main Stage',
    start_date: '2026-06-25T18:00:00Z',
    end_date: '2026-07-15T23:00:00Z',
    price_ugx: 25000,
    capacity: 15000,
    registered_count: 8900,
    image_url: 'https://images.unsplash.com/photo-1518091043644-c1d4457512c6?w=800&auto=format&fit=crop',
    organizer: 'AFCON360 Fan Zone Team',
    description: 'Ultra-HD LED stadium screens, food stalls, live DJs, and interactive games during World Cup 2026 matches.',
    featured: true
  }
];

export const mockRegistrations: EventRegistration[] = [
  {
    id: 'reg_001',
    event_id: 'evt_001',
    user_id: 'usr_fan1',
    ticket_type: 'VIP Pass',
    quantity: 2,
    total_ugx: 150000,
    qr_code: 'AFCON360-QR-98214-TKT',
    status: 'confirmed',
    created_at: '2026-03-02T10:15:00Z'
  }
];

export const mockProperties: Property[] = [
  {
    id: 'prop_001',
    public_id: 'pub_prop_serena',
    title: 'Kampala Serena Luxury Suite near Namboole Stadium Shuttle',
    property_type: 'Hotel',
    location: 'Central Kampala, Uganda',
    address: 'Kintu Road, Kampala',
    price_per_night_ugx: 450000,
    rating: 4.9,
    reviews_count: 128,
    image_url: 'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=800&auto=format&fit=crop',
    host_name: 'Serena Hospitality',
    amenities: ['Free WiFi', 'Swimming Pool', 'Airport Shuttle', 'AC', 'Breakfast Included'],
    bedrooms: 2,
    bathrooms: 2,
    status: 'approved'
  },
  {
    id: 'prop_002',
    public_id: 'pub_prop_lake_breeze',
    title: 'Ggaba Lake Victoria Breeze Penthouse',
    property_type: 'Apartment',
    location: 'Ggaba / Munyonyo, Kampala',
    address: 'Plot 44 Lake Drive, Munyonyo',
    price_per_night_ugx: 220000,
    rating: 4.8,
    reviews_count: 64,
    image_url: 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=800&auto=format&fit=crop',
    host_name: 'Grace Akello',
    amenities: ['Lake View Balcony', 'Kitchen', 'Free Parking', 'Washing Machine'],
    bedrooms: 3,
    bathrooms: 2,
    status: 'approved'
  },
  {
    id: 'prop_003',
    public_id: 'pub_prop_jinja_eco',
    title: 'Source of the Nile Eco Resort Cottage',
    property_type: 'Villa',
    location: 'Jinja, Uganda',
    address: 'Nile Crescent, Jinja',
    price_per_night_ugx: 310000,
    rating: 4.95,
    reviews_count: 92,
    image_url: 'https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?w=800&auto=format&fit=crop',
    host_name: 'Jinja Adventure Stays',
    amenities: ['River Kayaking', 'Solar Power', 'Restaurant', 'Garden View'],
    bedrooms: 1,
    bathrooms: 1,
    status: 'approved'
  }
];

export const mockBookings: PropertyBooking[] = [
  {
    id: 'bk_001',
    property_id: 'prop_002',
    user_id: 'usr_fan1',
    check_in: '2026-06-11',
    check_out: '2026-06-14',
    guests: 2,
    total_ugx: 660000,
    status: 'confirmed',
    created_at: '2026-03-01T12:00:00Z'
  }
];

export const mockVehicles: Vehicle[] = [
  {
    id: 'veh_001',
    public_id: 'pub_veh_001',
    name: 'Toyota Coaster Executive VIP Shuttle',
    type: 'VIP Coaster Bus',
    capacity: 28,
    rate_per_km_ugx: 3500,
    base_fare_ugx: 50000,
    driver_name: 'John Kato',
    plate_number: 'UBJ 482A',
    status: 'available',
    location: 'Entebbe International Airport / Kampala Central'
  },
  {
    id: 'veh_002',
    public_id: 'pub_veh_002',
    name: 'Land Cruiser V8 VIP Convoy SUV',
    type: 'Executive Sedan',
    capacity: 4,
    rate_per_km_ugx: 5000,
    base_fare_ugx: 80000,
    driver_name: 'Moses Opolot',
    plate_number: 'UBG 901Z',
    status: 'available',
    location: 'Munyonyo Commonwealth Resort'
  },
  {
    id: 'veh_003',
    public_id: 'pub_veh_003',
    name: 'AFCON Express Airport Transfer Van',
    type: 'Airport Shuttle Van',
    capacity: 12,
    rate_per_km_ugx: 2800,
    base_fare_ugx: 35000,
    driver_name: 'Samuel Ssemwanga',
    plate_number: 'UBL 112B',
    status: 'available',
    location: 'Entebbe Airport Terminal'
  }
];

export const mockTransportBookings: TransportBooking[] = [
  {
    id: 'tbk_001',
    vehicle_id: 'veh_001',
    user_id: 'usr_fan1',
    pickup_location: 'Entebbe International Airport',
    dropoff_location: 'Kampala Serena Hotel',
    pickup_time: '2026-06-11 14:00',
    distance_km: 42,
    total_ugx: 197000,
    status: 'confirmed' as any,
    created_at: '2026-03-02T11:00:00Z'
  }
];

export const mockKycSubmissions: KycSubmission[] = [
  {
    id: 'kyc_001',
    user_id: 'usr_fan1',
    document_type: 'National ID',
    document_number: 'CM98012345ABCD',
    status: 'approved',
    submitted_at: '2026-01-16T10:00:00Z',
    reviewed_at: '2026-01-16T11:30:00Z',
    reviewer_notes: 'National ID verified with NIRA database.'
  },
  {
    id: 'kyc_002',
    user_id: 'usr_host1',
    document_type: 'Proof of Residence',
    document_number: 'REG-PROPERTY-8842',
    status: 'approved',
    submitted_at: '2026-01-11T09:00:00Z',
    reviewed_at: '2026-01-11T10:15:00Z',
    reviewer_notes: 'Property deed verified.'
  }
];
