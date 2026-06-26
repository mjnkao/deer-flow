import { authApiUrl } from "@/core/auth/client";
import { buildLoginUrl } from "@/core/auth/types";

/** HTTP methods that the gateway's CSRFMiddleware checks. */
export type StateChangingMethod = "POST" | "PUT" | "DELETE" | "PATCH";

export const STATE_CHANGING_METHODS: ReadonlySet<StateChangingMethod> = new Set(
  ["POST", "PUT", "DELETE", "PATCH"],
);

/** Mirror of the gateway's ``should_check_csrf`` decision. */
export function isStateChangingMethod(method: string): boolean {
  return (STATE_CHANGING_METHODS as ReadonlySet<string>).has(
    method.toUpperCase(),
  );
}

const CSRF_COOKIE_PREFIX = "csrf_token=";
let authRedirectStarted = false;
let csrfRefreshPromise: Promise<string | null> | null = null;

async function resolveAuthRedirectTarget(returnPath: string): Promise<string> {
  try {
    const response = await globalThis.fetch(
      authApiUrl("/api/v1/auth/setup-status"),
      {
        credentials: "include",
        cache: "no-store",
      },
    );
    if (response.ok) {
      const data = (await response.json()) as { needs_setup?: boolean };
      if (data.needs_setup) return "/setup";
    }
  } catch {
    // Fall through to login; the auth pages can surface gateway/setup errors.
  }
  return buildLoginUrl(returnPath);
}

/**
 * Read the ``csrf_token`` cookie set by the gateway at login.
 *
 * SSR-safe: returns ``null`` when ``document`` is undefined so the same
 * helper can be imported from server components without a guard.
 *
 * Uses `String.split` instead of a regex to side-step ESLint's
 * `prefer-regexp-exec` rule and the cookie value's reliable `; `
 * separator (set by the gateway, not the browser, so format is stable).
 */
export function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  for (const pair of document.cookie.split("; ")) {
    if (pair.startsWith(CSRF_COOKIE_PREFIX)) {
      return decodeURIComponent(pair.slice(CSRF_COOKIE_PREFIX.length));
    }
  }
  return null;
}

/**
 * Return a CSRF token, minting one from the authenticated gateway session when
 * the browser has an access_token cookie but no csrf_token cookie yet.
 */
export async function ensureCsrfToken(): Promise<string | null> {
  const existing = readCsrfCookie();
  if (existing) return existing;
  if (typeof window === "undefined") return null;

  csrfRefreshPromise ??= globalThis
    .fetch(authApiUrl("/api/v1/auth/csrf"), {
      credentials: "include",
      cache: "no-store",
    })
    .then(async (response) => {
      if (!response.ok) return null;
      const data = (await response.json()) as { csrf_token?: unknown };
      return typeof data.csrf_token === "string" ? data.csrf_token : null;
    })
    .catch(() => null)
    .finally(() => {
      csrfRefreshPromise = null;
    });

  return csrfRefreshPromise;
}

/**
 * Fetch with credentials and automatic CSRF protection.
 *
 * Two centralized contracts every API call needs:
 *
 * 1. ``credentials: "include"`` so the HttpOnly access_token cookie
 *    accompanies cross-origin SSR-routed requests.
 * 2. ``X-CSRF-Token`` header on state-changing methods (POST/PUT/
 *    DELETE/PATCH), echoed from the ``csrf_token`` cookie. The gateway's
 *    CSRFMiddleware enforces Double Submit Cookie comparison and returns
 *    403 if the header is missing — silently breaking every call site
 *    that uses raw ``fetch()`` instead of this wrapper.
 *
 * Auto-redirects to ``/login`` on 401. Caller-supplied headers are
 * preserved; the helper only ADDS the CSRF header when it isn't already
 * present, so explicit overrides win.
 */
export async function fetch(
  input: RequestInfo | string,
  init?: RequestInit,
): Promise<Response> {
  const url = typeof input === "string" ? input : input.url;

  // Inject CSRF for state-changing methods. GET/HEAD/OPTIONS/TRACE skip
  // it to mirror the gateway's ``should_check_csrf`` logic exactly.
  let headers = init?.headers;
  if (isStateChangingMethod(init?.method ?? "GET")) {
    const token = await ensureCsrfToken();
    if (token) {
      // Fresh Headers instance so we don't mutate caller-supplied objects.
      const merged = new Headers(headers);
      if (!merged.has("X-CSRF-Token")) {
        merged.set("X-CSRF-Token", token);
      }
      headers = merged;
    }
  }

  const res = await globalThis.fetch(url, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    if (!authRedirectStarted) {
      authRedirectStarted = true;
      const path = window.location.pathname;
      if (path !== "/login" && path !== "/setup") {
        window.location.href = await resolveAuthRedirectTarget(path);
      }
    }
    throw new Error("Unauthorized");
  }

  return res;
}

/**
 * Build headers for CSRF-protected requests.
 *
 * **Prefer :func:`fetchWithAuth`** for new code — it injects the header
 * automatically on state-changing methods. This helper exists for legacy
 * call sites that need to compose headers manually (e.g. inside
 * `next/server` route handlers that build their own ``Headers`` object).
 *
 * Per RFC-001: Double Submit Cookie pattern.
 */
export function getCsrfHeaders(): HeadersInit {
  const token = readCsrfCookie();
  return token ? { "X-CSRF-Token": token } : {};
}
