// Region metadata for the UI — mirrors scraper/regions.py.
// Each region lists the platforms (tabs) available in that market.

export const REGIONS = [
  { id: 'jp', name: '日本',  flag: '🇯🇵', plats: [['youtube', 'YouTube'], ['official', '官方'], ['niconico', 'ニコニコ']] },
  { id: 'kr', name: '韩国',  flag: '🇰🇷', plats: [['youtube', 'YouTube'], ['official', '官方']] },
  { id: 'sg', name: '新加坡', flag: '🇸🇬', plats: [['youtube', 'YouTube'], ['official', '官方']] },
];

const byId = (id) => REGIONS.find((r) => r.id === id) || REGIONS[0];

// Platform [id,label] pairs available in a region.
export const regionPlats = (id) => byId(id).plats;

// Whether a platform tab exists in a region (jp has niconico, kr/sg don't).
export const regionHasPlat = (id, plat) => regionPlats(id).some(([p]) => p === plat);
