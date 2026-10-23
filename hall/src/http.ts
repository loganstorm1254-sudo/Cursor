export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export function json(data: unknown, status = 200, headers?: HeadersInit): Response {
  const responseHeaders = new Headers(headers);
  responseHeaders.set("content-type", "application/json; charset=utf-8");
  responseHeaders.set("cache-control", "no-store");
  return new Response(JSON.stringify(data), { status, headers: responseHeaders });
}

export async function readJson(request: Request, maxBytes: number): Promise<unknown> {
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    throw new HttpError(415, "Expected application/json");
  }
  const declared = request.headers.get("content-length");
  if (declared && Number(declared) > maxBytes) {
    throw new HttpError(413, "Request body is too large");
  }
  const body = await request.arrayBuffer();
  if (body.byteLength > maxBytes) {
    throw new HttpError(413, "Request body is too large");
  }
  if (body.byteLength === 0) {
    throw new HttpError(400, "Request body is empty");
  }
  try {
    return JSON.parse(new TextDecoder().decode(body));
  } catch {
    throw new HttpError(400, "Request body is not valid JSON");
  }
}

export function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new HttpError(400, "Expected a JSON object");
  }
  return value as Record<string, unknown>;
}

export function asString(value: unknown, label: string): string {
  if (typeof value !== "string") {
    throw new HttpError(400, `${label} is required`);
  }
  return value;
}
