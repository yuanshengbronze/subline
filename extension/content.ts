import type { SubtitleBundle } from '../src/types';
import { activeCue, validateBundle } from './sync';
let bundle: SubtitleBundle | undefined;
let enabled=true,delay=0,videoId='',generation=0;
const overlay=document.createElement('div');
overlay.id='subline-custom-subtitles';
overlay.setAttribute('aria-hidden','true');
Object.assign(overlay.style,{position:'absolute',bottom:'12%',left:'50%',transform:'translateX(-50%)',maxWidth:'84%',width:'max-content',textAlign:'center',color:'#fff',fontFamily:'Arial,sans-serif',fontSize:'clamp(16px,2.2vw,32px)',lineHeight:'1.35',background:'rgba(0,0,0,.78)',padding:'3px 9px',borderRadius:'3px',pointerEvents:'none',zIndex:'60',whiteSpace:'pre-wrap',overflow:'hidden',display:'none',WebkitLineClamp:'2',WebkitBoxOrient:'vertical',textShadow:'0 1px 2px #000'});
async function load(id:string) {
  const version=++generation;bundle=undefined;overlay.style.display='none';
  const data=await chrome.storage.local.get(['bundle:'+id,'enabled','delay']);
  if(version!==generation)return;
  const saved=data['bundle:'+id];
  bundle=validateBundle(saved)?saved:undefined;enabled=data.enabled!==false;delay=typeof data.delay==='number'?data.delay:0;
}
chrome.storage.onChanged.addListener(()=>{void load(videoId);});
function tick() {
  const id=location.pathname==='/watch' ? new URL(location.href).searchParams.get('v') || '' : '';
  if(id!==videoId){videoId=id;void load(id);}
  const player=document.querySelector<HTMLElement>('#movie_player');
  const video=player?.querySelector<HTMLVideoElement>('video');
  if(player && overlay.parentElement!==player)player.appendChild(overlay);
  const cue=enabled && id && bundle?.project.youtube_video_id===id && video && !player?.classList.contains('ad-showing') ? activeCue(bundle.cues,video.currentTime,delay):undefined;
  const text=cue?.translated_text || '';
  if(overlay.textContent!==text)overlay.textContent=text;
  overlay.style.display=text ? '-webkit-box':'none';
}
// Runs on all YouTube pages so SPA navigation into /watch also works.
setInterval(tick,80);tick();
