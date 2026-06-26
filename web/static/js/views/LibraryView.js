import { html } from '/static/vendor/preact-standalone.module.js';
import { useState, useEffect, useRef, useMemo } from '/static/vendor/preact-standalone.module.js';
import { api } from '../api.js';
import { fmtDate, fmtDateFull, fmtDur, cls } from '../util.js';
import { toast } from '../toast.js';
import { confirm } from '../confirm.js';

const SORTS = [['date', '最新'], ['name', '名称'], ['size', '大小']];
const thumbUrl = (f) => (f.thumb ? `/api/library/thumb/file/${encodeURIComponent(f.filename)}` : null);
const fileUrl = (f) => `/api/library/file/${encodeURIComponent(f.filename)}`;
const typeIcon = (f) => (f.type === 'audio' ? '🎵' : '🎬');

export function LibraryView({ saveDir }) {
  const [files, setFiles] = useState([]);
  const [stats, setStats] = useState({ count: 0, total_size_mb: 0 });
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState('date');
  const [mode, setMode] = useState('grid');
  const [group, setGroup] = useState(false);
  const [searchRaw, setSearchRaw] = useState('');
  const [sel, setSel] = useState(null);
  const [playing, setPlaying] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameVal, setRenameVal] = useState('');
  const thumbTried = useRef(false);
  const gridRef = useRef(null);
  const [showTop, setShowTop] = useState(false);

  const load = () => {
    setLoading(true);
    return api.get(`/api/library?sort=${sort}`)
      .then((d) => {
        setFiles(d.files || []);
        setStats({ count: d.count, total_size_mb: d.total_size_mb });
        setLoading(false);
        if (!thumbTried.current && (d.files || []).some((f) => !f.thumb)) {
          thumbTried.current = true;
          api.post('/api/library/thumb/batch').then(() => load()).catch(() => {});
        }
      })
      .catch(() => { setFiles([]); setLoading(false); });
  };

  useEffect(() => { thumbTried.current = false; }, [saveDir]);
  useEffect(() => { load(); }, [sort, saveDir]);
  // Stop preview + cancel rename when selection changes
  useEffect(() => { setPlaying(false); setRenaming(false); }, [sel && sel.filename]);

  const search = searchRaw.trim().toLowerCase();
  const shown = useMemo(
    () => (search ? files.filter((f) => f.filename.toLowerCase().includes(search)) : files),
    [files, search],
  );

  const groups = useMemo(() => {
    if (!group) return [{ label: null, items: shown }];
    const map = new Map();
    for (const f of shown) {
      const key = sort === 'size' ? '' : fmtDateFull(f.modified);
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(f);
    }
    return [...map.entries()].map(([label, items]) => ({ label, items }));
  }, [shown, group, sort]);

  const selFile = (f) => setSel(f);

  const openFile = (fn) => api.post('/api/library/open', { filename: fn })
    .catch(() => toast('无法打开文件', 'err'));

  const delFile = async (f) => {
    if (!(await confirm(`确认删除「${f.filename}」？`))) return;
    try {
      await api.del('/api/library', { filenames: [f.filename] });
      toast('已删除', 'ok');
      if (sel && sel.filename === f.filename) setSel(null);
      load();
    } catch { toast('删除失败', 'err'); }
  };

  const startRename = () => { setRenameVal(sel.filename); setRenaming(true); };
  const commitRename = async () => {
    const next = renameVal.trim();
    setRenaming(false);
    if (!next || next === sel.filename) return;
    try {
      const r = await api.post('/api/library/rename', { old: sel.filename, new: next });
      toast('已重命名', 'ok');
      thumbTried.current = false;
      await load();
      setSel((s) => (s ? { ...s, filename: r.filename } : s));
    } catch (e) { toast(e.message || '重命名失败', 'err'); }
  };

  // ── Media card / row ──
  const card = (f) => {
    const tu = thumbUrl(f);
    const isSel = sel && sel.filename === f.filename;
    return html`
      <div class=${cls('mc', isSel && 'sel')} key=${f.filename} onClick=${() => selFile(f)}>
        <div class="mc-thumb">
          ${tu ? html`<img src=${tu} loading="lazy" />` : html`<div class="mcnothumb">${typeIcon(f)}</div>`}
          <span class="mc-ext">${f.ext.replace('.', '')}</span>
          <div class="mc-acts">
            <button class="mc-act" title="播放" onClick=${(e) => { e.stopPropagation(); selFile(f); setPlaying(true); }}>▶</button>
            <button class="mc-act del" title="删除" onClick=${(e) => { e.stopPropagation(); delFile(f); }}>✕</button>
          </div>
        </div>
        <div class="mc-foot">
          <div class="mc-name" title=${f.filename}>${f.filename}</div>
          <div class="mc-sz">${f.size_mb} MB${f.duration_seconds ? ' · ' + fmtDur(f.duration_seconds) : ''}</div>
        </div>
      </div>`;
  };

  const row = (f) => {
    const tu = thumbUrl(f);
    const isSel = sel && sel.filename === f.filename;
    return html`
      <div class=${cls('mr', isSel && 'sel')} key=${f.filename} onClick=${() => selFile(f)}>
        <div class="mr-thumb">${tu ? html`<img src=${tu} loading="lazy" />` : html`<div class="mrnothumb">${typeIcon(f)}</div>`}</div>
        <div class="mr-name" title=${f.filename}>${f.filename}</div>
        <div class="mr-meta">${f.duration_seconds ? html`<span>${fmtDur(f.duration_seconds)}</span>` : null}<span>${f.size_mb} MB</span><span>${fmtDate(f.modified)}</span></div>
        <div class="mr-acts">
          <button class="ico-btn" title="播放" onClick=${(e) => { e.stopPropagation(); selFile(f); setPlaying(true); }}>▶</button>
          <button class="ico-btn del" title="删除" onClick=${(e) => { e.stopPropagation(); delFile(f); }}>✕</button>
        </div>
      </div>`;
  };

  let grid;
  if (loading) {
    grid = html`<div class="state-box"><div class="spin-wrap"><div class="spin"></div>加载中...</div></div>`;
  } else if (!files.length) {
    grid = html`<div class="state-box"><div class="ico">🎬</div>暂无素材<div class="sub">从热度榜下载视频后将出现在这里</div></div>`;
  } else if (!shown.length) {
    grid = html`<div class="state-box"><div class="ico">🔍</div>没有匹配的文件</div>`;
  } else {
    const render = mode === 'grid' ? card : row;
    grid = groups.map((g, gi) => html`
      ${g.label ? html`<div class="lib-group-label" key=${'l' + gi}>${g.label}</div>` : null}
      ${g.items.map(render)}`);
  }

  return html`
    <section class="view fade-in">
      <div class="lib-toolbar">
        <div class="seg">
          ${SORTS.map(([id, label]) => html`
            <button key=${id} class=${'seg-btn' + (sort === id ? ' on' : '')} onClick=${() => setSort(id)}>${label}</button>`)}
        </div>
        <div class="seg">
          <button class=${'seg-btn' + (mode === 'grid' ? ' on' : '')} onClick=${() => setMode('grid')}>网格</button>
          <button class=${'seg-btn' + (mode === 'list' ? ' on' : '')} onClick=${() => setMode('list')}>列表</button>
        </div>
        <button class=${'fchip' + (group ? ' on' : '')} onClick=${() => setGroup((x) => !x)}>按日期分组</button>
        <div class="search-box">
          <span class="ico">🔍</span>
          <input placeholder="搜索文件名" value=${searchRaw} onInput=${(e) => setSearchRaw(e.target.value)} />
          ${searchRaw ? html`<button class="clear" onClick=${() => setSearchRaw('')}>✕</button>` : null}
        </div>
        <span class="lib-stats">${stats.count} 个文件 · ${stats.total_size_mb} MB</span>
      </div>

      <div class="lib-body">
        <div class="lib-grid-wrap" ref=${gridRef} onScroll=${(e) => setShowTop(e.target.scrollTop > 500)}>
          <div class=${'lib-grid' + (mode === 'list' ? ' list' : '')}>${grid}</div>
          ${showTop ? html`<button class="back-top" title="回到顶部"
            onClick=${() => gridRef.current && gridRef.current.scrollTo({ top: 0, behavior: 'smooth' })}>↑</button>` : null}
        </div>
        <${DetailPanel} sel=${sel} playing=${playing} setPlaying=${setPlaying}
          renaming=${renaming} renameVal=${renameVal} setRenameVal=${setRenameVal}
          startRename=${startRename} commitRename=${commitRename}
          openFile=${openFile} delFile=${delFile} />
      </div>
    </section>`;
}

