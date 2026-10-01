import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_RENDER_OPTIONS } from "@/lib/render-options";

import {
  BrandColorPicker,
  CaptionPositionPicker,
  LayoutPicker,
  TemplatePicker,
} from "./template-picker";

const IMAGE = "https://i.ytimg.com/vi/abc123/hqdefault.jpg";

describe("TemplatePicker", () => {
  afterEach(cleanup);

  it("lists every template with the viewer's frame inside each preview", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="CAPTION_ACCENT"
        onChange={onChange}
        imageUrl={IMAGE}
      />,
    );

    const cards = screen.getAllByRole("button", { name: /템플릿$/ });
    expect(cards).toHaveLength(DEFAULT_RENDER_OPTIONS.templates.length);
    expect(screen.getByRole("button", { name: "자막 강조형 템플릿" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    for (const card of cards) {
      const frame = card.querySelector<HTMLElement>(".caption-sample-frame");
      expect(frame?.style.backgroundImage).toContain(IMAGE);
    }

    await user.click(screen.getByRole("button", { name: "페이퍼 템플릿" }));
    expect(onChange).toHaveBeenCalledWith("PAPER");
  });

  it("applies the brand colour to the spoken word, the pop word, and the title line", () => {
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="CAPTION_ACCENT"
        onChange={() => {}}
        imageUrl={IMAGE}
        brandColor="#FF4D4F"
        title={"AI가 고른 오늘의\n핵심 장면"}
        channelName="강철 멘탈 동기부여"
      />,
    );

    const accent = screen.getByRole("button", { name: "자막 강조형 템플릿" });
    const spoken = accent.querySelectorAll<HTMLElement>(".caption-sample-caption > span")[2];
    expect(spoken.style.color).toBe("rgb(255, 77, 79)");
    const secondLine = accent.querySelectorAll<HTMLElement>(".caption-sample-headline-line")[1];
    expect(secondLine.querySelector<HTMLElement>("span")?.style.color).toBe("rgb(255, 77, 79)");
    expect(accent.querySelector(".caption-sample-channel")?.textContent).toContain("강철 멘탈 동기부여");

    const pop = screen.getByRole("button", { name: "자막 팝형 템플릿" });
    const popWords = pop.querySelectorAll<HTMLElement>(".caption-sample-caption > span");
    expect(popWords[2].style.color).toBe("rgb(255, 77, 79)");
    expect(popWords[0].getAttribute("style")).toBeNull();

    const minimal = screen.getByRole("button", { name: "다크 미니멀 템플릿" });
    expect(minimal.querySelector(".caption-sample-caption")).toBeNull();
  });

  it("draws light stages with dark text and card chrome in the brand colour", () => {
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="SNS_CARD"
        onChange={() => {}}
        imageUrl={IMAGE}
        brandColor="#3B82F6"
      />,
    );

    const sns = screen.getByRole("button", { name: "SNS 템플릿 템플릿" });
    const sample = sns.querySelector<HTMLElement>(".caption-sample");
    expect(sample?.style.background).toBe("rgb(255, 255, 255)");
    expect(sns.querySelector<HTMLElement>(".caption-sample-pill")?.style.background).toBe("rgb(59, 130, 246)");
    expect(sns.querySelector(".caption-sample-pill")?.textContent).toBe("다시 보게 되는 순간");
    expect(sns.querySelector<HTMLElement>(".caption-sample-headline")?.style.color).toBe("rgb(34, 34, 34)");

    const community = screen.getByRole("button", { name: "커뮤니티 템플릿 템플릿" });
    expect(community.querySelector(".caption-sample-band")?.textContent).toBe("오늘의 화제");
    expect(community.querySelector(".caption-sample-kicker")?.textContent).toBe("실시간 베스트");
  });

  it("shows a neutral frame and a hint until a video is loaded", () => {
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="PAPER"
        onChange={() => {}}
        imageUrl={null}
      />,
    );

    expect(screen.getByText(/영상을 불러오면 그 장면이 미리보기에 들어갑니다/)).toBeTruthy();
    expect(document.querySelectorAll(".caption-sample-placeholder").length).toBe(
      DEFAULT_RENDER_OPTIONS.templates.length,
    );
  });

  it("only moves captions on templates that support position changes", () => {
    render(<TemplatePicker templates={DEFAULT_RENDER_OPTIONS.templates} value="CAPTION_ACCENT" onChange={() => {}} imageUrl={IMAGE} captionPosition="MIDDLE" />);
    expect(screen.getByRole("button", { name: "자막 강조형 템플릿" }).querySelector(".caption-sample-middle")).not.toBeNull();
    expect(screen.getByRole("button", { name: "페이퍼 템플릿" }).querySelector(".caption-sample-bottom")).not.toBeNull();
  });
});

