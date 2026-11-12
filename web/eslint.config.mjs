import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";
import jsxA11y from "eslint-plugin-jsx-a11y";

const config = [
  { ignores: [".next/**", "out/**", "next-env.d.ts"] },
  ...nextVitals,
  ...nextTs,
  // Strict accessibility lint on top of Next's defaults (the plugin is already registered by
  // eslint-config-next, so only the rules are added here).
  { rules: jsxA11y.flatConfigs.strict.rules },
];

export default config;
