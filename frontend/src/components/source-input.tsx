"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { API_URL } from "@/config";

type InputMode = "url" | "upload";

type Source = {
  id: string;
  type: "YOUTUBE" | "PRODUCT" | "UPLOAD";
  status: "CREATED" | "PREPARING" | "READY" | "FAILED";
  metadata?: {
    youtube?: {
      title?: string | null;
      channel_title?: string | null;
      duration_seconds?: number | null;
      thumbnail_url?: string | null;
    };
  };
};

async function readSourceResponse(response: Response): Promise<Source> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? "Source를 처리하지 못했습니다.");
  }
  return payload as Source;
}

function formatDuration(seconds?: number | null) {
  if (typeof seconds !== "number") return null;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

export function SourceInput() {
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);

    if (mode === "upload" && !file) {
      setError("업로드할 영상 파일을 선택해 주세요.");
      return;
    }

    setIsSubmitting(true);

    try {
      let response: Response;
      if (mode === "url") {
        response = await fetch(`${API_URL}/sources?prepare=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
      } else {
        const formData = new FormData();
        formData.append("file", file as File);
        response = await fetch(`${API_URL}/sources/upload`, {
          method: "POST",
          body: formData,
        });
      }

      setSource(await readSourceResponse(response));
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Source를 생성하지 못했습니다.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="source-panel" aria-labelledby="source-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">START WITH ONE SOURCE</p>
          <h2 id="source-heading">Shorts 원본을 입력하세요</h2>
        </div>
        <div className="mode-switch" aria-label="Source 입력 방식">
          <button
            className={mode === "url" ? "active" : ""}
            type="button"
            onClick={() => setMode("url")}
          >
            URL
          </button>
          <button
            className={mode === "upload" ? "active" : ""}
            type="button"
            onClick={() => setMode("upload")}
          >
            Upload
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {mode === "url" ? (
          <label className="field">
            <span>YouTube 또는 상품 URL</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://"
              required
            />
          </label>
        ) : (
          <label className="field file-field">
            <span>영상 파일</span>
            <input
              type="file"
              accept="video/*,.mkv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
        )}

        <button className="submit-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "YouTube Source 처리 중..." : "Source 생성"}
        </button>
      </form>

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {source ? (
        <div className="source-result" aria-live="polite">
          <div className="source-result-header">
            <span>{source.type}</span>
            <strong>{source.status}</strong>
          </div>
          {source.metadata?.youtube ? (
            <div className="source-metadata">
              {source.metadata.youtube.thumbnail_url ? (
                // The remote host varies by video, so this stays a plain image.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={source.metadata.youtube.thumbnail_url}
                  alt=""
                />
              ) : null}
              <div>
                <h3>{source.metadata.youtube.title ?? "제목 없음"}</h3>
                <p>
                  {[
                    source.metadata.youtube.channel_title,
                    formatDuration(source.metadata.youtube.duration_seconds),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
          ) : null}
          <code>{source.id}</code>
        </div>
      ) : null}
    </section>
  );
}