describe("LayoutPicker", () => {
  afterEach(cleanup);

  it("previews stage, fit, and fill placements", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <LayoutPicker
        layouts={DEFAULT_RENDER_OPTIONS.layouts}
        value="STAGE"
        onChange={onChange}
        imageUrl={IMAGE}
        stageColor="#F5F1E8"
      />,
    );

    const fill = screen.getByRole("button", { name: "가득 채우기 배치" });
    const fit = screen.getByRole("button", { name: "원본 + 흐린 배경 배치" });
    const stage = screen.getByRole("button", { name: "제목 + 원본 배치" });
    expect(fill.querySelector(".caption-sample-blur")).toBeNull();
    expect(stage.querySelector<HTMLElement>(".caption-sample")?.style.background).toBe("rgb(245, 241, 232)");
    expect(fit.querySelector<HTMLElement>(".caption-sample-blur")?.style.backgroundImage).toContain(IMAGE);

    await user.click(fit);
    expect(onChange).toHaveBeenCalledWith("FIT");
  });
});

describe("BrandColorPicker and CaptionPositionPicker", () => {
  afterEach(cleanup);

  it("selects swatches and caption positions", async () => {
    const user = userEvent.setup();
    const onColor = vi.fn();
    const onPosition = vi.fn();
    render(
      <>
        <BrandColorPicker swatches={DEFAULT_RENDER_OPTIONS.brand_colors} value="#4FE1E1" onChange={onColor} />
        <CaptionPositionPicker
          positions={DEFAULT_RENDER_OPTIONS.caption_positions}
          value="BOTTOM"
          onChange={onPosition}
        />
      </>,
    );

    expect(screen.getByRole("button", { name: "아쿠아 컬러" }).getAttribute("aria-pressed")).toBe("true");
    await user.click(screen.getByRole("button", { name: "골드 컬러" }));
    expect(onColor).toHaveBeenCalledWith("#FFD23F");

    expect(screen.getByRole("button", { name: "자막 하단" }).getAttribute("aria-pressed")).toBe("true");
    await user.click(screen.getByRole("button", { name: "자막 중앙" }));
    expect(onPosition).toHaveBeenCalledWith("MIDDLE");
  });
});

describe("TemplatePicker screenshot templates", () => {
  afterEach(cleanup);

  it("turns an uploaded screenshot into a selected custom template and can delete it", async () => {
    const user = userEvent.setup();
    const created = {
      id: "user-abc123",
      name: "솔로파티",
      description: "스크린샷에서 만든 내 템플릿",
      tag: "내 템플릿",
      karaoke: false,
      custom: true,
      base: "CAPTION_ACCENT",
      preview: { stage: "#000000", caption: "plain", picture: "0.615", hashtags: "true", channel: "false" },
    };
    const onCreateFromImage = vi.fn().mockResolvedValue(created);
    const onDeleteUserTemplate = vi.fn().mockResolvedValue(undefined);
    const onChange = vi.fn();
    const { rerender } = render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        userTemplates={[]}
        onCreateFromImage={onCreateFromImage}
        onDeleteUserTemplate={onDeleteUserTemplate}
        value="CAPTION_ACCENT"
        onChange={onChange}
        imageUrl={IMAGE}
      />,
    );

    const file = new File(["png"], "short.png", { type: "image/png" });
    await user.upload(screen.getByLabelText("쇼츠 스크린샷 올리기"), file);

    expect(onCreateFromImage).toHaveBeenCalledWith(file);
    expect(onChange).toHaveBeenCalledWith("user-abc123");

    rerender(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        userTemplates={[created]}
        onCreateFromImage={onCreateFromImage}
        onDeleteUserTemplate={onDeleteUserTemplate}
        value="user-abc123"
        onChange={onChange}
        imageUrl={IMAGE}
      />,
    );
    const card = screen.getByRole("button", { name: "솔로파티 템플릿" });
    expect(card.getAttribute("aria-pressed")).toBe("true");
    // The preview draws the picture band at the template's own height.
    const sample = card.querySelector<HTMLElement>(".caption-sample");
    expect(sample?.style.getPropertyValue("--picture")).toBe("61.5%");
    expect(sample?.className).toContain("caption-sample-tall");

    await user.click(screen.getByRole("button", { name: "솔로파티 템플릿 삭제" }));
    expect(onDeleteUserTemplate).toHaveBeenCalledWith("user-abc123");
  });

  it("shows the extraction error on the card", async () => {
    const user = userEvent.setup();
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        onCreateFromImage={vi.fn().mockRejectedValue(new Error("이미지가 너무 큽니다."))}
        value="CAPTION_ACCENT"
        onChange={vi.fn()}
        imageUrl={null}
      />,
    );

    await user.upload(
      screen.getByLabelText("쇼츠 스크린샷 올리기"),
      new File(["png"], "big.png", { type: "image/png" }),
    );

    expect(await screen.findByText("이미지가 너무 큽니다.")).toBeTruthy();
  });
});
