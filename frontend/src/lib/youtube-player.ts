export type YouTubePlayer = {
  getCurrentTime(): number;
  getPlayerState(): number;
  loadVideoById(options: { videoId: string; startSeconds: number }): void;
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  playVideo(): void;
  pauseVideo(): void;
  destroy(): void;
};

export type YouTubeAPI = {
  Player: new (element: HTMLElement, options: {
    videoId: string;
    width: string;
    height: string;
    playerVars: { origin: string; playsinline: number; rel: number };
    events: {
      onReady(event: { target: YouTubePlayer }): void;
      onError(): void;
      onAutoplayBlocked(): void;
      onStateChange(event: { data: number }): void;
    };
  }) => YouTubePlayer;
};

declare global {
  interface Window {
    YT?: YouTubeAPI;
    onYouTubeIframeAPIReady?: () => void;
  }
}

let apiPromise: Promise<YouTubeAPI> | undefined;

export function loadYouTubeAPI(): Promise<YouTubeAPI> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (apiPromise) return apiPromise;
  apiPromise = new Promise<YouTubeAPI>((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady;
    const script = document.createElement("script");
    const fail = () => {
      window.clearTimeout(timer);
      window.onYouTubeIframeAPIReady = previous;
      script.remove();
      reject(new Error("YouTube 플레이어를 불러오지 못했습니다."));
    };
    const timer = window.setTimeout(fail, 15000);
    window.onYouTubeIframeAPIReady = () => {
      window.clearTimeout(timer);
      window.onYouTubeIframeAPIReady = previous;
      if (window.YT?.Player) resolve(window.YT);
      else reject(new Error("YouTube 플레이어를 불러오지 못했습니다."));
      previous?.();
    };
    script.src = "https://www.youtube.com/iframe_api";
    script.onerror = fail;
    document.head.appendChild(script);
  }).catch((error) => {
    apiPromise = undefined;
    throw error;
  });
  return apiPromise;
}

export function youtubeVideoId(value: string): string | null {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    const parts = url.pathname.split("/").filter(Boolean);
    const id = host === "youtu.be"
      ? parts[0]
      : ["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"].includes(host)
        ? (url.pathname === "/watch" ? url.searchParams.get("v") : ["shorts", "embed", "live"].includes(parts[0]) ? parts[1] : null)
        : null;
    return id && /^[a-zA-Z0-9_-]{11}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}
