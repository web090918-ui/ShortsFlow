import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import "./design.css";

export const metadata: Metadata = {
  title: { default: "컷픽 Cutpick | 영상과 상품 링크로 쇼츠 만들기", template: "%s | 컷픽 Cutpick" },
  description: "YouTube 영상, 내 영상 파일, 상품 링크로 시작하세요. AI의 추천에 내 선택을 더해 세로 쇼츠를 만들고 MP4로 다운로드하세요.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}

