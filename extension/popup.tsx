import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import type { Project, SubtitleBundle } from '../src/types';
function Popup(){
  const [enabled,setEnabled]=useState(true),[delay,setDelay]=useState(0),[projects,setProjects]=useState<Project[]>([]),[selected,setSelected]=useState(''),[error,setError]=useState(''),[status,setStatus]=useState('Finding this video…'),[busy,setBusy]=useState(false);
  useEffect(()=>{void (async()=>{
    try {
      const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
      const url=tab?.url?new URL(tab.url):null;
      const id=url && ['www.youtube.com','youtube.com'].includes(url.hostname) && url.pathname==='/watch'?url.searchParams.get('v'):null;
      const data=await chrome.storage.local.get(['enabled','delay','bundle:'+id]);
      setEnabled(data.enabled!==false);setDelay(typeof data.delay==='number'?data.delay:0);
      const bundle=data['bundle:'+id] as SubtitleBundle|undefined;
      setSelected(bundle?.project.id || '');
      if(!id){setStatus('Open a YouTube video to choose subtitles.');return;}
      setStatus(bundle?'Cached subtitles ready: '+bundle.project.title:'No subtitles loaded for this video.');
      const result=await chrome.runtime.sendMessage({type:'PROJECTS',videoId:id});
      if(result.error)throw new Error(result.error);
      setProjects(result.projects);if(!bundle)setSelected(result.projects[0]?.id || '');
    }catch{setError('Backend unavailable. Start FastAPI to load projects. Cached subtitles still work.');}
  })();},[]);
  async function adjust(value:number){const next=Math.round(value*10)/10;setDelay(next);await chrome.storage.local.set({delay:next});}
  return <main><header><span className="logo">字</span><strong>subline.</strong><small>LOCAL SUBTITLES</small></header><label className="toggle">Show English subtitles<input type="checkbox" checked={enabled} onChange={e=>{setEnabled(e.target.checked);void chrome.storage.local.set({enabled:e.target.checked});}}/></label><section><label htmlFor="project">PROJECT FOR THIS VIDEO</label><select id="project" value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Select a project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select><button className="primary" disabled={!selected || busy} onClick={async()=>{setBusy(true);setError('');try{const result=await chrome.runtime.sendMessage({type:'LOAD_PROJECT',projectId:selected});if(result.error)throw new Error(result.error);setStatus('Subtitles loaded and saved offline.');setEnabled(true);}catch(e){setError(String(e));}finally{setBusy(false);}}}>{busy?'Loading…':'Load subtitles'}</button><p>{status}</p></section><section><label>SUBTITLE DELAY</label><div className="delay"><button aria-label="Show subtitles 0.1 seconds earlier" onClick={()=>void adjust(delay-.1)}>−</button><strong>{delay>0?'+':''}{delay.toFixed(1)} s</strong><button aria-label="Show subtitles 0.1 seconds later" onClick={()=>void adjust(delay+.1)}>+</button></div><p>Positive delay shows subtitles later. <button className="link" onClick={()=>void adjust(0)}>Reset</button></p></section>{error && <p role="alert" className="error">{error}</p>}<footer>Your captions, on your machine.</footer></main>;
}
createRoot(document.getElementById('root')!).render(<Popup/>);
