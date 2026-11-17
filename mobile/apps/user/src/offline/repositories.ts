import type {
  NativeEventRegistrationList,
} from "@afcon360/mobile-core";
import { authClient, eventClient, getSelectedApiBaseUrl } from "../services/api";
import type { FeedResponse } from "../types/feed";
import {
  getOfflineAccountScope,
  readOfflineCache,
  writeOfflineCache,
  type OfflineCacheEntry,
} from "./storage";

export type CachedSnapshot<T> = Pick<
  OfflineCacheEntry<T>,
  "value" | "storedAt" | "expiresAt" | "isFresh"
>;

async function scopeFor(userPublicId: string): Promise<string> {
  return getOfflineAccountScope(userPublicId, await getSelectedApiBaseUrl());
}

function snapshot<T>(entry: OfflineCacheEntry<T> | null): CachedSnapshot<T> | null {
  if (!entry) return null;
  return {
    value: entry.value,
    storedAt: entry.storedAt,
    expiresAt: entry.expiresAt,
    isFresh: entry.isFresh,
  };
}

async function saveBestEffort<T>(
  scope: string,
  key: string,
  value: T,
  ttlMs: number
): Promise<void> {
  try {
    await writeOfflineCache(scope, key, value, ttlMs);
  } catch {
    // A local cache failure must never turn a successful online API read into
    // a failed user journey. Offline availability is reported separately.
  }
}

const HOME_FEED_KEY = "home.feed.page1.v1";
const EVENT_REGISTRATIONS_KEY = "events.registrations.summary.v1";
const WISHLIST_KEY = "stays.wishlist.v1";
const HOME_FEED_TTL_MS = 15 * 60 * 1000;
const EVENT_REGISTRATIONS_TTL_MS = 5 * 60 * 1000;
const WISHLIST_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const MAX_STALE_MS = 7 * 24 * 60 * 60 * 1000;

export type WishlistItem = {
  propertyId: string;
  propertyTitle: string;
  propertyCity: string;
  propertyCountry: string;
  propertyImage: string | null;
  propertyStartingPrice: string;
  propertyCurrency: string;
  addedAt: number;
};

export type WishlistData = {
  items: WishlistItem[];
  updatedAt: number;
};

export const userOfflineRepository = {
  async readHomeFeed(userPublicId: string): Promise<CachedSnapshot<FeedResponse> | null> {
    return snapshot(await readOfflineCache<FeedResponse>(
      await scopeFor(userPublicId),
      HOME_FEED_KEY,
      MAX_STALE_MS
    ));
  },

  async refreshHomeFeed(
    userPublicId: string | null,
    page: number,
    seed: string | null
  ): Promise<FeedResponse> {
    const params = new URLSearchParams({
      page: String(page),
      per_page: "10",
      layout: "mixed",
    });
    if (seed) params.set("seed", seed);
    const response = await authClient.request<FeedResponse>(
      "/api/home/feed?" + params.toString()
    );
    if (userPublicId && page === 1 && !seed) {
      await saveBestEffort(
        await scopeFor(userPublicId),
        HOME_FEED_KEY,
        response,
        HOME_FEED_TTL_MS
      );
    }
    return response;
  },

  async readEventRegistrations(
    userPublicId: string
  ): Promise<CachedSnapshot<NativeEventRegistrationList> | null> {
    return snapshot(await readOfflineCache<NativeEventRegistrationList>(
      await scopeFor(userPublicId),
      EVENT_REGISTRATIONS_KEY,
      MAX_STALE_MS
    ));
  },

  async refreshEventRegistrations(
    userPublicId: string
  ): Promise<NativeEventRegistrationList> {
    const response = await eventClient.listRegistrations(50, 0);
    // The Home summary is read-only. Do not cache ticket QR payloads.
    const summary: NativeEventRegistrationList = {
      ...response,
      items: (response.items ?? []).map(item => ({ ...item, qr_code: "" })),
    };
    await saveBestEffort(
      await scopeFor(userPublicId),
      EVENT_REGISTRATIONS_KEY,
      summary,
      EVENT_REGISTRATIONS_TTL_MS
    );
    return summary;
  },

  async readWishlist(userPublicId: string): Promise<CachedSnapshot<WishlistData> | null> {
    return snapshot(await readOfflineCache<WishlistData>(
      await scopeFor(userPublicId),
      WISHLIST_KEY,
      MAX_STALE_MS
    ));
  },

  async addToWishlist(userPublicId: string, item: WishlistItem): Promise<WishlistData> {
    const cached = await this.readWishlist(userPublicId);
    const existing = cached?.value ?? { items: [], updatedAt: Date.now() };
    const filtered = existing.items.filter((i) => i.propertyId !== item.propertyId);
    const updated: WishlistData = {
      items: [{ ...item, addedAt: Date.now() }, ...filtered],
      updatedAt: Date.now(),
    };
    await saveBestEffort(await scopeFor(userPublicId), WISHLIST_KEY, updated, WISHLIST_TTL_MS);
    return updated;
  },

  async removeFromWishlist(userPublicId: string, propertyId: string): Promise<WishlistData> {
    const cached = await this.readWishlist(userPublicId);
    const existing = cached?.value ?? { items: [], updatedAt: Date.now() };
    const updated: WishlistData = {
      items: existing.items.filter((i) => i.propertyId !== propertyId),
      updatedAt: Date.now(),
    };
    await saveBestEffort(await scopeFor(userPublicId), WISHLIST_KEY, updated, WISHLIST_TTL_MS);
    return updated;
  },

  async clearWishlist(userPublicId: string): Promise<void> {
    const empty: WishlistData = { items: [], updatedAt: Date.now() };
    await saveBestEffort(await scopeFor(userPublicId), WISHLIST_KEY, empty, WISHLIST_TTL_MS);
  },
};
