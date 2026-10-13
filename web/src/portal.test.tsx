import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DownloadPage } from "./Public";
import { Modal } from "./ui";
import { useData } from "./api";
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const json=(value:unknown)=>({ok:true,json:async()=>value});
const release=(id:string,channel:string)=>({id,state:{channel,status:"PUBLISHED"},manifest:{version:id,platform:"windows-x64",size:200,minimum_os:"Windows 10/11",signature:"UNSIGNED",sha256:"a".repeat(64),components:["VIEWER"],notes:"Synthetic release",source_revision:"b".repeat(40)}});
describe("download and administrator safeguards",()=>{
 it("uses the posted stable release and keeps admin data off the public page",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(json([release("0.2.0","BETA"),release("0.1.0","STABLE")])));
  render(<MemoryRouter><DownloadPage/></MemoryRouter>);
  const button=await screen.findByRole("link",{name:/Windows 설치 프로그램 다운로드/});
  expect(button.getAttribute("href")).toBe("/portal-api/releases/0.1.0/download");
  expect(screen.getByText(/코드 서명이 없습니다/)).toBeTruthy();
  expect(screen.queryByText("관리자 인증키")).toBeNull();
 });
 it("does not fabricate a download when no version is published",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(json([])));
  render(<MemoryRouter><DownloadPage/></MemoryRouter>);
  expect(await screen.findByText("설치 파일을 준비 중입니다")).toBeTruthy();
  expect(screen.queryByRole("link",{name:/Windows 설치 프로그램 다운로드/})).toBeNull();
 });
 it("keeps the newest request when an obsolete response completes late",async()=>{
  let finishFirst:(v:unknown)=>void=()=>{};
  vi.stubGlobal("fetch",vi.fn((path:string)=>path.endsWith("first")?new Promise(r=>{finishFirst=r;}):Promise.resolve(json("newest"))));
  const hook=renderHook(({path})=>useData<string>(path),{initialProps:{path:"first"}});
  hook.rerender({path:"second"});
  await waitFor(()=>expect(hook.result.current.data).toBe("newest"));
  await act(async()=>{finishFirst(json("obsolete"));});
  expect(hook.result.current.data).toBe("newest");
 });
 it("traps modal keyboard focus and supports Escape",()=>{
  const close=vi.fn();
  render(<Modal labelId="title" onClose={close}><h2 id="title">Version</h2><button>First</button><button>Last</button></Modal>);
  expect(document.activeElement).toBe(screen.getByText("First"));
  fireEvent.keyDown(document,{key:"Tab",shiftKey:true});
  expect(document.activeElement).toBe(screen.getByText("Last"));
  fireEvent.keyDown(document,{key:"Tab"});
  expect(document.activeElement).toBe(screen.getByText("First"));
  fireEvent.keyDown(document,{key:"Escape"});expect(close).toHaveBeenCalledOnce();
 });
});
