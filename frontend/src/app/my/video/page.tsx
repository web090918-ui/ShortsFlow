import type { Metadata } from "next";
import { Suspense } from "react";

import { MemberStudio } from "@/components/member-workspace";
import { SourceInput } from "@/components/source-input";

export const metadata: Metadata = {
  title: "영상 쇼츠 만들기",
  description: "작업실에서 YouTube 링크나 내 영상 파일로 세로 쇼츠를 만드세요.",
};

export default async function WorkspaceVideoPage({
  searchParams,
}: {
  searchParams: Promise<{ url?: string | string[] }>;
}) {
  const params = await searchParams;
  const initialUrl = typeof params.url === "string" ? params.url : "";
  return (
    <MemberStudio kind="video">
      <Suspense fallback={null}>
        <SourceInput initialUrl={initialUrl} />
      </Suspense>
    </MemberStudio>
  );
}
