import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadYouTubeAPI, youtubeVideoId, type YouTubeAPI } from "@/lib/youtube-player";
import { SourcePlayer } from "./source-player";

vi.mock("@/lib/youtube-player", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/youtube-player")>(),
  loadYouTubeAPI: vi.fn(),
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("source playback", () => {
  it("accepts supported YouTube URLs and rejects unrelated hosts", () => {
    for (const url of ["https://youtu.be/M7lc1UVf-VE?t=12", "https://www.youtube.com/watch?v=M7lc1UVf-VE", "https://youtube.com/shorts/M7lc1UVf-VE", "https://youtube.com/live/M7lc1UVf-VE"]) {
      expect(youtubeVideoId(url)).toBe("M7lc1UVf-VE");
    }
    expect(youtubeVideoId("https://youtube.com.evil.example/watch?v=M7lc1UVf-VE")).toBeNull();
    expect(youtubeVideoId("bad input")).toBeNull();
  });

  it("marks local video times, seeks when ranges change, stops at the end, and releases the file", async () => {
    const user = userEvent.setup();
    const revoke = vi.fn();
    vi.stubGlobal("URL", class extends URL {
      static createObjectURL = vi.fn(() => "blob:local-video");
      static revokeObjectURL = revoke;
    });
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const props = { file: new File(["video"], "clip.mp4"), start: 10, end: 60, onStart: vi.fn(), onEnd: vi.fn() };
    const view = render(<SourcePlayer {...props} />);
    const video = screen.getByLabelText("업로드 원본 영상") as HTMLVideoElement;
    Object.defineProperty(video, "readyState", { value: 1 });
    fireEvent.loadedMetadata(video);
    video.currentTime = 25.9;
    fireEvent.timeUpdate(video);
    await user.click(screen.getByRole("button", { name: "현재 시간을 시작으로" }));
    await user.click(screen.getByRole("button", { name: "현재 시간을 종료로" }));
    expect(props.onStart).toHaveBeenCalledWith(25);
    expect(props.onEnd).toHaveBeenCalledWith(25);
    view.rerender(<SourcePlayer {...props} start={20} />);
    expect(video.currentTime).toBe(20);
    expect(play).toHaveBeenCalledOnce();
    view.rerender(<SourcePlayer {...props} start={20} end={50} />);
    expect(video.currentTime).toBe(50);
    play.mockClear();
    await user.click(screen.getByRole("button", { name: "선택 구간 재생" }));
    expect(video.currentTime).toBe(20);
    expect(play).toHaveBeenCalledOnce();
    pause.mockClear();
    video.currentTime = 50;
    fireEvent.timeUpdate(video);
    expect(pause).toHaveBeenCalledOnce();
    view.unmount();
    expect(revoke).toHaveBeenCalledWith("blob:local-video");
  });

  it("controls YouTube playback and handles embedding failures without blocking range inputs", async () => {
    vi.useFakeTimers();
    let options: ConstructorParameters<YouTubeAPI["Player"]>[1];
    const player = { getCurrentTime: vi.fn(() => 30), getPlayerState: vi.fn(() => 2), loadVideoById: vi.fn(), seekTo: vi.fn(), playVideo: vi.fn(), pauseVideo: vi.fn(), destroy: vi.fn() };
    vi.mocked(loadYouTubeAPI).mockResolvedValue({ Player: class {
      constructor(_element: HTMLElement, supplied: typeof options) { options = supplied; return player; }
    } as YouTubeAPI["Player"] });
    const props = { youtubeUrl: "https://youtu.be/M7lc1UVf-VE", start: 10, end: 60, onStart: vi.fn(), onEnd: vi.fn() };
    const view = render(<SourcePlayer {...props} />);
    await act(async () => {});
    act(() => { options.events.onReady({ target: player }); vi.advanceTimersByTime(250); });
    fireEvent.click(screen.getByRole("button", { name: "현재 시간을 시작으로" }));
    expect(props.onStart).toHaveBeenCalledWith(30);
    player.pauseVideo.mockClear();
    fireEvent.click(screen.getByRole("button", { name: "선택 구간 재생" }));
    expect(player.seekTo).toHaveBeenLastCalledWith(10, true);
    expect(player.playVideo).toHaveBeenCalledOnce();
    player.getCurrentTime.mockReturnValue(60);
    act(() => { vi.advanceTimersByTime(250); });
    expect(player.pauseVideo).toHaveBeenCalledOnce();
    player.getPlayerState.mockReturnValue(-1);
    view.rerender(<SourcePlayer {...props} start={15} />);
    expect(player.loadVideoById).toHaveBeenLastCalledWith({ videoId: "M7lc1UVf-VE", startSeconds: 15 });
    act(() => { options.events.onAutoplayBlocked(); });
    expect(screen.getByRole("status").textContent).toContain("브라우저가 재생을 제한");
    act(() => { options.events.onStateChange({ data: 1 }); });
    expect(screen.queryByRole("status")).toBeNull();
    act(() => { options.events.onError(); });
    expect(screen.getByRole("status").textContent).toContain("외부 재생");
    expect((screen.getByRole("button", { name: "선택 구간 재생" }) as HTMLButtonElement).disabled).toBe(true);
    view.unmount();
    expect(player.destroy).toHaveBeenCalledOnce();
  });
});
