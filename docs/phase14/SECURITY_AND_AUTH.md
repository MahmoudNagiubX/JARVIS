# Phase 14 security and authentication

The local application shell is public only as inert static assets. Runtime
state and mutations remain authenticated.

- Desktop start creates a server-held, one-use bootstrap token with a short
  default lifetime (30 seconds). The token contains the credential only in
  process memory and is never placed in a URL query string.
- `POST /auth/desktop-session` consumes that token, reuses the existing
  identity/device authentication, and issues a short-lived server session.
- The session is represented to the browser by an HttpOnly, SameSite=Strict,
  loopback cookie with a bounded Max-Age. The response exposes only owner,
  identity, device, CSRF, and expiry metadata.
- Cookie-backed mutations require `X-JARVIS-CSRF` and, when an Origin header
  is present, a matching loopback HTTP origin and server port. No CORS surface
  is added.
- Existing bearer/device/identity clients remain supported and continue to
  authenticate through the original identity authority.
- Owner filters are checked against the authenticated principal. Conversation
  history and all projection reads are owner-bound.
- Static assets send `X-Content-Type-Options: nosniff` and a strict CSP with
  same-origin scripts/styles/connectivity, no `unsafe-eval`, and no remote
  sources.
- Frontend source contains no credential storage, whole-payload logging,
  remote URLs, raw audio handling, or screenshot persistence. Memory edits and
  deletes call the canonical memory application methods.

The legacy `/health`, `/hud`, and `/experience/hud` public compatibility
routes remain unchanged in purpose. The old HUD remains a fallback/diagnostic
surface while `/app` is the daily product.
