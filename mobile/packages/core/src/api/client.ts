export type TokenReader = () => Promise<string | null>;
export type BaseUrlReader = () => Promise<string | undefined>;

export type ApiClientOptions = {
  baseUrl?: string;
  getBaseUrl?: BaseUrlReader;
  allowPrivateHttp?: boolean;
  readAccessToken?: TokenReader;
  timeoutMs?: number;
};

export type RequestOptions = Omit<RequestInit, "headers" | "body"> & {
  headers?: Record<string, string>;
  body?: unknown;
};

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function isPrivateIpv4(hostname: string): boolean {
  const parts = hostname.split(".");
  if (parts.length !== 4 || !parts.every(part => /^\d{1,3}$/.test(part))) return false;
  const octets = parts.map(Number);
  if (octets.some(value => value < 0 || value > 255)) return false;
  const [first, second] = octets;
  return first === 10 ||
    (first === 172 && second >= 16 && second <= 31) ||
    (first === 192 && second === 168);
}

function resolveBaseUrl(override?: string, allowPrivateHttp = false): string {
  const raw = (override ?? process.env.EXPO_PUBLIC_API_BASE_URL ?? "https://www.pamoja.space").trim();
  if (!raw) throw new Error("EXPO_PUBLIC_API_BASE_URL is not configured.");
  const parsed = new URL(raw);
  const localHosts = new Set(["localhost", "127.0.0.1", "10.0.2.2"]);
  const localHttpAllowed = parsed.protocol === "http:" && (
    localHosts.has(parsed.hostname) || (allowPrivateHttp && isPrivateIpv4(parsed.hostname))
  );
  if (parsed.protocol !== "https:" && !localHttpAllowed) {
    throw new Error("The mobile API must use HTTPS, except for an approved local preview server.");
  }
  return parsed.toString().replace(/\/+$/, "");
}

export class ApiClient {
  private readonly baseUrlOverride?: string;
  private readonly getBaseUrl?: BaseUrlReader;
  private readonly allowPrivateHttp: boolean;
  private readonly readAccessToken?: TokenReader;
  private readonly timeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrlOverride = options.baseUrl;
    this.getBaseUrl = options.getBaseUrl;
    this.allowPrivateHttp = options.allowPrivateHttp ?? false;
    this.readAccessToken = options.readAccessToken;
    this.timeoutMs = options.timeoutMs ?? 15000;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    if (!path.startsWith("/") || path.startsWith("//")) {
      throw new Error("API paths must be origin-relative and start with one slash.");
    }
    // Read the selected origin for every request so preview server changes apply immediately.
    const selectedBaseUrl = await this.getBaseUrl?.();
    const baseUrl = resolveBaseUrl(selectedBaseUrl ?? this.baseUrlOverride, this.allowPrivateHttp);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const token = await this.readAccessToken?.();
      const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
      let body: BodyInit | undefined;
      if (options.body !== undefined) {
        if (typeof options.body === "string" || options.body instanceof FormData) {
          body = options.body as BodyInit;
        } else {
          headers["Content-Type"] = "application/json";
          body = JSON.stringify(options.body);
        }
      }
      if (token) headers.Authorization = "Bearer " + token;
      const response = await fetch(baseUrl + path, {
        ...options, headers, body, credentials: "omit", signal: controller.signal
      });
      const type = response.headers.get("content-type") ?? "";
      const payload = response.status === 204 ? null :
        type.includes("application/json") ? await response.json() : await response.text();
      if (!response.ok) {
        const message = payload && typeof payload === "object" && "message" in payload
          ? String((payload as { message: unknown }).message)
          : "The server could not complete the request.";
        throw new ApiError(message, response.status, payload);
      }
      return payload as T;
    } finally {
      clearTimeout(timeout);
    }
  }

  get<T>(path: string, options: Omit<RequestOptions, "method" | "body"> = {}) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options: Omit<RequestOptions, "method" | "body"> = {}) {
    return this.request<T>(path, { ...options, method: "POST", body });
  }
}
