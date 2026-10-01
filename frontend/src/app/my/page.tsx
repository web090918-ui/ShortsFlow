import type { Metadata } from "next";

import { MyWorks } from "@/components/my-works";
import { SiteNav } from "@/components/site-nav";

export const metadata: Metadata = {
  title: "내 작업",
  description: "내 계정으로 만든 쇼츠와 분석 결과를 다시 확인하고 다운로드하세요.",
};

export default function MyPage() {
  return (
    <>
      <SiteNav current="my" />
      <main className="studio-page my-page" id="main-content">
        <div className="studio-shell">
          <header className="studio-heading">
            <div>
              <p className="eyebrow">MY WORKS</p>
              <h1>내가 만든 쇼츠</h1>
              <p>이 계정으로 만든 쇼츠와 분석 결과입니다. 다운로드 링크는 24시간, 파일은 하루 동안 보관됩니다.</p>
            </div>
          </header>
          <MyWorks />
        </div>
      </main>
    </>
  );
}
