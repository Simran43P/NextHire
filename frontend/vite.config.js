import { defineConfig } from 'vite'
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    // Pinned to IPv4. Left to itself Vite binds "localhost", which on Windows
    // can resolve to ::1 only - while uvicorn binds 127.0.0.1 only. The two
    // then sit on opposite stacks and http://localhost:5173 is refused in a
    // normal browser, even though everything looks fine from inside an editor
    // that proxies the port.
    host: "127.0.0.1",
    port: 5173,
    // Fail loudly rather than silently moving to 5174, which is not in the
    // backend's CORS allowlist and would surface as unexplained CORS errors.
    strictPort: true,
  },
})
