import Link from "next/link";
import type { ReactNode } from "react";
import { LoginGate } from "@/components/login-gate";
import { SiteNav } from "@/components/site-nav";
import { ShortPreview } from "@/components/short-preview";

export function StudioShell({ kind, children }: { kind: "video" | "affiliate"; children: ReactNode }) {
  const video = kind === "video";
  return (
    <>
      <SiteNav current={kind} />
      <main className={`studio-page ${video ? "video-studio" : "affiliate-studio"}`} id="main-content">
        <div className="studio-shell">
          <div className="studio-breadcrumb"><Link href="/">홈</Link><span aria-hidden="true">/</span><span>{video ? "영상 쇼츠" : "어필리에이트 쇼츠"}</span></div>
          <header className="studio-heading"><div><p className="eyebrow">{video ? "VIDEO STUDIO" : "AFFILIATE STUDIO"}</p><h1>{video ? "긴 영상에서, 빛나는 한 장면." : "상품의 매력을, 한 편의 쇼츠로."}</h1><p>{video ? "영상을 가져오고, 마음에 드는 구간을 골라보세요." : "상품을 확인하고, 내 콘텐츠에 맞는 소개 방식을 골라보세요."}</p></div><span className="studio-format">9:16 <span>MP4</span></span></header>
          <div className="studio-grid">
            <div className="studio-workspace"><LoginGate>{children}</LoginGate></div>
            <aside className="studio-guide" aria-label="제작 안내">
              <p className="section-label">YOUR NEXT SHORT</p>
              <ShortPreview variant={video ? "video" : "product"} />
              <p className="preview-disclaimer">디자인 예시 · 실제 생성 결과와 다를 수 있어요</p>
              <h2>{video ? "좋은 장면은 놓치지 않도록" : "소개하고 싶은 이유가 전해지도록"}</h2>
              <ul className="studio-tips">
                <li><span>01</span>{video ? "AI Score로 추천한 Top 3에서 선택" : "상품 정보 확인 후 콘텐츠 앵글 선택"}</li>
                <li><span>02</span>{video ? "원하는 구간은 직접 지정해 제작" : "내레이션과 가격 카드로 상품 소개"}</li>
                <li><span>03</span>완성된 영상 확인 후 MP4 다운로드</li>
              </ul>
              <div className="studio-info">{video ? "직접 소유하거나 이용 허가를 받은 영상만 사용해 주세요." : "현재 쿠팡 파트너스를 지원합니다. 아고다·트립닷컴은 준비 중입니다."}</div>
            </aside>
          </div>
          <div className="studio-bottom-note"><span>cutpick.</span> 소스를 고르고, 나만의 쇼츠를 완성하세요.</div>
        </div>
      </main>
    </>
  );
}
