import { html } from '/static/vendor/preact-standalone.module.js';
import { useState, useEffect, useMemo, useRef } from '/static/vendor/preact-standalone.module.js';
import { api } from '../api.js';
import { durBucket } from '../util.js';
import { useIncremental, useDebounced, usePersistedState } from '../hooks.js';
import { startDownload } from '../downloads.js';
import { VideoCard } from '../components/VideoCard.js';
import { SelectionBar } from '../components/SelectionBar.js';
import { regionPlats } from '../regions.js';

const WINS = [['24h', '24小时'], ['3d', '3天'], ['7d', '7天'], ['30d', '30天']];
const SORTS = [
  ['score', '热度'], ['views', '播放量'], ['likes', '点赞'],
  ['comments', '评论'], ['duration', '时长'], ['date', '最新'],
];
const DURS = [['all', '全部时长'], ['short', '短(<4分)'], ['mid', '中(4–20分)'], ['long', '长(>20分)']];

const SORT_FN = {
  score: (a, b) => (b.score || 0) - (a.score || 0),
  views: (a, b) => (b.view_count || 0) - (a.view_count || 0),
  likes: (a, b) => (b.like_count || 0) - (a.like_count || 0),
  comments: (a, b) => (b.comment_count || 0) - (a.comment_count || 0),
  duration: (a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0),
  date: (a, b) => (Date.parse(b.published_at || 0) || 0) - (Date.parse(a.published_at || 0) || 0),
};

