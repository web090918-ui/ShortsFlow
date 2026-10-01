import type { Metadata } from "next";
import Link from "next/link";

import { MyProjects } from "@/components/my-projects";
import { SiteNav } from "@/components/site-nav";

export const metadata: Metadata = {
  title: "내 프로젝트",
  description: "원본 영상별로 만든 쇼츠와 AI 분석 결과를 다시 확인하고 다운로드하세요.",
};

export default function MyPage() {
  return (
    <>
      <SiteNav current="my" />
      <main className="studio-page my-page" id="main-content">
        <div className="studio-shell">
          <header className="studio-heading project-heading">
            <div>
              <p className="eyebrow">MY PROJECTS</p>
              <h1>내 프로젝트</h1>
              <p>원본 영상 하나가 프로젝트 하나입니다. 프로젝트를 열면 그 영상으로 만든 쇼츠와 분석 결과가 보입니다. 다운로드 링크는 24시간, 파일은 하루 동안 보관됩니다.</p>
            </div>
            <Link className="submit-button project-new" href="/video">
              새 쇼츠 만들기 →
            </Link>
          </header>
          <MyProjects />
        </div>
      </main>
    </>
  );
}
