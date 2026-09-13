/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API origin; leave unset to call the same origin (dev proxy / nginx). */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
