import { html } from '/static/vendor/preact-standalone.module.js';

export function SelectionBar({ count, format, onFormat, onDownload, onClear, visible }) {
  return html`
    <div class=${'sel-pill' + (visible && count > 0 ? ' show' : '')}>
      <span class="sel-txt">已选 <b>${count}</b> 个</span>
      <select class="sel-fmt" value=${format} onChange=${(e) => onFormat(e.target.value)}>
        <option value="best">最高画质</option>
        <option value="1080p">1080p</option>
        <option value="720p">720p</option>
        <option value="480p">480p</option>
        <option value="audio_only">仅音频</option>
      </select>
      <button class="pill-btn prim" disabled=${count === 0} onClick=${onDownload}>↓ 下载</button>
      <button class="pill-btn ghost" onClick=${onClear}>取消</button>
    </div>`;
}
