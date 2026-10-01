import type { Metadata } from "next";
import { MemberSettings } from "@/components/member-workspace";
export const metadata: Metadata = { title: "계정 · 제작 설정" };
export default function SettingsPage() { return <MemberSettings />; }
