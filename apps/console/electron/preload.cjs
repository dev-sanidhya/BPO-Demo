const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("platformRuntime", {
  desktop: true,
  apiBase: process.env.PLATFORM_API_URL || "http://localhost:18080",
  sip: {
    enabled: process.env.PLATFORM_SIP_ENABLED === "true",
    wsUrl: process.env.PLATFORM_SIP_WS_URL || "ws://localhost:8088/ws",
    host: process.env.PLATFORM_SIP_HOST || "localhost",
    extension: process.env.PLATFORM_SIP_EXTENSION || "1001",
    password: process.env.PLATFORM_SIP_PASSWORD || "changeme1001",
  },
});
