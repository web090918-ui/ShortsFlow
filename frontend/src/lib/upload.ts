import { API_URL } from "@/config";

export type UploadTarget =
  | { mode: "signed_put"; url: string; headers: Record<string, string> }
  | { mode: "direct"; url: string };

/** Read a video file's duration in the browser so the server never has to probe it. */
export function readVideoDuration(file: File, timeoutMs = 8000): Promise<number | null> {
  return new Promise((resolve) => {
    if (typeof document === "undefined") {
      resolve(null);
      return;
    }
    const video = document.createElement("video");
    const url = URL.createObjectURL(file);
    let settled = false;
    const finish = (value: number | null) => {
      if (settled) return;
      settled = true;
      URL.revokeObjectURL(url);
      video.removeAttribute("src");
      resolve(value);
    };
    const timer = window.setTimeout(() => finish(null), timeoutMs);
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      window.clearTimeout(timer);
      finish(Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null);
    };
    video.onerror = () => {
      window.clearTimeout(timer);
      finish(null);
    };
    video.src = url;
  });
}

let durationReader = readVideoDuration;

/** Test hook: jsdom cannot decode media, so tests supply the duration. */
export function setDurationReaderForTests(reader: typeof readVideoDuration | null) {
  durationReader = reader ?? readVideoDuration;
}

export function currentDurationReader() {
  return durationReader;
}

/** Send the bytes where the API told us to; the API itself only sees small requests. */
export async function putUpload(target: UploadTarget, file: File): Promise<void> {
  const url = target.mode === "signed_put" ? target.url : `${API_URL}${target.url}`;
  const headers: Record<string, string> =
    target.mode === "signed_put" ? target.headers : { "Content-Type": file.type || "video/mp4" };
  const response = await fetch(url, { method: "PUT", headers, body: file });
  if (!response.ok) {
    throw new Error(
      target.mode === "signed_put"
        ? "스토리지에 파일을 올리지 못했습니다. 네트워크를 확인하고 다시 시도해 주세요."
        : "파일을 업로드하지 못했습니다.",
    );
  }
}
