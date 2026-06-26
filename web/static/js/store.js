import { useState, useEffect } from '/static/vendor/preact-standalone.module.js';

// ─── Minimal observable store ──────────────────────────
export function createStore(initial) {
  let state = initial;
  const subs = new Set();
  return {
    get: () => state,
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : patch;
      state = Object.assign({}, state, next);
      subs.forEach((fn) => fn(state));
    },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
}

// Re-render a component whenever the store changes; returns selected slice.
export function useStore(store, selector = (s) => s) {
  const [, force] = useState(0);
  useEffect(() => store.subscribe(() => force((n) => n + 1)), [store]);
  return selector(store.get());
}
