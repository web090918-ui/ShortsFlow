import type { Metadata } from "next";
import { Suspense } from "react";

import { AffiliateInput } from "@/components/affiliate-input";
import { MemberStudio } from "@/components/member-workspace";

export const metadata: Metadata = {
  title: "글·사진으로 만들기",
  description: "정보·이야기·사진을 짧은 영상으로. 제목과 사진으로 내레이션이 들어간 세로 영상을 만드세요.",
};

export default function WorkspaceAffiliatePage() {
  return (
    <MemberStudio kind="affiliate">
      <Suspense fallback={null}>
        <AffiliateInput />
      </Suspense>
    </MemberStudio>
  );
}