function DetailPanel({ sel, playing, setPlaying, renaming, renameVal, setRenameVal, startRename, commitRename, openFile, delFile }) {
  if (!sel) {
    return html`
      <aside class="lib-detail">
        <div class="dp-thumb"><div class="dp-empty-thumb"><div class="ico">🎬</div>点击文件查看详情</div></div>
        <div class="dp-body"></div>
      </aside>`;
  }
  const tu = thumbUrl(sel);
  let media;
  if (playing) {
    media = sel.type === 'audio'
      ? html`<audio src=${fileUrl(sel)} controls autoplay></audio>`
      : html`<video src=${fileUrl(sel)} controls autoplay></video>`;
  } else if (tu) {
    media = html`<img src=${tu} /><div class="dp-play-badge" title="播放" onClick=${() => setPlaying(true)}>▶</div>`;
  } else {
    media = html`<div class="dp-empty-thumb"><div class="ico">${typeIcon(sel)}</div></div>
                 <div class="dp-play-badge" title="播放" onClick=${() => setPlaying(true)}>▶</div>`;
  }

  return html`
    <aside class="lib-detail">
      <div class="dp-thumb">${media}</div>
      <div class="dp-body">
        ${renaming
          ? html`<input class="dp-rename" value=${renameVal} autofocus
                   onInput=${(e) => setRenameVal(e.target.value)}
                   onKeyDown=${(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') commitRename(); }}
                   onBlur=${commitRename} />`
          : html`<div class="dp-fname" title="双击重命名" onDblClick=${startRename}>${sel.filename}</div>`}
        <div class="dp-meta">
          <div class="dp-row"><span class="k">大小</span><span class="v">${sel.size_mb} MB</span></div>
          ${sel.duration_seconds ? html`<div class="dp-row"><span class="k">时长</span><span class="v">${fmtDur(sel.duration_seconds)}</span></div>` : null}
          <div class="dp-row"><span class="k">格式</span><span class="v">${sel.ext.replace('.', '').toUpperCase()}</span></div>
          <div class="dp-row"><span class="k">类型</span><span class="v">${sel.type === 'video' ? '视频' : '音频'}</span></div>
          <div class="dp-row"><span class="k">修改时间</span><span class="v">${fmtDateFull(sel.modified)}</span></div>
        </div>
        <div class="dp-actions">
          ${!playing ? html`<button class="dp-btn open" onClick=${() => setPlaying(true)}>▶ 应用内播放</button>` : null}
          <button class="dp-btn ghost" onClick=${() => openFile(sel.filename)}>↗ 用系统播放器打开</button>
          <button class="dp-btn ghost" onClick=${startRename}>✎ 重命名</button>
          <button class="dp-btn del" onClick=${() => delFile(sel)}>✕ 删除</button>
        </div>
      </div>
    </aside>`;
}
