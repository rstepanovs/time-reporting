/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin; leave unset to call the same origin (dev proxy / nginx). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** `package.json`'s `version`, injected by `vite.config.ts`'s `define`. */
declare const __APP_VERSION__: string;
/** The `VITE_GIT_SHA` build arg baked into `frontend/Dockerfile`'s image; `null` outside Docker. */
declare const __GIT_SHA__: string | null;
