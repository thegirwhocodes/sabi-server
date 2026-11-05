# sabi-identity-api (Vercel)

Stateless identity lookups that used to require the Vultr box. Reads Supabase
through the canonical learner view, so a caller's identity and consent state are
one HTTP request away from any service.

Deployed: https://sabi-identity-api.vercel.app

| Route | Purpose |
|---|---|
| `GET /api/health` | liveness plus whether Supabase is configured |
| `GET /api/learner?phone=%2B2348036844773` | canonical learner: name status, level, consents, pilot_ready |

## Environment
`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (set on production and preview).

## Next
Fold the remaining read-only admin routes in here, then point the voice app's
identity lookups at this service so the media gateway only streams audio.
