"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { describeCreditBudget, loginUrl, logout } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";

export function AuthMenu() {
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const { status, loading, setStatus } = useAuthStatus();

  if (loading) return <span className="auth-menu" aria-busy="true" />;

  if (status.user) {
    const label = status.user.name ?? status.user.email ?? "내 계정";
    return (
      <div className="auth-menu">
        <Link href="/my" className={pathname === "/my" ? "active" : ""}>
          내 작업
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
        <span className="auth-user" title={status.user.email ?? undefined}>
          {status.user.picture ? (
            // Google avatar hosts vary; a plain image avoids remote-pattern config.
            // eslint-disable-next-line @next/next/no-img-element
            <img src={status.user.picture} alt="" referrerPolicy="no-referrer" />
          ) : null}
          {label}
        </span>
        <button
          type="button"
          className="auth-logout"
          onClick={async () => {
            await logout();
            setStatus({ ...status, user: null });
            router.push("/");
            router.refresh();
          }}
        >
          로그아웃
        </button>
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
