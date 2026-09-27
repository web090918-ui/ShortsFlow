"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { API_URL } from "@/config";

type InputMode = "url" | "upload";

type Source = {
  id: string;
  type: "YOUTUBE" | "PRODUCT" | "UPLOAD";
  status: "CREATED";
};

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
        response = await fetch(`${API_URL}/sources`, {
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

      const payload = await response.json();
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : null;
        throw new Error(detail ?? "Source를 생성하지 못했습니다.");
      }

      setSource(payload as Source);
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
          {isSubmitting ? "Source 생성 중..." : "Source 생성"}
        </button>
      </form>

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {source ? (
        <div className="source-result" aria-live="polite">
          <span>{source.type}</span>
          <strong>{source.status}</strong>
          <code>{source.id}</code>
        </div>
      ) : null}
    </section>
  );
}
