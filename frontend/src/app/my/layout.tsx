import type { Metadata } from "next";
import { Suspense, type ReactNode } from "react";
import { MemberWorkspace } from "@/components/member-workspace";
export const metadata: Metadata = { robots: { index: false, follow: false } };
export default function MemberLayout({ children }: { children: ReactNode }) {
  return <Suspense fallback={<p role="status">작업실을 불러오는 중...</p>}><MemberWorkspace>{children}</MemberWorkspace></Suspense>;
}
