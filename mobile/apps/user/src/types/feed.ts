export type FeedMetadata = {
  city?: string | null;
  country?: string | null;
  property_type?: string | null;
  price_per_night?: string | number | null;
  route_type?: string | null;
  primary_zone?: string | null;
  module_label?: string | null;
  promo?: boolean;
  is_promo?: boolean;
  [key: string]: unknown;
};

export type FeedItem = {
  feed_id: string;
  type: 'post' | 'event' | 'ad' | 'system_update' | 'property' | 'transport' | string;
  title?: string | null;
  body?: string | null;
  image_url?: string | null;
  link_url?: string | null;
  author_name?: string | null;
  source_module?: string | null;
  metadata?: FeedMetadata | null;
  created_at?: string | null;
  is_pinned?: boolean;
};

export type FeedResponse = {
  items?: FeedItem[];
  page?: number;
  per_page?: number;
  has_more?: boolean;
  seed?: string;
  error?: string;
};

export type LoadMode = 'initial' | 'refresh' | 'more';