import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

// Zoom/Verschieben fuer die Overhaken-Karte ohne Bibliothek: Die Ebenen
// (Luftbild, Canvas, SVG) liegen in einem Container mit
// `translate(x, y) scale(k)` (Ursprung oben links, Pixel des Rahmens).
// - Strg/Cmd + Mausrad bzw. Trackpad-Pinch (sendet ctrlKey) zoomt um den Zeiger,
//   normales Mausrad scrollt weiter die Seite.
// - Zwei Finger: Pinch-Zoom; ein Finger/Maus ziehen verschiebt, sobald gezoomt.
export interface View {
  k: number;
  x: number;
  y: number;
}

export const MAX_ZOOM = 6;
const IDENTITY: View = { k: 1, x: 0, y: 0 };

function clamp(v: View, w: number, h: number): View {
  const k = Math.min(Math.max(v.k, 1), MAX_ZOOM);
  // Inhalt deckt den Rahmen immer ganz ab (kein leerer Rand).
  const x = Math.min(0, Math.max(w - w * k, v.x));
  const y = Math.min(0, Math.max(h - h * k, v.y));
  return { k, x, y };
}

/** Zoom um den Punkt (cx, cy) in Rahmen-Pixeln um den Faktor f. */
export function zoomAt(v: View, f: number, cx: number, cy: number, w: number, h: number): View {
  const k = Math.min(Math.max(v.k * f, 1), MAX_ZOOM);
  const r = k / v.k;
  return clamp({ k, x: cx - (cx - v.x) * r, y: cy - (cy - v.y) * r }, w, h);
}

/** `ready`: Rahmen ist gerendert (die Karte erscheint erst nach dem Laden). */
export function useZoom(frame: RefObject<HTMLDivElement | null>, ready: boolean) {
  const [view, setView] = useState<View>(IDENTITY);
  const [size, setSize] = useState({ w: 0, h: 0 });
  // Aktive Zeiger (Maus/Finger) fuer Ziehen und Pinch.
  const pts = useRef(new Map<number, { x: number; y: number }>());

  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setSize({ w: r.width, h: r.height });
      setView((v) => clamp(v, r.width, r.height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [frame, ready]);

  // Wheel muss nicht-passiv sein, sonst laesst sich das Seiten-Zoomen nicht
  // unterdruecken (React registriert wheel passiv).
  useEffect(() => {
    const el = frame.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const f = Math.exp(-e.deltaY * 0.01);
      setView((v) => zoomAt(v, f, e.clientX - r.left, e.clientY - r.top, r.width, r.height));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [frame, ready]);

  const local = (e: React.PointerEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top, w: r.width, h: r.height };
  };

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    const p = local(e);
    pts.current.set(e.pointerId, { x: p.x, y: p.y });
    // Zeiger festhalten, damit Ziehen ueber den Rand hinaus weiterlaeuft.
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const prev = pts.current.get(e.pointerId);
    if (!prev) return;
    const p = local(e);
    const all = pts.current;
    if (all.size >= 2) {
      // Pinch: Abstand und Mittelpunkt der ersten beiden Zeiger.
      const ids = [...all.keys()].slice(0, 2);
      const before = ids.map((id) => all.get(id)!);
      all.set(e.pointerId, { x: p.x, y: p.y });
      const after = ids.map((id) => all.get(id)!);
      const dist = (q: { x: number; y: number }[]) => Math.hypot(q[0].x - q[1].x, q[0].y - q[1].y);
      const mid = (q: { x: number; y: number }[]) => ({
        x: (q[0].x + q[1].x) / 2,
        y: (q[0].y + q[1].y) / 2,
      });
      const d0 = dist(before);
      const f = d0 > 0 ? dist(after) / d0 : 1;
      const m0 = mid(before);
      const m1 = mid(after);
      setView((v) => {
        const z = zoomAt(v, f, m0.x, m0.y, p.w, p.h);
        return clamp({ ...z, x: z.x + m1.x - m0.x, y: z.y + m1.y - m0.y }, p.w, p.h);
      });
      return;
    }
    all.set(e.pointerId, { x: p.x, y: p.y });
    const dx = p.x - prev.x;
    const dy = p.y - prev.y;
    if (Math.abs(dx) + Math.abs(dy) > 0) {
      setView((v) => {
        if (v.k <= 1) return v;
        return clamp({ ...v, x: v.x + dx, y: v.y + dy }, p.w, p.h);
      });
    }
  }, []);

  const onPointerEnd = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    pts.current.delete(e.pointerId);
  }, []);

  const zoomBy = useCallback(
    (f: number) => setView((v) => zoomAt(v, f, size.w / 2, size.h / 2, size.w, size.h)),
    [size.w, size.h],
  );
  const reset = useCallback(() => setView(IDENTITY), []);

  return {
    view,
    size,
    zoomBy,
    reset,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: onPointerEnd,
      onPointerCancel: onPointerEnd,
    },
  };
}
