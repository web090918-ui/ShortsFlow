import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AffiliateInput, detectProvider } from "./affiliate-input";

const PARTNERS_URL =
  "https://partners.coupang.com/#affiliate/ws/linkgeneration/PRODUCT/7310929139/25822417217?product%5Btitle%5D=x";

describe("detectProvider", () => {
  it("recognises supported and planned affiliate hosts", () => {
    expect(detectProvider(PARTNERS_URL)?.id).toBe("coupang");
    expect(detectProvider("https://www.agoda.com/hotel")?.status).toBe("planned");
    expect(detectProvider("https://kr.trip.com/hotels")?.id).toBe("trip");
    expect(detectProvider("https://youtube.com/watch?v=1")).toBeNull();
    expect(detectProvider("nonsense")).toBeNull();
  });
});

describe("AffiliateInput", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("explains that planned providers are not available yet without calling the API", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch");

    render(<AffiliateInput />);
    await user.type(screen.getByLabelText("어필리에이트 링크"), "https://www.agoda.com/some-hotel");
    await user.click(screen.getByRole("button", { name: "상품 정보 불러오기" }));

    expect((await screen.findByRole("alert")).textContent).toContain("아고다 링크는 준비 중");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("prepares a Coupang Partners link and shows the product card with the angle action", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: "prod-1",
          type: "PRODUCT",
          status: "READY",
          metadata: {
            product: {
              provider: "coupang_partners",
              product_id: "7310929139",
              title: "코카콜라 오리지널 무라벨, 370ml, 24개",
              origin_price: 28600,
              sales_price: 17990,
              discount_rate: 37,
              image_url: "https://thumbnail5.coupangcdn.com/thumbnails/remote/1000x1000ex/a.jpg",
              product_url: "https://www.coupang.com/vp/products/7310929139",
              facts: ["판매가 17,990원", "37% 할인"],
            },
          },
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<AffiliateInput />);
    await user.type(screen.getByLabelText("어필리에이트 링크"), PARTNERS_URL);
    await user.click(screen.getByRole("button", { name: "상품 정보 불러오기" }));

    expect(await screen.findByText("코카콜라 오리지널 무라벨, 370ml, 24개")).toBeTruthy();
    expect(screen.getByText("17,990원")).toBeTruthy();
    expect(screen.getAllByText("37% 할인").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "콘텐츠 앵글 만들기" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/sources?prepare=true",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ url: PARTNERS_URL }) }),
    );
  });
});
