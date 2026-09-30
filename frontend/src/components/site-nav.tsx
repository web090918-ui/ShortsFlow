import Link from "next/link";

type Props = { current?: "home" | "video" | "affiliate" };

export function SiteNav({ current = "home" }: Props) {
  return (
    <nav className="site-nav" aria-label="주요 메뉴">
      <Link href="/" className={current === "home" ? "brand active" : "brand"}>
        SHORTSFLOW
      </Link>
      <div className="site-nav-links">
        <Link href="/video" className={current === "video" ? "active" : ""}>
          영상으로 만들기
        </Link>
        <Link href="/affiliate" className={current === "affiliate" ? "active" : ""}>
          상품·여행 링크로 만들기
        </Link>
      </div>
    </nav>
  );
}
