"use client";

import { useEffect, useRef } from "react";

import { loadYouTubeAPI } from "@/lib/youtube-player";
import type { YouTubePlayer } from "@/lib/youtube-player";

type Props = {
  videoId: string;
  startSeconds: number;
};

/**
 * The actual YouTube frame at a candidate's start: a muted player cued to that
 * second and paused, so the preview shows the scene itself. Clicking it plays
 * (muted) from there. Mounted only when scrolled into view.
 */
export function CandidateScene({ videoId, startSeconds }: Props) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element || typeof window === "undefined" || !("IntersectionObserver" in window)) return;
    let cancelled = false;
    let player: YouTubePlayer | null = null;
    let mount: HTMLDivElement | null = null;

    const create = () => {
      if (cancelled || mount) return;
      mount = document.createElement("div");
      element.appendChild(mount);
      const target = Math.max(0, startSeconds + 1);
      loadYouTubeAPI()
        .then((api) => {
          if (cancelled || !mount) return;
          player = new api.Player(mount, {
            videoId,
            width: "100%",
            height: "100%",
            playerVars: {
              origin: window.location.origin,
              playsinline: 1,
              rel: 0,
              controls: 0,
              mute: 1,
              start: Math.floor(target),
              modestbranding: 1,
            },
            events: {
              onReady: ({ target: ready }) => {
                if (cancelled) return;
                ready.mute();
                // Seeking an unstarted player loads that frame; pausing keeps it on screen.
                ready.seekTo(target, true);
                ready.pauseVideo();
              },
              onError: () => undefined,
              onAutoplayBlocked: () => undefined,
              onStateChange: () => undefined,
            },
          });
        })
        .catch(() => undefined);
    };

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        create();
        observer.disconnect();
      }
    });
    observer.observe(element);

    return () => {
      cancelled = true;
      observer.disconnect();
      player?.destroy();
      mount?.remove();
    };
  }, [videoId, startSeconds]);

  return <div ref={host} className="candidate-scene" aria-hidden="true" />;
}
