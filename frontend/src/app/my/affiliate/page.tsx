import type { Metadata } from "next";
import { Suspense } from "react";

import { AffiliateInput } from "@/components/affiliate-input";
import { MemberStudio } from "@/components/member-workspace";

export const metadata: Metadata = {
  title: "상품 쇼츠 만들기",
  description: "작업실에서 쿠팡 파트너스 상품 링크로 내레이션이 들어간 상품 쇼츠를 만드세요.",
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
