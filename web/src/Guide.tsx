import { useEffect, useId, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowRight, BookOpen, Check, ChevronRight, Expand, LockKeyhole, LogOut } from "lucide-react";
import { ApiError, request, useData, type Session } from "./api";
import { Empty, ErrorBox, Loading, Modal } from "./ui";

type Callout = { title: string; text: string; target: [number,number]; label: [number,number] };
export type GuideTab = { id: string; title: string; summary: string; image_id?: string; steps: string[]; notes?: string; callouts: Callout[] };
export type GuideGroup = { id: string; title: string; subtitle: string; tabs: GuideTab[] };
type GuideData = { schema: string; groups: GuideGroup[] };

function ResearcherLogin({ onLogin }: { onLogin: (s:Session) => void }) {
 const [id,setId]=useState(""); const [key,setKey]=useState(""); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
 async function submit(e:FormEvent) { e.preventDefault();setBusy(true);setError("");try { const s=await request<Session>("guide/login",{method:"POST",body:JSON.stringify({client_id:id.trim(),credential:key})});setKey("");onLogin(s); } catch(e) {setError(e instanceof ApiError && e.status===429 ? "잠시 후 다시 로그인해 주세요." : "발급받은 client ID와 인증키를 확인해 주세요.");}finally{setBusy(false);} }
 return <div className="guide-login"><div><LockKeyhole size={28}/><p className="eyebrow">RESEARCHER ACCESS</p><h3>실제 데이터 화면으로 안내합니다.</h3><p>한국세라믹기술원 연구원에게 발급한 중앙 서버 계정으로 로그인하세요. 권한이 있는 프로젝트의 사용 가이드가 열립니다.</p><ul><li>JPG · 단일 페이지 TIFF의 2D 분석</li><li>여러 페이지 TIFF의 스택 · 3D 탐색</li><li>ROI, 검수, 저장, 정합, Wafer Map, 서버 연결</li></ul></div><form onSubmit={submit}><label htmlFor="researcher-id">연구원 client ID</label><input id="researcher-id" autoComplete="username" value={id} onChange={e=>setId(e.target.value)} maxLength={128} required/><label htmlFor="researcher-key">인증키</label><input id="researcher-key" type="password" autoComplete="current-password" value={key} onChange={e=>setKey(e.target.value)} maxLength={200} required/>{error&&<p role="alert" className="login-error">{error}</p>}<button type="submit" className="download-button" disabled={busy}>{busy?"연결 확인 중…":"연구원 가이드 열기"}<ArrowRight size={18}/></button><small>인증키는 브라우저 저장소에 보관하지 않습니다.</small></form></div>;
}
export function AnnotatedScreen({ tab, large=false }: { tab:GuideTab; large?:boolean }) {
 const marker=useId().replaceAll(":", ""); const [failed,setFailed]=useState(false);
 useEffect(()=>setFailed(false),[tab.image_id]);
 if(!tab.image_id) return <Empty title="화면 없이 진행하는 단계">아래 순서를 따라 진행하세요.</Empty>;
 return <div className={`annotated-screen ${large?"expanded-screen":""}`}>
  {failed ? <div role="alert" className="screenshot-error">화면을 불러오지 못했습니다. 로그인과 프로젝트 권한을 확인해 주세요.</div> : <><img src={`/portal-api/guide/images/${tab.image_id}`} alt={`${tab.title} — 실제 XRT 원본으로 촬영한 프로그램 화면`} onError={()=>setFailed(true)}/><svg viewBox="0 0 1000 625" aria-hidden="true" className="screen-arrows"><defs><marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#ffc160"/></marker></defs>{tab.callouts.map((c,i)=><g key={c.title}><line x1={c.label[0]*10} y1={c.label[1]*6.25} x2={c.target[0]*10} y2={c.target[1]*6.25} stroke="#ffc160" strokeWidth="2.5" markerEnd={`url(#${marker})`}/><circle cx={c.label[0]*10} cy={c.label[1]*6.25} r="16" fill="#18332e" stroke="#ffc160" strokeWidth="2"/><text x={c.label[0]*10} y={c.label[1]*6.25+5} textAnchor="middle" fill="white" fontSize="16" fontWeight="700">{i+1}</text></g>)}</svg></>}
 </div>;
}
export function GuideWorkspace({ data }: { data:GuideData }) {
 const [params,setParams]=useSearchParams();const [expanded,setExpanded]=useState(false);
 const group=data.groups.find(g=>g.id===params.get("work"))??data.groups[0];
 const tab=group?.tabs.find(t=>t.id===params.get("tab"))??group?.tabs[0];
 function choose(g:GuideGroup,t:GuideTab=g.tabs[0]) {setExpanded(false);setParams({work:g.id,tab:t.id},{replace:true,preventScrollReset:true});}
 if(!group||!tab)return <Empty title="사용 가이드를 준비 중입니다"/>;
 return <div className="guide-workspace"><aside className="guide-master"><p className="eyebrow">작업 선택</p><nav aria-label="사용 가이드 작업"><ol>{data.groups.map((g,i)=><li key={g.id}><button className={g.id===group.id?"selected":""} aria-current={g.id===group.id?"step":undefined} onClick={()=>choose(g)}><span className="master-index">{String(i+1).padStart(2,"0")}</span><span><strong>{g.title}</strong><small>{g.tabs.length}개 화면</small></span><ChevronRight size={15}/></button></li>)}</ol></nav></aside><section className="guide-detail" aria-labelledby="work-title"><div className="guide-detail-heading"><div><p className="eyebrow">WORKSPACE GUIDE</p><h3 id="work-title">{group.title}</h3><p>{group.subtitle}</p></div><BookOpen size={24}/></div><div role="tablist" aria-label={`${group.title} 화면`} className="guide-tabs">{group.tabs.map((t,i)=><button role="tab" id={`tab-${group.id}-${t.id}`} aria-selected={t.id===tab.id} aria-controls={`panel-${group.id}`} tabIndex={t.id===tab.id?0:-1} key={t.id} onClick={()=>choose(group,t)} onKeyDown={e=>{const delta=e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0;const next=e.key==="Home"?0:e.key==="End"?group.tabs.length-1:delta?(i+delta+group.tabs.length)%group.tabs.length:-1;if(next>=0){e.preventDefault();choose(group,group.tabs[next]);document.getElementById(`tab-${group.id}-${group.tabs[next].id}`)?.focus();}}}>{t.title}</button>)}</div><div role="tabpanel" tabIndex={0} id={`panel-${group.id}`} aria-labelledby={`tab-${group.id}-${tab.id}`}><div className="guide-tab-heading"><p>{tab.summary}</p>{tab.image_id&&<button className="outline-button" onClick={()=>setExpanded(true)}><Expand size={15}/> 화면 크게 보기</button>}</div><AnnotatedScreen tab={tab}/><p className="screen-caption">실제 원본 데이터로 촬영한 화면 · 화면의 번호와 아래 설명을 함께 확인하세요.</p><div className="guide-instructions"><ol className="callout-list">{tab.callouts.map((c,i)=><li key={c.title}><span>{i+1}</span><div><h4>{c.title}</h4><p>{c.text}</p></div></li>)}</ol><div className="guide-steps"><h4>이렇게 진행하세요</h4><ol>{tab.steps.map(s=><li key={s}><Check size={14}/>{s}</li>)}</ol>{tab.notes&&<p className="guide-note">{tab.notes}</p>}</div></div></div></section>{expanded&&<Modal labelId="expanded-title" onClose={()=>setExpanded(false)}><h2 id="expanded-title">{group.title} · {tab.title}</h2><AnnotatedScreen tab={tab} large/><button className="outline-button" onClick={()=>setExpanded(false)}>닫기</button></Modal>}</div>;
}
function AuthorizedGuide() {
 const {data,error,loading}=useData<GuideData>("guide");
 if(loading)return <Loading/>;
 if(error instanceof ApiError && error.status===403)return <Empty title="프로젝트 접근 권한이 필요합니다">관리자에게 연구원 계정의 가이드 프로젝트 권한을 요청해 주세요. 다른 연구 데이터는 표시하지 않습니다.</Empty>;
 if(error)return <ErrorBox error={error}/>;
 return data?<GuideWorkspace data={data}/>:null;
}
export function GuideExplorer() {
 const [session,setSession]=useState<Session>();const [checking,setChecking]=useState(true);const [error,setError]=useState("");
 useEffect(()=>{const a=new AbortController();request<Session>("session",{signal:a.signal}).then(s=>{if(!a.signal.aborted)setSession(s);}).catch(()=>{}).finally(()=>{if(!a.signal.aborted)setChecking(false);});return()=>a.abort();},[]);
 return <section className="guide-section site-width" id="research-guide"><div className="guide-heading"><div><p className="eyebrow">KICET RESEARCH GUIDE</p><h2>지금 하실 작업을 선택하세요.</h2><p>왼쪽에서 작업을 고르고, 위쪽 탭에서 각 화면의 조작 방법을 확인하세요.</p></div>{session&&<button className="outline-button" onClick={async()=>{try{await request("logout",{method:"POST",headers:{"X-Xrt-Csrf":session.csrf}});setSession(undefined);}catch{setError("로그아웃하지 못했습니다. 다시 시도해 주세요.");}}}><LogOut size={15}/> 로그아웃</button>}</div>{error&&<p role="alert">{error}</p>}{checking?<Loading/>:session?<AuthorizedGuide/>:<ResearcherLogin onLogin={setSession}/>}</section>;
}
