import { afterEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  renderHook,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ReleaseHistory } from "./Admin";
import { releaseHighlights } from "./releaseNotes";
import { DownloadPage, NotesPage } from "./Public";
import { GuideWorkspace } from "./Guide";
import { ThemeToggle } from "./Theme";
import { Modal } from "./ui";
import { useData } from "./api";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});
const json = (value: unknown) => ({ ok: true, json: async () => value });
const release = (id: string, channel: string) => ({
  id,
  state: { channel, status: "PUBLISHED", reason: "CI accepted" },
  manifest: {
    version: id,
    platform: "windows-x64",
    size: 200,
    minimum_os: "Windows 10/11",
    signature: "UNSIGNED",
    source_archive: {
      filename: "SiCXrtAnalyzer-source.zip",
      size: 500,
      sha256: "c".repeat(64),
      source_revision: "b".repeat(40),
    },
    sha256: "a".repeat(64),
    components: ["VIEWER"],
    notes: "Synthetic release",
    source_revision: "b".repeat(40),
  },
});
describe("download and administrator safeguards", () => {
  it("uses the posted stable release and keeps admin data off the public page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((path:string) => Promise.resolve(path.endsWith("/releases") ? json([release("0.2.0", "BETA"), release("0.1.0", "STABLE")]) : {ok:false,status:401,json:async()=>({detail:"SESSION_REQUIRED"})})),
    );
    render(
      <MemoryRouter>
        <DownloadPage />
      </MemoryRouter>,
    );
    const button = await screen.findByRole("link", {
      name: /Windows 다운로드/,
    });
    expect(button.getAttribute("href")).toBe(
      "/portal-api/releases/0.1.0/download",
    );
    expect(screen.queryByText(/SHA-256/)).toBeNull();
    expect(screen.queryByText("사용 전에 확인하세요")).toBeNull();
    expect(screen.queryByText("사용 가이드", {selector:"h1"})).toBeNull();
    expect(screen.getByRole("link", {name:/GPLv3 소스 다운로드/}).getAttribute("href")).toBe("/portal-api/releases/0.1.0/source");
    expect(screen.queryByText("관리자 인증키")).toBeNull();
  });
  it("does not fabricate a download when no version is published", async () => {
    vi.stubGlobal("fetch", vi.fn((path:string) => Promise.resolve(path.endsWith("/releases") ? json([]) : {ok:false,status:401,json:async()=>({detail:"SESSION_REQUIRED"})})));
    render(
      <MemoryRouter>
        <DownloadPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("설치 파일을 준비 중입니다")).toBeTruthy();
    expect(
      screen.queryByRole("link", { name: /Windows 다운로드/ }),
    ).toBeNull();
  });
  it("keeps the newest request when an obsolete response completes late", async () => {
    let finishFirst: (v: unknown) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn((path: string) =>
        path.endsWith("first")
          ? new Promise((r) => {
              finishFirst = r;
            })
          : Promise.resolve(json("newest")),
      ),
    );
    const hook = renderHook(({ path }) => useData<string>(path), {
      initialProps: { path: "first" },
    });
    hook.rerender({ path: "second" });
    await waitFor(() => expect(hook.result.current.data).toBe("newest"));
    await act(async () => {
      finishFirst(json("obsolete"));
    });
    expect(hook.result.current.data).toBe("newest");
  });
  it("traps modal keyboard focus and supports Escape", () => {
    const close = vi.fn();
    render(
      <Modal labelId="title" onClose={close}>
        <h2 id="title">Version</h2>
        <button>First</button>
        <button>Last</button>
      </Modal>,
    );
    expect(document.activeElement).toBe(screen.getByText("First"));
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText("Last"));
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("First"));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalledOnce();
  });
});

