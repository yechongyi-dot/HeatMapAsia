import { html } from '/static/vendor/preact-standalone.module.js';
import { createStore, useStore } from './store.js';

const store = createStore({ items: [] });
let seq = 0;

export function toast(msg, type = 'ok') {
  const id = ++seq;
  store.set((s) => ({ items: [...s.items, { id, msg, type, leaving: false }] }));
  setTimeout(() => {
    store.set((s) => ({ items: s.items.map((t) => (t.id === id ? { ...t, leaving: true } : t)) }));
    setTimeout(() => store.set((s) => ({ items: s.items.filter((t) => t.id !== id) })), 200);
  }, 2800);
}

export function Toasts() {
  const { items } = useStore(store);
  return html`
    <div class="toasts">
      ${items.map((t) => html`
        <div key=${t.id} class=${'toast ' + t.type + (t.leaving ? ' leaving' : '')}>
          <span class="t-dot"></span>${t.msg}
        </div>`)}
    </div>`;
}
