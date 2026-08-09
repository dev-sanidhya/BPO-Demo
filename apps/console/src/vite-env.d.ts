/// <reference types="vite/client" />

interface Window {
  platformRuntime?: {
    desktop: boolean;
    apiBase: string;
  };
}