export function RankView({ region, plat, win, onPlat, onWin, dataVersion, channelFilter, onClearChannelFilter }) {
  const PLATS = regionPlats(region);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [searchRaw, setSearchRaw] = useState('');
  const search = useDebounced(searchRaw, 180).trim().toLowerCase();
  const [sort, setSort] = usePersistedState('hm.sort', 'score');
  const [dur, setDur] = useState('all');
  const [noShorts, setNoShorts] = useState(false);
  const [noLive, setNoLive] = useState(false);

  const [picked, setPicked] = useState(() => new Set());
  const [format, setFormat] = usePersistedState('hm.format', 'best');

  const scrollRef = useRef(null);
  const searchRef = useRef(null);
  const [showTop, setShowTop] = useState(false);

  const hasFilters = !!(search || dur !== 'all' || noShorts || noLive || channelFilter);
  const clearFilters = () => {
    setSearchRaw(''); setDur('all'); setNoShorts(false); setNoLive(false);
    if (channelFilter) onClearChannelFilter();
  };

  // "/" focuses the search box (unless already typing in a field)
  useEffect(() => {
    const h = (e) => {
      if (e.key === '/' && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
        e.preventDefault();
        searchRef.current && searchRef.current.focus();
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  // Fetch when region / platform / window changes
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(false); setPicked(new Set());
    api.get(`/api/videos?region=${region}&platform=${plat}&window=${win}&limit=300`)
      .then((d) => { if (alive) { setVideos(d.videos || []); setLoading(false); } })
      .catch(() => { if (alive) { setError(true); setLoading(false); } });
    return () => { alive = false; };
  }, [region, plat, win, dataVersion]);

  // Escape clears the current selection
  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') setPicked(new Set()); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);

  // Filter + sort (memoised)
  const filtered = useMemo(() => {
    let list = videos;
    if (channelFilter) list = list.filter((v) => v.channel === channelFilter);
    if (search) list = list.filter((v) => (`${v.title} ${v.channel}`).toLowerCase().includes(search));
    if (dur !== 'all') list = list.filter((v) => durBucket(v.duration_seconds) === dur);
    if (noShorts) list = list.filter((v) => !v.is_short);
    if (noLive) list = list.filter((v) => !v.is_live);
    return [...list].sort(SORT_FN[sort]);
  }, [videos, channelFilter, search, dur, noShorts, noLive, sort]);

  const resetKey = `${region}|${plat}|${win}|${search}|${sort}|${dur}|${noShorts}|${noLive}|${channelFilter || ''}`;
  const { count, sentinelRef, hasMore } = useIncremental(filtered.length, resetKey);

  const togglePick = (vid) => setPicked((prev) => {
    const next = new Set(prev);
    if (next.has(vid)) next.delete(vid); else next.add(vid);
    return next;
  });
  const clearSel = () => setPicked(new Set());

  const dlOne = (v) => startDownload(
    [{ video_id: v.video_id, platform: plat, title: v.title, thumbnail_url: v.thumbnail_url || '' }],
    format,
  );
  const dlSelected = () => {
    const items = filtered.filter((v) => picked.has(v.video_id))
      .map((v) => ({ video_id: v.video_id, platform: plat, title: v.title, thumbnail_url: v.thumbnail_url || '' }));
    if (!items.length) return;
    startDownload(items, format, ({ ok }) => { if (ok) clearSel(); });
  };

  let body;
  if (loading) {
    body = html`<div class="state-box"><div class="spin-wrap"><div class="spin"></div>加载中...</div></div>`;
  } else if (error) {
    body = html`<div class="state-box"><div class="ico">⚠</div>加载失败，请重试</div>`;
  } else if (!videos.length) {
    body = html`<div class="state-box"><div class="ico">📭</div>暂无数据<div class="sub">点击右上角 ⟳ 采集最新视频</div></div>`;
  } else if (!filtered.length) {
    body = html`<div class="state-box"><div class="ico">🔍</div>没有匹配的视频<div class="sub">试试调整搜索或筛选条件</div></div>`;
  } else {
    body = html`
      <div class="rank-grid">
        ${filtered.slice(0, count).map((v, i) => html`
          <${VideoCard} key=${v.video_id} v=${v} rank=${i + 1}
            picked=${picked.has(v.video_id)} onPick=${togglePick} onDownload=${dlOne} />`)}
        ${hasMore ? html`<div class="load-more" ref=${sentinelRef}>加载更多…</div>` : null}
      </div>`;
  }

  return html`
    <section class="view fade-in">
      <div class="rtoolbar">
        <div class="seg">
          ${PLATS.map(([id, label]) => html`
            <button key=${id} class=${'seg-btn' + (plat === id ? ' on' : '')} onClick=${() => onPlat(id)}>${label}</button>`)}
        </div>
        <div class="seg">
          ${WINS.map(([id, label]) => html`
            <button key=${id} class=${'seg-btn' + (win === id ? ' on' : '')} onClick=${() => onWin(id)}>${label}</button>`)}
        </div>
        <div class="search-box">
          <span class="ico">🔍</span>
          <input ref=${searchRef} placeholder="搜索标题 / 频道  (按 / 聚焦)" value=${searchRaw}
                 onInput=${(e) => setSearchRaw(e.target.value)} />
          ${searchRaw ? html`<button class="clear" onClick=${() => setSearchRaw('')}>✕</button>` : null}
        </div>
        <select class="sel-input" value=${sort} onChange=${(e) => setSort(e.target.value)}>
          ${SORTS.map(([id, label]) => html`<option key=${id} value=${id}>${label}</option>`)}
        </select>
        <select class="sel-input" value=${dur} onChange=${(e) => setDur(e.target.value)}>
          ${DURS.map(([id, label]) => html`<option key=${id} value=${id}>${label}</option>`)}
        </select>
        <div class="chip-row">
          <button class=${'fchip' + (noShorts ? ' on' : '')} onClick=${() => setNoShorts((x) => !x)}>排除 Shorts</button>
          <button class=${'fchip' + (noLive ? ' on' : '')} onClick=${() => setNoLive((x) => !x)}>排除直播</button>
          ${channelFilter ? html`
            <button class="fchip on" onClick=${onClearChannelFilter} title="清除频道筛选">
              频道: ${channelFilter} <span class="x">✕</span>
            </button>` : null}
          ${hasFilters ? html`<button class="fchip clear-all" onClick=${clearFilters}>清除筛选 ✕</button>` : null}
        </div>
        <span class="rtoolbar-count">${filtered.length} / ${videos.length} 个视频</span>
      </div>
      <div class="rank-scroll" ref=${scrollRef} onScroll=${(e) => setShowTop(e.target.scrollTop > 500)}>${body}</div>
      ${showTop ? html`<button class="back-top" title="回到顶部"
        onClick=${() => scrollRef.current && scrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })}>↑</button>` : null}
      <${SelectionBar} count=${picked.size} format=${format} onFormat=${setFormat}
        onDownload=${dlSelected} onClear=${clearSel} visible=${true} />
    </section>`;
}
