// The browser must call the API through the same-origin /api proxy (see
// next.config.ts) so the HttpOnly session cookie travels with every request.
// An absolute NEXT_PUBLIC_API_URL is honoured only in tests; a leftover value in
// a hosting environment would otherwise bypass the proxy and lose the session.
export const API_URL =
  process.env.NODE_ENV === "test" && process.env.NEXT_PUBLIC_API_URL
    ? process.env.NEXT_PUBLIC_API_URL
    : "/api";
