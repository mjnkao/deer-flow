import { getBackendBaseURL } from "@/core/config";

export function authApiUrl(path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const backendBase = getBackendBaseURL();
  if (!backendBase) return normalizedPath;
  return `${backendBase}${normalizedPath}`;
}
