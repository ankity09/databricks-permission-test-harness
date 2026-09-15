# Permission Test Harness — frontend

React 18 + TypeScript + Vite + Tailwind. This is the client for the
[Databricks Permission Test Harness](../README.md); FastAPI serves the built
output (`client/dist`) as static files.

## Commands

```bash
npm install
npm run dev          # Vite dev server with HMR (proxy /api to the FastAPI backend on :8000)
npx tsc --noEmit     # type check (strict)
npm run build        # production build into dist/ (must run before deploy)
npm run lint         # oxlint
```

## Layout

- `src/App.tsx` — tab shell + test loop assembly
- `src/components/` — ChatDock, ScenariosTab, ActivityTab, ResultPanel/Matrix, pickers, IdentityBanner
- `src/store.ts` — Zustand slices (test loop, chat, scenarios, activity, theme, dock width)
- `src/api.ts` — centralized API client
- `src/types.ts` — shared TypeScript contracts
- `src/index.css` + `tailwind.config.ts` — DuBois palette as CSS variables (dark/light themes)

See the [root README](../README.md) for architecture, the trust model, and deployment.
