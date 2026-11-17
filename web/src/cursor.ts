import { useSyncExternalStore } from "react";

// Kleiner Store fuer den Zeitpunkt unter dem Mauszeiger im Chart (hover) und
// die per Tippen fixierte Ablese-Linie (pinned). Die Overhaken-Karte liest ihn,
// ohne dass App/Chart bei jeder Mausbewegung neu rendern.
// Klick auf eine Top-Sturmflut- bzw. Sturmflut-Stufen-Linie im Chart: die
// Karte zeigt dann den Scheitel des Ereignisses bzw. ein Szenario mit Scheitel
// auf der Stufe, bis dieselbe Linie erneut geklickt wird.
export type Scenario =
  | { kind: "event"; rank: number }
  | { kind: "level"; stufe: string; cm: number };

export interface Cursor {
  hover: number | null;
  pinned: number | null;
  scenario: Scenario | null;
}

let state: Cursor = { hover: null, pinned: null, scenario: null };
const listeners = new Set<() => void>();

export function setCursor(patch: Partial<Cursor>): void {
  const next = { ...state, ...patch };
  if (
    next.hover === state.hover &&
    next.pinned === state.pinned &&
    next.scenario === state.scenario
  )
    return;
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

export function sameScenario(a: Scenario | null, b: Scenario | null): boolean {
  if (!a || !b) return a === b;
  if (a.kind === "event" && b.kind === "event") return a.rank === b.rank;
  if (a.kind === "level" && b.kind === "level") return a.stufe === b.stufe;
  return false;
}

/** Szenario setzen bzw. loesen, wenn dieselbe Linie erneut geklickt wird. */
export function toggleScenario(s: Scenario): void {
  setCursor({ scenario: sameScenario(state.scenario, s) ? null : s });
}

/** Nur das Szenario (rendert nicht bei jeder Mausbewegung neu). */
export function useScenario(): Scenario | null {
  return useSyncExternalStore(subscribe, () => state.scenario);
}
