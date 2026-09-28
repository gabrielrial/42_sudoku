// The only module that knows the shape of the API. Everything else imports
// from here, so an endpoint change has one place to land.

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export interface ApiErrorBody {
  error: { code: string; message: string };
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let code = "unknown_error";
    let message = response.statusText;
    try {
      const body = (await response.json()) as ApiErrorBody;
      code = body.error.code;
      message = body.error.message;
    } catch {
      // Not every failure carries the envelope (a proxy 502, say).
    }
    throw new ApiError(code, response.status, message);
  }

  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export interface Health {
  status: string;
  date: string;
}

export const getHealth = (): Promise<Health> => request<Health>("/health");
