"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type Props = {
  /** The job whose start should trigger the notice; a new id shows it again. */
  jobId: string | null;
  /** Where "내 프로젝트" leads; the project page when the source is known. */
  projectHref?: string;
};

/**
 * Layer popup shown once per started render: the work runs on the server, so the
 * creator may leave and collect the result from 내 프로젝트.
 */
export function BackgroundNotice({ jobId, projectHref = "/my" }: Props) {
  const [openFor, setOpenFor] = useState<string | null>(null);
  const seen = useRef<string | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!jobId || seen.current === jobId) return;
    seen.current = jobId;
    setOpenFor(jobId);
  }, [jobId]);

  useEffect(() => {
    if (!openFor) return;
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenFor(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openFor]);

  if (!openFor) return null;
  return (
    <div className="layer-backdrop" onClick={() => setOpenFor(null)}>
      <div
        className="layer-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="background-notice-title"
        onClick={(event) => event.stopPropagation()}
      >
        <span className="layer-icon" aria-hidden="true">
          ⏳
        </span>
        <h3 id="background-notice-title">만들기 시작했어요</h3>
        <p>
          페이지를 떠나도 계속 만들어져요.
          <br />
          완성되면 <strong>내 프로젝트</strong>에서 받을 수 있어요.
        </p>
        <div className="layer-actions">
          <button ref={closeButton} type="button" className="submit-button" onClick={() => setOpenFor(null)}>
            여기서 기다리기
          </button>
          <Link className="submit-button secondary-button" href={projectHref}>
            내 프로젝트 보기
          </Link>
        </div>
      </div>
    </div>
  );
}
