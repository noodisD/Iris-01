/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string;
  readonly VITE_USE_MOCKS?: string;
  readonly VITE_FEATURE_FITBIT_AIR?: string;
  readonly VITE_FEATURE_CONSTELLATION?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
