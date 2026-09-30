import type { Metadata } from "next";
import { AffiliateInput } from "@/components/affiliate-input";
import { StudioShell } from "@/components/studio-shell";

export const metadata: Metadata = {
  title: "어필리에이트 쇼츠 만들기",
  description: "쿠팡 파트너스 상품 링크에서 콘텐츠 앵글을 고르고, 내레이션과 가격 카드가 포함된 상품 쇼츠를 만드세요.",
};

export default function AffiliatePage() {
  return <StudioShell kind="affiliate"><AffiliateInput /></StudioShell>;
}
