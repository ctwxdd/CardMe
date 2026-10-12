# CardMe privacy

Photos are processed locally on your Mac. CardMe does not upload photos, photo metadata, filenames, paths, or card identifiers. You do not need an account.

## Optional usage statistics

Statistics are enabled by default. Turn them off in **CardMe → Settings → Privacy**.

Events contain app opens, app version, scan totals, photos flagged for review, scan completion/failure/cancellation, recovery mode and result counts (full-size, preview, thumbnail, review and unrecovered), and support-link clicks. There is no installation identifier.

The website publishes only reported recovery-session and full-size-photo totals for the last 90 days. These exclude users who opt out and may count repeat recoveries. Individual event records remain private.

App opens count launches, not unique people. Result counts may include the same photo recovered more than once. A support-link click does not indicate a donation.

Reports are scheduled for deletion after 90 days; cleanup backlogs may take longer. Uploads are best-effort, have no offline backlog, and never block recovery. Turning statistics off cancels outstanding uploads. Requests already transmitted may still arrive, and earlier records are not deleted by switching the setting off.

Statistics are sent to `https://cardme-control-plane.azurewebsites.net/api/v1/usage` and stored in CardMe’s dedicated Azure account. The administrator dashboard is separate from Pickology.

The Azure hosting service necessarily receives network addresses and may retain request metadata.

## Website and support links

The website counts visits and clicks on download and support links without cookies, persistent identifiers, URLs, or referrers in its event payloads. Do Not Track and Global Privacy Control disable these events. Website hosting still receives connection information such as IP addresses.

Opening the optional Ko-fi link visits an external service governed by its own privacy terms. CardMe records link clicks when usage statistics are enabled; it does not receive payment details or confirm individual donations.

## Public bug reports

Do not attach personal photographs, whole-card images, private recovery logs, credentials, or device identifiers to public issues. Use synthetic data and describe the failure without exposing private material.
