import type { Metadata } from "next";
import { SourceInput } from "@/components/source-input";
import { StudioShell } from "@/components/studio-shell";

export const metadata: Metadata = {
  title: "영상으로 쇼츠 만들기",
  description: "YouTube 링크나 내 영상 파일에서 구간을 선택하고, AI 추천 Top 3로 세로 쇼츠를 만들어 다운로드하세요.",
};

export default function VideoPage() {
  return <StudioShell kind="video"><SourceInput /></StudioShell>;
}
