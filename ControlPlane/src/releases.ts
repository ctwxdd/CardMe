export type ReleaseDownloads = {
  available: boolean; checkedAt: string; totalDmgDownloads: number | null;
  releases: { version: string; repository: string; downloads: number }[];
};
const repositories = ['CardMe', 'CardMe-releases'];
// Counts are lifetime asset downloads, including repeat and verification downloads.
export function createReleaseDownloads(fetcher: typeof fetch = fetch, now: () => number = Date.now) {
  let cached: ReleaseDownloads | undefined;
  let expires = 0;
  let pending: Promise<ReleaseDownloads> | undefined;
  return async (): Promise<ReleaseDownloads> => {
    if (cached && now() < expires) return cached;
    if (pending) return pending;
    pending = (async () => {
      let result: ReleaseDownloads;
      try {
        const groups = await Promise.all(repositories.map(async repository => {
          const response = await fetcher(`https://api.github.com/repos/ctwxdd/${repository}/releases?per_page=100`, {
            headers: { Accept: 'application/vnd.github+json', 'User-Agent': 'CardMe-statistics' },
            signal: AbortSignal.timeout(5000), redirect: 'error'
          });
          if (!response.ok) throw new Error('Release statistics unavailable');
          const data: unknown = await response.json();
          if (!Array.isArray(data) || data.length > 100) throw new Error('Invalid release response');
          return data.flatMap(release => {
            if (!release || release.draft || typeof release.tag_name !== 'string' || !/^v\d+\.\d+\.\d+$/.test(release.tag_name)) return [];
            const version = release.tag_name.slice(1);
            if (!Array.isArray(release.assets)) throw new Error('Invalid release assets');
            const assets = release.assets.filter((asset: { name?: unknown }) => asset?.name === `CardMe-${version}.dmg`);
            if (assets.length > 1) throw new Error('Duplicate DMG asset');
            if (!assets.length) return [];
            const count = assets[0].download_count;
            if (!Number.isSafeInteger(count) || count < 0) throw new Error('Invalid download count');
            return [{ version, repository, downloads: count as number }];
          });
        }));
        const releases = groups.flat().sort((a, b) => {
          const av = a.version.split('.').map(Number), bv = b.version.split('.').map(Number);
          return bv[0] - av[0] || bv[1] - av[1] || bv[2] - av[2] || a.repository.localeCompare(b.repository);
        });
        const total = releases.reduce((sum, r) => sum + r.downloads, 0);
        if (!Number.isSafeInteger(total)) throw new Error('Invalid download total');
        result = { available: true, checkedAt: new Date(now()).toISOString(), totalDmgDownloads: total, releases };
      } catch {
        result = { available: false, checkedAt: new Date(now()).toISOString(), totalDmgDownloads: null, releases: [] };
      }
      cached = result;
      expires = now() + (result.available ? 300000 : 60000);
      return result;
    })();
    try { return await pending; } finally { pending = undefined; }
  };
}
