import type { Cue, SubtitleBundle } from '../src/types';
export function activeCue(cues: Cue[], currentTime: number, delay: number): Cue | undefined {
  const ms = Math.round((currentTime - delay) * 1000);
  // Last-starting active cue wins if imported SRT cues overlap.
  let lo = 0, hi = cues.length;
  while (lo < hi) { const mid = (lo + hi) >>> 1; if(cues[mid].start_ms <= ms) lo=mid+1; else hi=mid; }
  for(let i=lo-1;i>=0;i--) if(ms<cues[i].end_ms) return cues[i];
  return undefined;
}
export function validateBundle(value: unknown): value is SubtitleBundle {
  if(!value || typeof value !== 'object') return false;
  const b=value as SubtitleBundle;
  if(b.version!==1 || !b.project || typeof b.project.id!=='string' || !/^[\w-]{11}$/.test(b.project.youtube_video_id || '') || !Array.isArray(b.cues) || !b.cues.length || b.cues.length>10000) return false;
  return b.cues.every((c,i) => typeof c.id==='string' && typeof c.translated_text==='string' && c.translated_text.trim().length>0 && c.translated_text.length<=500 && Number.isInteger(c.start_ms) && Number.isInteger(c.end_ms) && c.start_ms>=0 && c.end_ms>c.start_ms && (!i || b.cues[i-1].start_ms<c.start_ms));
}
