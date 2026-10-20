export type ApiArea = "core" | "eye";

const configuredOrigin = String(import.meta.env.VITE_EYE_API_URL || "").replace(/\/+$/, "");
export const apiPrefix = String(import.meta.env.VITE_EYE_API_PREFIX || "/api/v1").replace(/\/+$/, "");

export function apiUrl(area: ApiArea, path: string): string {
  const cleanPath = `/${path}`.replace(/\/+/g, "/");
  const areaPath = area === "eye" ? "/eye" : "";
  return `${configuredOrigin}${apiPrefix}${areaPath}${cleanPath}`;
}

export interface DataService {
  request<T>(area: ApiArea, path: string, options?: RequestInit): Promise<T>;
  raw(area: ApiArea, path: string, options?: RequestInit): Promise<Response>;
}

export const httpDataService: DataService = {
  async request<T>(area: ApiArea, path: string, options?: RequestInit) {
    const response = await fetch(apiUrl(area, path), options);
    if (!response.ok) throw response;
    return response.json() as Promise<T>;
  },
  raw: (area, path, options) => fetch(apiUrl(area, path), options),
};