it("navigates master-detail tabs with keyboard and keeps the current screenshot", async()=>{
 const makeTab=(id:string,title:string)=>({id,title,image_id:id,summary:title,steps:["Select actual data"],callouts:[]});
 const data={schema:"xrt_research_guide/v1",groups:[{id:"viewer",title:"Viewer",subtitle:"Read-only",tabs:[makeTab("fit","Fit"),makeTab("zoom","Zoom")]},{id:"roi",title:"ROI",subtitle:"Coordinates",tabs:[makeTab("edit","Edit")]}]};
 render(<MemoryRouter><GuideWorkspace data={data}/></MemoryRouter>);
 fireEvent.keyDown(screen.getByRole("tab",{name:"Fit"}),{key:"ArrowRight"});
 await waitFor(()=>expect(screen.getByRole("tab",{name:"Zoom"}).getAttribute("aria-selected")).toBe("true"));
 expect(screen.getByRole("img").getAttribute("src")).toBe("/portal-api/guide/public/images/zoom");
 fireEvent.click(screen.getByRole("button",{name:/ROI/}));
 expect(screen.getByRole("tab",{name:"Edit"}).getAttribute("aria-selected")).toBe("true");
});
it("persists only the theme preference",()=>{
 render(<ThemeToggle/>);fireEvent.click(screen.getByRole("button",{name:"다크 모드로 전환"}));
 expect(document.documentElement.dataset.theme).toBe("dark");expect(localStorage.getItem("xrt-theme:v1")).toBe("dark");expect(localStorage.length).toBe(1);
});

it("keeps two primary destinations and moves notes to the footer", async () => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json([release("0.4.3", "BETA")]))));
  render(<MemoryRouter><DownloadPage /></MemoryRouter>);
  await screen.findByRole("link", {name: /Windows 다운로드/});
  const main = within(screen.getByRole("navigation", {name: "주 메뉴"}));
  expect(main.getAllByRole("link").map(a => a.textContent)).toEqual(["다운로드", "사용 가이드"]);
  expect(main.queryByRole("link", {name: "개발 노트"})).toBeNull();
  expect(within(screen.getByRole("contentinfo")).getByRole("link", {name: "개발 노트"}).getAttribute("href")).toBe("/notes");
});
it("shows only three recent plain-text improvement notes without the deployment ledger", async () => {
  const releases = ["0.4.3", "0.4.2", "0.4.1", "0.4.0"].map(v => ({...release(v, "BETA"), manifest: {...release(v, "BETA").manifest, notes: "- 메뉴를 정리했습니다.\n- <script>실행하지 않음</script>\n- 가독성을 개선했습니다.\n- 네 번째 상세 항목"}}));
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(releases))));
  render(<MemoryRouter><NotesPage /></MemoryRouter>);
  expect(await screen.findAllByRole("article")).toHaveLength(3);
  expect(screen.queryByText("v0.4.0")).toBeNull();
  expect(screen.queryByText("네 번째 상세 항목")).toBeNull();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.queryByText(/SHA-256/)).toBeNull();
  expect(screen.getAllByText("<script>실행하지 않음</script>")).toHaveLength(3);
});
it("keeps old sentence notes readable and does not invent missing changes", () => {
  expect(releaseHighlights("시작 확인을 추가했습니다. 재시도를 개선했습니다.")).toEqual(["시작 확인을 추가했습니다.", "재시도를 개선했습니다."]);
  expect(releaseHighlights("\n ")).toEqual([]);
  expect(releaseHighlights("1. 한 가지 변경")).toEqual(["한 가지 변경"]);
});
it("exposes complete release evidence and every deployment event to the administrator view", async () => {
  const row = release("0.4.3", "BETA");
  const events = [{id:"first",revision:1,created_at:100,state:{status:"DRAFT",channel:"BETA",reason:"Registered with installer and source hashes"},actor:"builder"},{id:"second",revision:2,created_at:200,state:{status:"PUBLISHED",channel:"BETA",reason:"CI and actual installation accepted"},actor:"operator"}];
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(events))));
  render(<ReleaseHistory release={{...row, created_at:100, revision:2, event_id:"second", download_requests:0, manifest:{...row.manifest, schema:"xrt_app_release/v1", filename:"setup.exe", model_included:false, license:"GPL-3.0-only", distribution_clearance:{status:"APPROVED",reference:"Publisher consent"}}}} onClose={() => {}} />);
  expect(await screen.findByText("CI and actual installation accepted")).toBeTruthy();
  expect(screen.getByText("Registered with installer and source hashes")).toBeTruthy();
  expect(screen.getByText("a".repeat(64), {selector:"code"})).toBeTruthy();
  expect(screen.getByText("b".repeat(40), {selector:"code"})).toBeTruthy();
  expect(screen.getByText("APPROVED · Publisher consent")).toBeTruthy();
});
