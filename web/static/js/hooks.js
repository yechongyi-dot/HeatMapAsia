import { useState, useEffect, useRef } from '/static/vendor/preact-standalone.module.js';

// Reveal items incrementally as a sentinel scrolls into view.
// Returns { count, sentinelRef, hasMore }. Resets to `step` when resetKey changes.
export function useIncremental(total, resetKey, step = 60) {
  const [count, setCount] = useState(step);
  const sentinelRef = useRef(null);

  useEffect(() => { setCount(step); }, [resetKey, step]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return undefined;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) setCount((c) => c + step); },
      { rootMargin: '500px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [total, step]);

  return { count: Math.min(count, total), sentinelRef, hasMore: count < total };
}

// Like useState but persisted to localStorage under `key`.
export function usePersistedState(key, initial) {
  const [v, setV] = useState(() => {
    try {
      const s = localStorage.getItem(key);
      return s === null ? initial : JSON.parse(s);
    } catch { return initial; }
  });
  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* ignore quota */ }
  }, [key, v]);
  return [v, setV];
}

// Debounced value hook.
export function useDebounced(value, ms = 200) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
