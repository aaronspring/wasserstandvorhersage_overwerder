import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base = Repo-Name, damit Assets unter
// aaronspring.github.io/wasserstandvorhersage_overwerder/ aufgeloest werden.
export default defineConfig({
  base: "/wasserstandvorhersage_overwerder/",
  plugins: [react()],
});
