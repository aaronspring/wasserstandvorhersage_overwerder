import { useSyncExternalStore } from "react";

// Kleiner Store fuer den Zeitpunkt unter dem Mauszeiger im Chart (hover) und
// die per Tippen fixierte Ablese-Linie (pinned). Die Overhaken-Karte liest ihn,
// ohne dass App/Chart bei jeder Mausbewegung neu rendern.
export interface Cursor {
  hover: number | null;
  pinned: number | null;
}

let state: Cursor = { hover: null, pinned: null };
const listeners = new Set<() => void>();

export function setCursor(patch: Partial<Cursor>): void {
  const next = { ...state, ...patch };
  if (next.hover === state.hover && next.pinned === state.pinned) return;
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useCursor(): Cursor {
  return useSyncExternalStore(subscribe, () => state);
}
