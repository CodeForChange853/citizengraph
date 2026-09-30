/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" forces the local fixture adapter (no Python API needed). */
  readonly VITE_USE_FIXTURES?: string;
}
