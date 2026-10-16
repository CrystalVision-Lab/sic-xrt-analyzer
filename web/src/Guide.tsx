import workflowGuide from "./workflow-guide.json";
import { useEffect, useId, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, Check, ChevronRight, Expand } from "lucide-react";
import { useData } from "./api";
import { Empty, ErrorBox, Loading, Modal } from "./ui";

type Callout = { title: string; text: string; target: [number,number]; label: [number,number] };
export type GuideTab = { id: string; title: string; summary: string; image_id?: string; steps: string[]; notes?: string; callouts: Callout[] };
export type GuideGroup = { id: string; title: string; subtitle: string; tabs: GuideTab[] };
type GuideData = { schema: string; groups: GuideGroup[] };

export function AnnotatedScreen({ tab, large=false }: { tab:GuideTab; large?:boolean }) {
 const marker=useId().replaceAll(":", ""); const [failed,setFailed]=useState(false);
 useEffect(()=>setFailed(false),[tab.image_id]);
 if(!tab.image_id) return <Empty title="화면 없이 진행하는 단계">아래 순서를 따라 진행하세요.</Empty>;
 return <div className={`annotated-screen ${large?"expanded-screen":""}`}>
  {failed ? <div role="alert" className="screenshot-error">화면을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</div> : <><img src={`/portal-api/guide/public/images/${tab.image_id}`} alt={`${tab.title} — 실제 XRT 원본으로 촬영한 프로그램 화면`} onError={()=>setFailed(true)}/><svg viewBox="0 0 1000 625" aria-hidden="true" className="screen-arrows"><defs><marker id={marker} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#ffc160"/></marker></defs>{tab.callouts.map((c,i)=><g key={c.title}><line x1={c.label[0]*10} y1={c.label[1]*6.25} x2={c.target[0]*10} y2={c.target[1]*6.25} stroke="#ffc160" strokeWidth="2.5" markerEnd={`url(#${marker})`}/><circle cx={c.label[0]*10} cy={c.label[1]*6.25} r="16" fill="#18332e" stroke="#ffc160" strokeWidth="2"/><text x={c.label[0]*10} y={c.label[1]*6.25+5} textAnchor="middle" fill="white" fontSize="16" fontWeight="700">{i+1}</text></g>)}</svg></>}
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
export function GuideExplorer() {
 const {data,error,loading}=useData<GuideData>("guide/public");
 return <section className="guide-section site-width" id="research-guide"><div className="guide-heading"><div><p className="eyebrow">WORKSPACE GUIDE</p><h1>사용 가이드</h1></div></div>{loading?<Loading/>:error?<ErrorBox error={error}/>:data?<GuideWorkspace data={{...data, groups:[...workflowGuide.groups, ...data.groups]}}/>:null}</section>;
}
