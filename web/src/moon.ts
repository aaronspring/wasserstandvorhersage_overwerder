// Mondphase -> Emoji. Thematisch passend, da die Tide-Amplitude dem Mond folgt:
// Spring-/Nipptiden entstehen bei Voll-/Neumond bzw. den Vierteln.
// Berechnung netzfrei aus dem synodischen Monat (mittlere Lunation), kein
// Anspruch auf astronomische Minutengenauigkeit — fuer die Phasen-Anzeige reicht's.

// Bekannter Neumond als Anker (2000-01-06 18:14 UTC).
const NEW_MOON_REF_MS = Date.UTC(2000, 0, 6, 18, 14, 0);
// Mittlere Laenge eines synodischen Monats in Tagen.
const SYNODIC_DAYS = 29.530588853;
const DAY_MS = 86_400_000;

export interface MoonPhase {
  emoji: string;
  label: string;
  // Anteil der Lunation seit Neumond in [0, 1).
  fraction: number;
}

// 8 Phasen, gleichmaessig ueber die Lunation verteilt (jede ueberdeckt 1/8).
const PHASES: Array<{ emoji: string; label: string }> = [
  { emoji: "🌑", label: "Neumond" },
  { emoji: "🌒", label: "zunehmende Sichel" },
  { emoji: "🌓", label: "erstes Viertel" },
  { emoji: "🌔", label: "zunehmender Mond" },
  { emoji: "🌕", label: "Vollmond" },
  { emoji: "🌖", label: "abnehmender Mond" },
  { emoji: "🌗", label: "letztes Viertel" },
  { emoji: "🌘", label: "abnehmende Sichel" },
];

export function moonPhase(atMs: number = Date.now()): MoonPhase {
  const age = ((atMs - NEW_MOON_REF_MS) / DAY_MS) % SYNODIC_DAYS;
  const fraction = (age < 0 ? age + SYNODIC_DAYS : age) / SYNODIC_DAYS;
  // Index um eine halbe Segmentbreite versetzt, damit Voll-/Neumond in der
  // Mitte ihres Segments liegen statt an dessen Kante.
  const index = Math.floor(fraction * 8 + 0.5) % 8;
  return { ...PHASES[index], fraction };
}
