import Link from "next/link";

import { AuthMenu } from "@/components/auth-menu";

type Props = { current?: "home" | "video" | "affiliate" | "my" };

export function SiteNav({ current = "home" }: Props) {
  return (
    <header className="site-header">
      <a className="skip-link" href="#main-content">본문으로 이동</a>
      <nav className="site-nav" aria-label="주요 메뉴">
        <Link href="/" className="brand" aria-label="Cutpick 홈" aria-current={current === "home" ? "page" : undefined}>
          <span className="brand-symbol" aria-hidden="true"><i /><i /></span>
          cutpick<span className="brand-dot">.</span>
        </Link>
        <div className="site-nav-links">
          <Link href="/video" aria-current={current === "video" ? "page" : undefined} className={current === "video" ? "active" : ""}>영상 쇼츠</Link>
          <Link href="/affiliate" aria-current={current === "affiliate" ? "page" : undefined} className={current === "affiliate" ? "active" : ""}>어필리에이트 쇼츠</Link>
        </div>
        <div className="site-nav-right">
          <AuthMenu />
          <Link className="nav-start" href="/#start">쇼츠 만들기 <span aria-hidden="true">↗</span></Link>
        </div>
      </nav>
    </header>
  );
}
