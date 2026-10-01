import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_RENDER_OPTIONS } from "@/lib/render-options";

import { LayoutPicker, TemplatePicker } from "./template-picker";

const IMAGE = "https://i.ytimg.com/vi/abc123/hqdefault.jpg";

describe("TemplatePicker", () => {
  afterEach(cleanup);

  it("lists every template with the viewer's frame inside each preview", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="CLEAN_CAPTION"
        onChange={onChange}
        imageUrl={IMAGE}
      />,
    );

    const cards = screen.getAllByRole("button", { name: /템플릿$/ });
    expect(cards).toHaveLength(DEFAULT_RENDER_OPTIONS.templates.length);
    expect(screen.getByRole("button", { name: "클린 템플릿" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    for (const card of cards) {
      const frame = card.querySelector<HTMLElement>(".caption-sample-frame");
      expect(frame?.style.backgroundImage).toContain(IMAGE);
    }

    await user.click(screen.getByRole("button", { name: "헤드라인 레드 템플릿" }));
    expect(onChange).toHaveBeenCalledWith("HEADLINE_RED");
  });

  it("colours the spoken word on karaoke templates only", () => {
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="IMPACT_YELLOW"
        onChange={() => {}}
        imageUrl={IMAGE}
      />,
    );

    const impact = screen.getByRole("button", { name: "임팩트 옐로 템플릿" });
    const spoken = impact.querySelectorAll<HTMLElement>(".caption-sample-caption > span")[2];
    expect(spoken.style.color).toBe("rgb(255, 210, 63)");

    const pop = screen.getByRole("button", { name: "카라오케 팝 템플릿" });
    const popLine = pop.querySelector<HTMLElement>(".caption-sample-caption");
    expect(popLine?.style.backgroundColor).toBe("rgb(17, 17, 17)");
    const popSpoken = pop.querySelectorAll<HTMLElement>(".caption-sample-caption > span")[2];
    expect(popSpoken.style.color).toBe("rgb(215, 255, 79)");

    const clean = screen.getByRole("button", { name: "클린 템플릿" });
    const plain = clean.querySelectorAll<HTMLElement>(".caption-sample-caption > span")[2];
    expect(plain.getAttribute("style")).toBeNull();
  });

  it("shows a neutral frame and a hint until a video is loaded", () => {
    render(
      <TemplatePicker
        templates={DEFAULT_RENDER_OPTIONS.templates}
        value="MINIMAL"
        onChange={() => {}}
        imageUrl={null}
      />,
    );

    expect(screen.getByText(/영상을 불러오면 그 장면이 미리보기에 들어갑니다/)).toBeTruthy();
    expect(document.querySelectorAll(".caption-sample-placeholder").length).toBe(
      DEFAULT_RENDER_OPTIONS.templates.length,
    );
  });
});

describe("LayoutPicker", () => {
  afterEach(cleanup);

  it("previews fill as a cropped frame and fit over a blurred copy", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <LayoutPicker
        layouts={DEFAULT_RENDER_OPTIONS.layouts}
        value="FILL"
        onChange={onChange}
        imageUrl={IMAGE}
      />,
    );

    const fill = screen.getByRole("button", { name: "가득 채우기 배치" });
    const fit = screen.getByRole("button", { name: "원본 + 흐린 배경 배치" });
    const stage = screen.getByRole("button", { name: "제목 + 원본 배치" });
    expect(fill.querySelector(".caption-sample-blur")).toBeNull();
    expect(stage.querySelector(".caption-sample-blur")).toBeNull();
    expect(stage.querySelector(".caption-sample-stage")).toBeTruthy();
    expect(fit.querySelector<HTMLElement>(".caption-sample-blur")?.style.backgroundImage).toContain(IMAGE);
    expect(fit.querySelector(".caption-sample-fit")).toBeTruthy();

    await user.click(fit);
    expect(onChange).toHaveBeenCalledWith("FIT");
  });
});
