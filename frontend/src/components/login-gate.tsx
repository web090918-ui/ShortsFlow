"use client";

import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { loginUrl } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";

/** Shows the wizard when the API allows it, otherwise a sign-in card. */
export function LoginGate({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const loginResult = useSearchParams()?.get("login") ?? null;
  const { status, loading } = useAuthStatus();
  const loginNotice =
    loginResult === "failed"
      ? "Google 로그인에 실패했습니다. 콘솔의 리디렉션 URI와 클라이언트 시크릿이 맞는지, 이 계정이 테스트 사용자로 등록되어 있는지 확인해 주세요."
      : loginResult === "cancelled"
        ? "Google 로그인이 취소되었습니다."
        : null;

  if (loading) {
    return (
      <section className="source-panel" aria-busy="true">
        <p className="range-help">로그인 상태를 확인하는 중...</p>
      </section>
    );
  }

  if (status.auth_required && !status.user) {
    return (
      <section className="source-panel login-gate" aria-labelledby="login-heading">
        <p className="section-label">SIGN IN</p>
        <h2 id="login-heading">로그인하고 시작하세요</h2>
        {loginNotice ? (
          <p className="message error-message" role="alert">
            {loginNotice}
          </p>
        ) : null}
        <p className="range-help">
          만든 쇼츠와 분석 결과는 계정에 저장되어 ‘내 작업’에서 다시 볼 수 있습니다. Google 계정으로
          로그인하면 바로 이어서 진행됩니다.
        </p>
        {status.login_available ? (
          <a className="submit-button auth-login-button" href={loginUrl(pathname)}>
            Google로 로그인
          </a>
        ) : (
          <p className="range-error">로그인이 아직 설정되지 않았습니다. 관리자에게 문의해 주세요.</p>
        )}
      </section>
    );
  }

  return <>{children}</>;
}
