# CardMe website

Independent Azure Static Web App: https://witty-meadow-00543f01e.6.azurestaticapps.net

Run `python3 scripts/build-website.py` and serve `website/dist` as the website root. The generator produces nine locales, canonical links, sitemap, robots policy, and Azure route/security configuration. Direct GitHub Release asset links download the notarized DMG without a CardMe redirect.

Deploy with the manual `Deploy CardMe website` GitHub workflow. Azure resource group and app are both `CardMe`; the deployment secret is `AZURE_STATIC_WEB_APPS_API_TOKEN`. Pickology is untouched.

Anonymous visit and click counts use CardMe’s dedicated Function and Storage in the CardMe resource group; Do Not Track and Global Privacy Control disable them. No cookies, persistent IDs, photo uploads, URLs, or referrers are sent. Ko-fi is optional.
