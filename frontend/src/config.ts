// Same-origin proxy path by default (see next.config.ts rewrites). Setting
// NEXT_PUBLIC_API_URL to an absolute URL bypasses the proxy; cookies then depend
// on third-party cookie rules, so keep the default in production.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";
