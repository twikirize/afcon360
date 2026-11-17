import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import * as SQLite from "expo-sqlite";
import type { MobileIdentity } from "@afcon360/mobile-core";

const DATABASE_NAME = "afcon360-user-offline.db";
const DATABASE_KEY_STORAGE_KEY = "afcon360.user.offline-db-key.v1";
const ACTIVE_ACCOUNT_SCOPE_KEY = "afcon360.user.offline-active-scope.v1";
const DATABASE_SCHEMA_VERSION = 1;

export const DEFAULT_CACHE_MAX_STALE_MS = 7 * 24 * 60 * 60 * 1000;
export const OFFLINE_SESSION_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export type OfflineCacheEntry<T> = {
  value: T;
  storedAt: number;
  expiresAt: number;
  isFresh: boolean;
};

export type OfflineIdentitySnapshot = {
  user: MobileIdentity;
  lastVerifiedAt: number;
};

type CacheRow = {
  payload_json: string;
  stored_at: number;
  expires_at: number;
  schema_version: number;
};

let databasePromise: Promise<SQLite.SQLiteDatabase> | null = null;

export function getOfflineAccountScope(userPublicId: string, environmentOrigin: string): string {
  if (!userPublicId || userPublicId.length > 128) {
    throw new Error("A verified AFCON360 account is required for offline storage.");
  }
  const origin = new URL(environmentOrigin).origin.toLowerCase();
  const scope = origin + "::" + userPublicId;
  if (scope.length > 255) {
    throw new Error("The selected AFCON360 environment cannot be used for offline storage.");
  }
  return scope;
}

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
}

async function getOrCreateDatabaseKey(): Promise<string> {
  const existing = await SecureStore.getItemAsync(DATABASE_KEY_STORAGE_KEY);
  if (existing) {
    if (!/^[0-9a-f]{64}$/i.test(existing)) {
      throw new Error("AFCON360 could not unlock its protected offline database key.");
    }
    return existing;
  }

  const generated = toHex(await Crypto.getRandomBytesAsync(32));
  await SecureStore.setItemAsync(DATABASE_KEY_STORAGE_KEY, generated, {
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
  return generated;
}

async function initializeDatabase(): Promise<SQLite.SQLiteDatabase> {
  const key = await getOrCreateDatabaseKey();
  const database = await SQLite.openDatabaseAsync(DATABASE_NAME);

  try {
    // Expo SQLite can silently ignore PRAGMA key when SQLCipher is not compiled
    // into the native binary. Fail closed before reading or writing user data.
    const cipher = await database.getFirstAsync<{ cipher_version: string }>(
      "PRAGMA cipher_version"
    );
    if (!cipher?.cipher_version) {
      throw new Error(
        "Protected offline storage is unavailable in this build. Rebuild AFCON360 with SQLCipher enabled."
      );
    }

    // This value is a locally generated, hex-validated key. Never log it or
    // replace it with a user-controlled value.
    await database.execAsync("PRAGMA key = \"x'" + key + "'\";");
    await database.getFirstAsync<{ count: number }>(
      "SELECT count(*) AS count FROM sqlite_master"
    );
    await database.execAsync(
      "PRAGMA cipher_memory_security = ON;" +
      "PRAGMA foreign_keys = ON;" +
      "PRAGMA journal_mode = WAL;" +
      "PRAGMA synchronous = FULL;" +
      "PRAGMA secure_delete = ON;"
    );

    const current = await database.getFirstAsync<{ user_version: number }>(
      "PRAGMA user_version"
    );
    const version = current?.user_version ?? 0;
    if (version > DATABASE_SCHEMA_VERSION) {
      throw new Error("The AFCON360 offline database was created by a newer app version.");
    }

    if (version < 1) {
      await database.execAsync(
        "CREATE TABLE IF NOT EXISTS offline_cache (" +
          "account_scope TEXT NOT NULL," +
          "cache_key TEXT NOT NULL," +
          "payload_json TEXT NOT NULL," +
          "stored_at INTEGER NOT NULL," +
          "expires_at INTEGER NOT NULL," +
          "schema_version INTEGER NOT NULL," +
          "PRIMARY KEY (account_scope, cache_key)" +
        ");" +
        "CREATE INDEX IF NOT EXISTS idx_offline_cache_scope_expiry " +
          "ON offline_cache (account_scope, expires_at);" +
        "PRAGMA user_version = 1;"
      );
    }

    return database;
  } catch (error) {
    await database.closeAsync().catch(() => undefined);
    throw error;
  }
}

function getDatabase(): Promise<SQLite.SQLiteDatabase> {
  if (!databasePromise) {
    databasePromise = initializeDatabase().catch(error => {
      databasePromise = null;
      throw error;
    });
  }
  return databasePromise;
}

function assertCacheIdentity(accountScope: string, cacheKey: string): void {
  if (!accountScope || accountScope.length > 255) {
    throw new Error("An account scope is required for AFCON360 offline storage.");
  }
  if (!cacheKey || cacheKey.length > 255) {
    throw new Error("A valid cache key is required for AFCON360 offline storage.");
  }
}

export async function writeOfflineCache<T>(
  accountScope: string,
  cacheKey: string,
  value: T,
  ttlMs = 15 * 60 * 1000
): Promise<void> {
  assertCacheIdentity(accountScope, cacheKey);
  const payload = JSON.stringify(value);
  if (typeof payload !== "string" || payload.length > 2_000_000) {
    throw new Error("This AFCON360 response is not suitable for the offline cache.");
  }

  const now = Date.now();
  const safeTtl = Math.min(
    Math.max(Math.floor(ttlMs), 1000),
    30 * 24 * 60 * 60 * 1000
  );
  const database = await getDatabase();
  await database.runAsync(
    "INSERT INTO offline_cache " +
      "(account_scope, cache_key, payload_json, stored_at, expires_at, schema_version) " +
      "VALUES (?, ?, ?, ?, ?, ?) " +
      "ON CONFLICT(account_scope, cache_key) DO UPDATE SET " +
      "payload_json = excluded.payload_json, " +
      "stored_at = excluded.stored_at, " +
      "expires_at = excluded.expires_at, " +
      "schema_version = excluded.schema_version",
    accountScope,
    cacheKey,
    payload,
    now,
    now + safeTtl,
    DATABASE_SCHEMA_VERSION
  );
}

export async function readOfflineCache<T>(
  accountScope: string,
  cacheKey: string,
  maxStaleMs = DEFAULT_CACHE_MAX_STALE_MS
): Promise<OfflineCacheEntry<T> | null> {
  assertCacheIdentity(accountScope, cacheKey);
  const database = await getDatabase();
  const row = await database.getFirstAsync<CacheRow>(
    "SELECT payload_json, stored_at, expires_at, schema_version " +
      "FROM offline_cache WHERE account_scope = ? AND cache_key = ?",
    accountScope,
    cacheKey
  );
  if (!row) return null;

  const age = Date.now() - row.stored_at;
  if (
    row.schema_version !== DATABASE_SCHEMA_VERSION ||
    age < 0 ||
    age > Math.max(0, maxStaleMs)
  ) {
    await database.runAsync(
      "DELETE FROM offline_cache WHERE account_scope = ? AND cache_key = ?",
      accountScope,
      cacheKey
    );
    return null;
  }

  try {
    return {
      value: JSON.parse(row.payload_json) as T,
      storedAt: row.stored_at,
      expiresAt: row.expires_at,
      isFresh: row.expires_at > Date.now(),
    };
  } catch {
    await database.runAsync(
      "DELETE FROM offline_cache WHERE account_scope = ? AND cache_key = ?",
      accountScope,
      cacheKey
    );
    return null;
  }
}

export async function saveOfflineIdentity(
  user: MobileIdentity,
  environmentOrigin: string
): Promise<void> {
  if (!user.public_id || user.client !== "user") {
    throw new Error("Only a verified AFCON360 User identity can be cached for offline restoration.");
  }

  const scope = getOfflineAccountScope(user.public_id, environmentOrigin);
  // Clear the pointer first. A failed account switch must never restore the
  // previous account's cached identity against the newly stored credentials.
  await SecureStore.deleteItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY);
  await writeOfflineCache(
    scope,
    "identity.v1",
    user,
    OFFLINE_SESSION_MAX_AGE_MS
  );
  await SecureStore.setItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY, scope, {
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
  });
}

