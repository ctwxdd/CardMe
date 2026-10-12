# CardMe statistics service

CardMe owns its own Azure Function, Flex Consumption plan, managed identity, Storage account, Entra application and administrator dashboard in resource group `CardMe`. It has no Pickology runtime, storage, certificate, DNS, Key Vault, or enrollment dependencies.

- Public ingestion: `https://cardme-control-plane.azurewebsites.net/api/v1/usage`
- Protected dashboard: `https://cardme-control-plane.azurewebsites.net/api/v1/admin/usage`
- Protected aggregate JSON: `/api/v1/admin/usage/data`
- Public totals: `/api/v1/public/totals` (reported rescue sessions and full-size photos over the last 90 days, cached for five minutes; no event records or timestamps)
- Health: `/api/health`

Only the CardMe website origin may submit browser events. Native app reports use the same strict anonymous schema without browser credentials. Bodies are limited to 1 KiB; counts and fields are validated, with per-source minute limits, a daily instance limit and bounded limiter storage. Public reports are unverified and counts can include repeats. Daily cleanup deletes reports older than 90 days in bounded batches. No photos, file names, paths, card IDs, user IDs or IP addresses are persisted in event rows. Azure receives connection information as part of hosting.

Easy Auth protects every route except ingestion, public totals and health. Code also requires a bounded, platform-produced Entra principal whose object ID is in `CARDME_ADMIN_OBJECT_IDS`. The dedicated Entra registration and managed identity are independent; sharing the same human administrator does not grant either product access to the other's resources. Administrator HTML uses hashed inline-script/style CSP and text-only DOM rendering.

Run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` here. `scripts/package.sh` produces `../work/cardme-control-plane.zip`. `infra/main.bicep` owns the infrastructure; supply the dedicated Entra registration ID, tenant, secure client secret and administrator object IDs at deployment. Never commit deployment secrets. Deploy the package with Azure CLI `functionapp deployment source config-zip` to `CardMe/cardme-control-plane`.

The optional one-time `scripts/migrate-statistics.mjs` copies a `CardMeUsage` table between explicit endpoints using the maintainer's Azure CLI login. It creates records without overwriting existing events, verifies every copied event, saves only count/status evidence and leaves the source unchanged. Retire the old ingestion route before the final migration pass. Delete the old table only after verification.

Already installed 0.3.23 and earlier clients have the retired endpoint compiled in; their optional uploads fail quietly after removal. Photo recovery remains local and independent of statistics.
