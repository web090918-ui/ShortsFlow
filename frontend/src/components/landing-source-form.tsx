"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { youtubeVideoId } from "@/lib/youtube-player";

export function LandingSourceForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!youtubeVideoId(url.trim())) {
      setError("올바른 YouTube 영상 링크를 입력해 주세요.");
      return;
    }
    setError(null);
    router.push(`/video?url=${encodeURIComponent(url.trim())}`);
  }

  return (
    <form onSubmit={submit} noValidate>
      <label className="poster-input-label" htmlFor="landing-video-url">YouTube 영상 링크</label>
      <div className="poster-input-row">
        <input id="landing-video-url" type="url" value={url} onChange={(event) => { setUrl(event.target.value); setError(null); }} placeholder="영상 링크를 붙여넣으세요" aria-invalid={Boolean(error)} aria-describedby={error ? "landing-url-error" : undefined} autoComplete="url" />
        <button type="submit">시작 <span aria-hidden="true">→</span></button>
      </div>
      {error ? <p id="landing-url-error" className="poster-input-error" role="alert">{error}</p> : null}
    </form>
  );
}
