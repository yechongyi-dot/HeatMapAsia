import { html } from '/static/vendor/preact-standalone.module.js';
import { useUpdate } from '../update.js';

const LABEL = { download: '正在下载更新…', extract: '正在解压…', done: '更新完成，正在重启…' };

export function UpdateModal() {
  const { active, phase, pct } = useUpdate();
  if (!active) return null;
  return html`
    <div class="overlay">
      <div class="dialog">
        <p>${LABEL[phase] || '正在更新…'}</p>
        <div class="up-bar-wrap"><div class="up-bar" style=${'width:' + pct + '%'}></div></div>
        <div class="up-pct">${pct}%</div>
      </div>
    </div>`;
}
