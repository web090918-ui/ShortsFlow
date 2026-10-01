import type { Metadata } from "next";

import { ProjectDetail } from "@/components/my-projects";

export const metadata: Metadata = {
  title: "프로젝트",
  description: "이 원본 영상으로 만든 쇼츠와 AI 분석 결과입니다.",
};

export default async function ProjectPage({ params }: { params: Promise<{ sourceId: string }> }) {
  const { sourceId } = await params;
  return (
    <ProjectDetail sourceId={sourceId} />
  );
}
