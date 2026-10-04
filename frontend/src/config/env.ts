// Vite exposes VITE_* values to the browser. Keep credentials on the backend.
// Reserved for the future HTTP implementation in services/meetings.ts.
export const config = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL || "http://localhost:7071/api").replace(/\/+$/, ""),
}
