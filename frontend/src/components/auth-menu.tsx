"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { describeCreditBudget, loginUrl, logout } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";

export function AuthMenu({ compact = false }: { compact?: boolean }) {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const { status, loading, setStatus } = useAuthStatus();
  const [logoutError, setLogoutError] = useState("");

  if (loading) return <span className="auth-menu" aria-busy="true" />;

  if (status.user) {
    const label = status.user.name ?? status.user.email ?? "내 계정";
    return (
      <div className="auth-menu">
        <Link href="/my" className={pathname.startsWith("/my") ? "active" : ""}>
          내 프로젝트
        </Link>
        {typeof status.credits === "number" ? (
          <Link
            href="/my"
            className="credit-badge"
            title={describeCreditBudget(status) ?? "남은 크레딧"}
          >
            크레딧 <strong>{status.credits}</strong>
          </Link>
        ) : null}
        {!compact ? <span className="auth-user" title={status.user.email ?? undefined}>
          {status.user.picture ? (
            // Google avatar hosts vary; a plain image avoids remote-pattern config.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={status.user.picture} alt="" referrerPolicy="no-referrer" />
          ) : null}
          {!compact ? label : null}
        </span> : null}
        <button
          type="button"
          className="auth-logout"
          onClick={async () => {
            try {
              setLogoutError("");
              await logout();
              setStatus({ ...status, user: null, credits: null });
              router.push("/");
              router.refresh();
            } catch { setLogoutError("로그아웃하지 못했습니다. 다시 시도해 주세요."); }
          }}
        >
          {compact ? "Logout" : "로그아웃"}
        </button>
        {logoutError ? <span role="alert">{logoutError}</span> : null}
      </div>
    );
  }

  if (!status.login_available) return null;

  return (
    <div className="auth-menu">
      <a className="auth-login" href={loginUrl(pathname)}>
        Google로 로그인
      </a>
    </div>
  );
}
