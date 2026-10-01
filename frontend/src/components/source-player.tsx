"use client";

import { useEffect, useRef, useState } from "react";
import { formatTimecode } from "@/lib/timecode";
import { loadYouTubeAPI, youtubeVideoId, type YouTubePlayer } from "@/lib/youtube-player";

type Props = {
  youtubeUrl?: string;
  file?: File;
  start: number;
  end: number;
  onStart: (seconds: number) => void;
  onEnd: (seconds: number) => void;
};

function playYouTubeFrom(player: YouTubePlayer, videoId: string, seconds: number) {
  if ([-1, 5].includes(player.getPlayerState())) {
    player.loadVideoById({ videoId, startSeconds: seconds });
  } else {
    player.seekTo(seconds, true);
    player.playVideo();
  }
}

/** Mount with a source key so a new source always gets a fresh player. */
export function SourcePlayer({ youtubeUrl, file, start, end, onStart, onEnd }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const youtube = useRef<YouTubePlayer | null>(null);
  const stopAt = useRef<number | null>(null);
  const previousRange = useRef({ start, end });
  const pendingStart = useRef(false);
  const [ready, setReady] = useState(false);
  const [current, setCurrent] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [playbackNotice, setPlaybackNotice] = useState<string | null>(null);
  const videoId = youtubeUrl ? youtubeVideoId(youtubeUrl) : null;

  useEffect(() => {
    if (!file || !video.current) return;
    const media = video.current;
    const localUrl = URL.createObjectURL(file);
    media.src = localUrl;
    return () => {
      media.removeAttribute("src");
      URL.revokeObjectURL(localUrl);
    };
  }, [file]);

  useEffect(() => {
    if (!videoId || !host.current) return;
    let cancelled = false;
    let player: YouTubePlayer | null = null;
    let timer: number | undefined;
    const mount = document.createElement("div");
    host.current.appendChild(mount);
    loadYouTubeAPI().then((api) => {
      if (cancelled) return;
      player = new api.Player(mount, {
        videoId, width: "100%", height: "100%",
        playerVars: { origin: window.location.origin, playsinline: 1, rel: 0 },
        events: {
          onReady: ({ target }) => {
            if (cancelled) return;
            youtube.current = target;
            if (pendingStart.current) {
              pendingStart.current = false;
              stopAt.current = previousRange.current.end;
              playYouTubeFrom(target, videoId, previousRange.current.start);
            } else if (previousRange.current.start > 0) {
              target.seekTo(previousRange.current.start, true);
              target.pauseVideo();
            }
            setReady(true);
            timer = window.setInterval(() => {
              const time = target.getCurrentTime();
              if (!Number.isFinite(time)) return;
              setCurrent(time);
              if (stopAt.current !== null && time >= stopAt.current) {
                target.pauseVideo();
                stopAt.current = null;
              }
            }, 250);
          },
          onError: () => {
            if (cancelled) return;
            setReady(false);
            setError("YouTube에서 이 영상의 외부 재생을 허용하지 않거나 영상을 불러올 수 없습니다. 원본 링크에서 확인 후 아래 시간을 직접 입력해 주세요.");
          },
          onAutoplayBlocked: () => {
            if (!cancelled) setPlaybackNotice("브라우저가 재생을 제한했습니다. ‘선택 구간 재생’ 또는 영상의 재생 버튼을 눌러 주세요.");
          },
          onStateChange: ({ data }) => {
            if (!cancelled && data === 1) setPlaybackNotice(null);
          },
        },
      });
    }).catch(() => {
      if (!cancelled) setError("플레이어를 불러오지 못했습니다. 새로고침하거나 원본 링크에서 영상을 확인해 주세요.");
    });
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      youtube.current = null;
      player?.destroy();
      mount.remove();
    };
  }, [videoId]);

  useEffect(() => {
    const previous = previousRange.current;
    previousRange.current = { start, end };
    if (previous.start === start && previous.end === end) return;
    const startChanged = previous.start !== start;
    stopAt.current = startChanged ? end : null;
    const time = startChanged ? start : end;
    pendingStart.current = startChanged && !youtube.current && Boolean(videoId);
    if (youtube.current) {
      if (startChanged && videoId) playYouTubeFrom(youtube.current, videoId, time);
      else { youtube.current.pauseVideo(); youtube.current.seekTo(time, true); }
    }
    if (video.current && video.current.readyState >= 1) {
      video.current.currentTime = time;
      if (startChanged) {
        void video.current.play().catch(() => setPlaybackNotice("‘선택 구간 재생’을 눌러 영상을 확인해 주세요."));
      } else video.current.pause();
    }
  }, [start, end, videoId]);

  function playRange() {
    stopAt.current = end;
    if (youtube.current && videoId) playYouTubeFrom(youtube.current, videoId, start);
    if (video.current) {
      video.current.currentTime = start;
      void video.current.play().catch(() => {
        stopAt.current = null;
        setError("재생 버튼을 눌러 다시 시도해 주세요.");
      });
    }
  }

  function readCurrent() {
    return Math.floor(youtube.current?.getCurrentTime() ?? video.current?.currentTime ?? current);
  }

  return (
    <section className="source-player" aria-label="원본 영상 플레이어" aria-live="off">
      <div className="source-player-heading">
        <strong>원본 영상 확인</strong>
        {videoId ? <a href={`https://www.youtube.com/watch?v=${videoId}`} target="_blank" rel="noreferrer">YouTube에서 보기 ↗</a> : null}
      </div>
      {file ? (
        <video ref={video} controls playsInline preload="metadata" aria-label="업로드 원본 영상"
          onLoadedMetadata={() => { setReady(true); if (video.current) video.current.currentTime = start; }}
          onTimeUpdate={() => {
            const media = video.current;
            if (!media) return;
            setCurrent(media.currentTime);
            if (stopAt.current !== null && media.currentTime >= stopAt.current) {
              media.pause();
              stopAt.current = null;
            }
          }}
          onError={() => { setReady(false); setError("이 파일을 브라우저에서 재생할 수 없습니다. 아래 시간을 직접 입력해 주세요."); }}
        />
      ) : videoId ? <div ref={host} className="source-player-youtube" /> : <p>원본 영상을 불러오면 여기에서 재생할 수 있습니다.</p>}
      {error ? <p className="range-error" role="status">{error}</p> : null}
      {playbackNotice ? <p className="source-player-help" role="status">{playbackNotice}</p> : null}
      <div className="source-player-actions">
        <span>현재 <strong>{formatTimecode(current)}</strong></span>
        <button type="button" disabled={!ready || Math.floor(current) >= end} onClick={() => onStart(readCurrent())}>현재 시간을 시작으로</button>
        <button type="button" disabled={!ready || Math.floor(current) <= start} onClick={() => onEnd(readCurrent())}>현재 시간을 종료로</button>
        <button type="button" disabled={!ready || end <= start} onClick={playRange}>선택 구간 재생</button>
      </div>
      <p className="source-player-help">시작점을 바꾸면 해당 시점부터 재생합니다. 종료점을 바꾸면 마지막 장면으로 이동합니다.</p>
    </section>
  );
}
