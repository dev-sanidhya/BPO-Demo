/// <reference types="vite/client" />

interface Window {
  platformRuntime?: {
    desktop: boolean;
    apiBase: string;
    sip?: {
      enabled: boolean;
      wsUrl: string;
      host: string;
      extension: string;
      password: string;
    };
  };
}
