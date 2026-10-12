import type { HttpRequest } from "@azure/functions";
import { HttpError } from "./functions.ts";
export async function readJson(request: HttpRequest, maximumBytes: number): Promise<unknown> {
  let bytes: Uint8Array;
  try {
    if (request.body) {
      const reader = request.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > maximumBytes) {
            await reader.cancel();
            throw new HttpError("body_too_large", 413);
          }
          chunks.push(value);
        }
      } finally { reader.releaseLock(); }
      bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    } else {
      bytes = new Uint8Array(await request.arrayBuffer());
    }
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError("invalid_body", 400);
  }
  if (bytes.byteLength > maximumBytes) {
    throw new HttpError("body_too_large", 413);
  }
  let text: string;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new HttpError("invalid_body", 400);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new HttpError("invalid_json", 400);
  }
}
