const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("platformRuntime", {
  desktop: true,
  apiBase: process.env.PLATFORM_API_URL || "http://localhost:18080",
});
