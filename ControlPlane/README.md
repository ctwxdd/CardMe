# CardMe statistics service

CardMe owns its own Azure Function, Flex Consumption plan, managed identity, Storage account, Entra application and administrator dashboard in resource group `CardMe`. It has no Pickology runtime, storage, certificate, DNS, Key Vault, or enrollment dependencies.

- Public ingestion: `https://cardme-control-plane.azurewebsites.net/api/v1/usage`
- Static sign-in entrance: `https://witty-meadow-00543f01e.6.azurestaticapps.net/admin` (shows connection status immediately, then opens the protected dashboard, reusing an existing login or entering Microsoft login when needed)
- Protected dashboard: `https://cardme-control-plane.azurewebsites.net/api/v1/admin/usage`
- Protected aggregate JSON: `/api/v1/admin/usage/data`
- Health: `/api/health`

Only the CardMe website origin may submit browser events. Native app reports use the same strict anonymous schema without browser credentials. Bodies are limited to 1 KiB; counts and fields are validated, with per-source minute limits, a daily instance limit and bounded limiter storage. Public reports are unverified and counts can include repeats. Daily cleanup deletes reports older than 90 days in bounded batches. No photos, file names, paths, card IDs, user IDs or IP addresses are persisted in event rows. Azure receives connection information as part of hosting.

Easy Auth protects every route except ingestion and health. Code also requires a bounded, platform-produced Entra principal whose object ID is in `CARDME_ADMIN_OBJECT_IDS`. The dedicated Entra registration and managed identity are independent; sharing the same human administrator does not grant either product access to the other's resources. Administrator HTML uses hashed inline-script/style CSP and text-only DOM rendering.

Run `npm ci`, `npm run typecheck`, `npm test`, and `npm run build` here. `scripts/package.sh` produces `../work/cardme-control-plane.zip`. `infra/main.bicep` owns the infrastructure; supply the dedicated Entra registration ID, tenant, secure client secret and administrator object IDs at deployment. Never commit deployment secrets. Deploy the package with Azure CLI `functionapp deployment source config-zip` to `CardMe/cardme-control-plane`.

The dedicated Entra application must register `https://cardme-control-plane.azurewebsites.net/.auth/login/aad/callback` as a Web redirect URI and enable ID-token issuance for Easy Auth's `code id_token` login response. Keep implicit access-token issuance disabled. Configure the dedicated app (not another product's registration) with:

```sh
az ad app update --id YOUR_CARDME_ENTRA_CLIENT_ID --enable-id-token-issuance true
```

The optional one-time `scripts/migrate-statistics.mjs` copies a `CardMeUsage` table between explicit endpoints using the maintainer's Azure CLI login. It creates records without overwriting existing events, verifies every copied event, saves only count/status evidence and leaves the source unchanged. Retire the old ingestion route before the final migration pass. Delete the old table only after verification.

Already installed 0.3.23 and earlier clients have the retired endpoint compiled in; their optional uploads fail quietly after removal. Photo recovery remains local and independent of statistics.
