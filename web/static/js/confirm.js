import { html } from '/static/vendor/preact-standalone.module.js';
import { createStore, useStore } from './store.js';

const store = createStore({ open: false, msg: '', okText: '删除', resolve: null });

// confirm(msg) -> Promise<boolean>
export function confirm(msg, okText = '删除') {
  return new Promise((resolve) => {
    store.set({ open: true, msg, okText, resolve });
  });
}

function close(result) {
  const { resolve } = store.get();
  store.set({ open: false, resolve: null });
  if (resolve) resolve(result);
}

export function ConfirmHost() {
  const { open, msg, okText } = useStore(store);
  if (!open) return null;
  return html`
    <div class="overlay" onClick=${(e) => { if (e.target === e.currentTarget) close(false); }}>
      <div class="dialog">
        <p>${msg}</p>
        <div class="dialog-btns">
          <button class="dbtn cancel" onClick=${() => close(false)}>取消</button>
          <button class="dbtn danger" onClick=${() => close(true)}>${okText}</button>
        </div>
      </div>
    </div>`;
}
