// @ts-check
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

/**
 * Lint rules for the admin panel.
 *
 * `tsc --noEmit` already catches type errors, so this is here for the class it
 * cannot see: hook dependency mistakes. A stale closure in a query or mutation
 * shows an operator data from a previous render, which on a payments screen is
 * a wrong number acted upon, not a cosmetic bug.
 */
export default tseslint.config(
  { ignores: ["dist", "public/locales", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // An unused argument named with a leading underscore is deliberate.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Node scripts, not browser code.
    files: ["scripts/**/*.mjs", "eslint.config.js", "vite.config.ts"],
    languageOptions: { globals: { process: "readonly", console: "readonly" } },
  },
);
