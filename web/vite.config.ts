import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base = Repo-Name, damit Assets unter
// aaronspring.github.io/wasserstandvorhersage_overwerder/ aufgeloest werden.
export default defineConfig({
  base: "/wasserstandvorhersage_overwerder/",
  plugins: [react()],
  // Zeitpunkt des Frontend-Builds (UTC, ISO-8601) zur Build-Zeit einbacken,
  // damit die Seite anzeigen kann, wie frisch der Deploy ist.
  define: {
    __BUILD_TIME__: JSON.stringify(new Date().toISOString()),
  },
});
