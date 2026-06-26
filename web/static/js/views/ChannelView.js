import { html } from '/static/vendor/preact-standalone.module.js';
import { useState, useEffect, useMemo } from '/static/vendor/preact-standalone.module.js';
import { api } from '../api.js';
import { fmtN, avatarColor, initial } from '../util.js';
import { regionPlats } from '../regions.js';

const WINS = [['24h', '24小时'], ['3d', '3天'], ['7d', '7天'], ['30d', '30天']];
const METRICS = [['total_score', '总热度'], ['total_views', '总播放'], ['video_count', '视频数']];
const COLS = [
  ['channel', '频道', false],
  ['video_count', '视频数', true],
  ['total_views', '总播放', true],
  ['total_score', '总热度', true],
  ['avg_score', '平均热度', true],
];

export function ChannelView({ region, plat, win, onPlat, onWin, dataVersion, onPickChannel }) {
  const PLATS = regionPlats(region);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [metric, setMetric] = useState('total_score');
  const [sortKey, setSortKey] = useState('total_score');
  const [sortDir, setSortDir] = useState('desc');

  useEffect(() => {
    let alive = true;
    setLoading(true); setError(false);
    api.get(`/api/channels?region=${region}&platform=${plat}&window=${win}`)
      .then((d) => { if (alive) { setChannels(d.channels || []); setLoading(false); } })
      .catch(() => { if (alive) { setError(true); setLoading(false); } });
    return () => { alive = false; };
  }, [region, plat, win, dataVersion]);

  const chartData = useMemo(() => {
    const sorted = [...channels].sort((a, b) => b[metric] - a[metric]).slice(0, 12);
    const max = sorted.length ? sorted[0][metric] : 1;
    return { rows: sorted, max: max || 1 };
  }, [channels, metric]);

  const tableData = useMemo(() => {
    const dir = sortDir === 'desc' ? -1 : 1;
    return [...channels].sort((a, b) => {
      if (sortKey === 'channel') return dir * String(a.channel).localeCompare(b.channel);
      return dir * (a[sortKey] - b[sortKey]);
    });
  }, [channels, sortKey, sortDir]);

  const setSort = (key) => {
    if (key === sortKey) setSortDir((d) => (d === 'desc' ? 'asc' : 'desc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const metricLabel = METRICS.find((m) => m[0] === metric)[1];

  let body;
  if (loading) {
    body = html`<div class="state-box"><div class="spin-wrap"><div class="spin"></div>加载中...</div></div>`;
  } else if (error) {
    body = html`<div class="state-box"><div class="ico">⚠</div>加载失败，请重试</div>`;
  } else if (!channels.length) {
    body = html`<div class="state-box"><div class="ico">📊</div>暂无频道数据<div class="sub">先在热度榜采集视频</div></div>`;
  } else {
    body = html`
      <div class="ch-card">
        <div class="ch-card-hdr">
          <span class="ch-card-title">热门频道 Top ${chartData.rows.length}（按${metricLabel}）</span>
          <div class="seg">
            ${METRICS.map(([id, label]) => html`
              <button key=${id} class=${'seg-btn' + (metric === id ? ' on' : '')} onClick=${() => setMetric(id)}>${label}</button>`)}
          </div>
        </div>
        ${chartData.rows.map((c) => html`
          <div class="bar-row" key=${c.channel_id}>
            <span class="bar-label" title=${c.channel} onClick=${() => onPickChannel(c.channel)}>${c.channel}</span>
            <div class="bar-track">
              <div class=${'bar-fill' + (metric === 'total_views' ? ' blue' : '')}
                   style=${`width:${Math.max(2, (c[metric] / chartData.max) * 100)}%`}></div>
            </div>
            <span class="bar-val">${fmtN(c[metric])}</span>
          </div>`)}
      </div>

      <div class="ch-card">
        <div class="ch-card-hdr"><span class="ch-card-title">全部频道（${channels.length}）</span></div>
        <table class="ch-table">
          <thead>
            <tr>
              ${COLS.map(([key, label, num]) => html`
                <th key=${key} style=${num ? '' : 'text-align:left'} onClick=${() => setSort(key)}>
                  ${label}${sortKey === key ? html`<span class="arr"> ${sortDir === 'desc' ? '▾' : '▴'}</span>` : ''}
                </th>`)}
            </tr>
          </thead>
          <tbody>
            ${tableData.map((c) => html`
              <tr key=${c.channel_id}>
                <td>
                  <div class="ch-name-cell" onClick=${() => onPickChannel(c.channel)}>
                    <div class="ch-avatar" style=${`background:${avatarColor(c.channel)}`}>${initial(c.channel)}</div>
                    <span class="ch-name-txt" title=${c.channel}>${c.channel}</span>
                  </div>
                </td>
                <td>${c.video_count}</td>
                <td>${fmtN(c.total_views)}</td>
                <td>${fmtN(c.total_score)}</td>
                <td>${fmtN(c.avg_score)}</td>
              </tr>`)}
          </tbody>
        </table>
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
        <span class="rtoolbar-count">${channels.length} 个频道</span>
      </div>
      <div class="ch-scroll">${body}</div>
    </section>`;
}
