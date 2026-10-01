import type { Metadata } from "next";
import { MyProjects } from "@/components/my-projects";
import { MemberWelcome } from "@/components/member-workspace";
export const metadata: Metadata = { title: "내 작업실", description: "내 쇼츠 프로젝트와 크레딧, 제작 설정을 관리하세요." };
export default function MyPage() {
  return <><MemberWelcome /><h2>내 프로젝트</h2><p>프로젝트를 열어 쇼츠와 분석 결과를 확인하세요. 다운로드 링크는 24시간, 파일은 하루 동안 보관됩니다.</p><MyProjects /></>;
}