export async function readOfflineIdentity(
  environmentOrigin: string
): Promise<OfflineIdentitySnapshot | null> {
  const activeScope = await SecureStore.getItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY);
  const originPrefix = new URL(environmentOrigin).origin.toLowerCase() + "::";
  if (!activeScope || !activeScope.startsWith(originPrefix)) return null;

  const publicId = activeScope.slice(originPrefix.length);
  if (!publicId) return null;
  const identity = await readOfflineCache<MobileIdentity>(
    activeScope,
    "identity.v1",
    OFFLINE_SESSION_MAX_AGE_MS
  );
  if (
    !identity?.value ||
    identity.value.public_id !== publicId ||
    identity.value.client !== "user"
  ) {
    return null;
  }
  return { user: identity.value, lastVerifiedAt: identity.storedAt };
}

export async function clearOfflineAccount(
  userPublicId: string,
  environmentOrigin: string
): Promise<void> {
  if (!userPublicId) return;
  const scope = getOfflineAccountScope(userPublicId, environmentOrigin);
  const activeScope = await SecureStore.getItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY);
  if (activeScope === scope) {
    await SecureStore.deleteItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY);
  }
  const database = await getDatabase();
  await database.runAsync(
    "DELETE FROM offline_cache WHERE account_scope = ?",
    scope
  );
}

export async function clearAllOfflineData(): Promise<void> {
  // Removing the secure active-account pointer first makes all old cache rows
  // unreachable even if the database cannot currently be opened.
  await SecureStore.deleteItemAsync(ACTIVE_ACCOUNT_SCOPE_KEY);
  const database = await getDatabase();
  await database.runAsync("DELETE FROM offline_cache");
}
