/** Parse an API response, turning non-JSON failures (e.g. a plain-text 429) into a readable error. */
export async function readJsonResponse<T>(response: Response, fallback: string): Promise<T> {
  const text = await response.text();
  let payload: unknown = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && typeof (payload as { detail?: unknown }).detail === "string"
        ? ((payload as { detail: string }).detail as string)
        : null;
    if (detail) throw new Error(detail);
    if (response.status === 429) {
      throw new Error("요청이 너무 많아 잠시 제한되었어요. 1분 뒤 다시 시도해 주세요.");
    }
    if (response.status >= 500) {
      throw new Error(`서버가 응답하지 못했어요 (${response.status}). 잠시 후 다시 시도해 주세요.`);
    }
    const snippet = text.trim().slice(0, 120);
    throw new Error(snippet ? `${fallback} (${response.status}: ${snippet})` : fallback);
  }
  if (payload === null) {
    throw new Error(`${fallback} (서버 응답을 읽을 수 없어요)`);
  }
  return payload as T;
}
