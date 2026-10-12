import { validateBundle } from './sync';
const API='http://127.0.0.1:8000';
async function request(path: string) {
  const response=await fetch(API+path,{signal:AbortSignal.timeout(10000)});
  if(!response.ok) throw new Error(`Backend returned ${response.status}.`);
  return response.json();
}
async function save(data: unknown) {
  if(!validateBundle(data)) throw new Error('Project needs a YouTube video ID and a complete set of translated cues.');
  await chrome.storage.local.set({['bundle:'+data.project.youtube_video_id]:data,enabled:true});
  return {ok:true};
}
chrome.runtime.onMessage.addListener((message,_sender,respond)=>{
  const task=async()=>{
    if(message.type==='PROJECTS') return {projects:await request('/projects?youtube_video_id='+encodeURIComponent(String(message.videoId)))};
    if(message.type==='LOAD_PROJECT') return save(await request('/projects/'+encodeURIComponent(String(message.projectId))+'/subtitles'));
    throw new Error('Unknown request.');
  };
  task().then(respond).catch(e=>respond({error:e.message}));return true;
});
chrome.runtime.onMessageExternal.addListener((message,sender,respond)=>{
  if(!sender.url || !['http://localhost:5173','http://127.0.0.1:5173'].includes(new URL(sender.url).origin) || message.type!=='SUBLINE_LOAD') {
    respond({ok:false,error:'Only the local Subline studio can send subtitles.'});return false;
  }
  save(message.data).then(respond).catch(e=>respond({ok:false,error:e.message}));return true;
});
