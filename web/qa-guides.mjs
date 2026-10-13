import { chromium } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const origin="http://127.0.0.1:18770";
const output=resolve(process.env.XRT_QA_OUTPUT??"../artifacts/distribution122/browser-guide");await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on("pageerror",e=>errors.push(e.message));
const privateAuth=JSON.parse(await readFile(resolve("../artifacts/sync106-private/admin.json"),"utf8"));
const report={status:"RUNNING",origin,screens:0,tabs:0,themes:[],private_credentials_sent_to:"LOOPBACK_ONLY"};
try{
 await page.goto(origin+"/guide");await page.getByRole("heading",{name:"실제 데이터 화면으로 안내합니다."}).waitFor();
 const logged=await page.request.post(origin+"/portal-api/guide/login",{headers:{Origin:origin},data:{client_id:privateAuth.client_id,credential:privateAuth.credential}});if(!logged.ok())throw new Error("Guide local auth rejected");
 await page.reload();await page.getByRole("tablist").waitFor();
 const data=await(await page.request.get(origin+"/portal-api/guide")).json();
 for(const g of data.groups){for(const t of g.tabs){
   await page.goto(origin+"/guide?work="+g.id+"&tab="+t.id);await page.getByRole("tab",{name:t.title,exact:true}).waitFor();
   await page.waitForFunction(()=>{const im=document.querySelector('.annotated-screen img');return im&&im.complete&&im.naturalWidth>0;});
   if(await page.locator('.screen-arrows line').count()<1)throw new Error("Missing callout arrows");
   if(await page.locator('[role=tabpanel]').getAttribute('aria-labelledby')!==`tab-${g.id}-${t.id}`)throw new Error("Wrong selected panel");report.tabs++;
 }}
 for(const theme of ['light','dark']){await page.evaluate(t=>{localStorage.setItem('xrt-theme:v1',t);},theme);await page.reload();await page.getByRole('tablist').waitFor();if(await page.locator('html').getAttribute('data-theme')!==theme)throw new Error('Theme mismatch');for(const width of [390,1100,1440]){await page.setViewportSize({width,height:1000});await page.screenshot({path:resolve(output,theme+'-'+width+'.png'),fullPage:true});const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);if(overflow)throw new Error('Page overflow at '+width);report.screens++;}report.themes.push(theme);}
 await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'화면 크게 보기'}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');if(await page.getByRole('dialog').count())throw new Error('Preview did not close');
 const storage=await page.evaluate(()=>({local:Object.keys(localStorage),session:Object.keys(sessionStorage)}));if(storage.session.length||storage.local.some(k=>k!=='xrt-theme:v1'))throw new Error('Unexpected credential storage');
 await page.getByRole('button',{name:'로그아웃',exact:true}).click();await page.getByRole('heading',{name:'실제 데이터 화면으로 안내합니다.'}).waitFor();if((await page.request.get(origin+'/portal-api/guide/images/jpg-fit')).status()!==401)throw new Error('Image still accessible after logout');
 if(errors.length)throw new Error('Browser errors: '+errors.join('; '));report.status='PASS';
}finally{await writeFile(resolve(output,'report.json'),JSON.stringify(report,null,2));await browser.close();}
console.log(JSON.stringify(report));
