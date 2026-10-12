import { test } from 'node:test';
import assert from 'node:assert/strict';
import { activeCue, validateBundle } from './sync';
import type { Cue } from '../src/types';
const cue=(start:number,end:number,id='one'):Cue=>({id,cue_index:1,start_ms:start,end_ms:end,source_text:'你好',translated_text:'Hello',confidence:.9,notes:null});
test('subtitle boundaries, gaps, seeking and positive/negative delay',()=>{
  const cues=[cue(1000,2000),cue(3000,4000,'two')];
  assert.equal(activeCue(cues,.999,0),undefined);
  assert.equal(activeCue(cues,1,0)?.id,'one');
  assert.equal(activeCue(cues,2,0),undefined);
  assert.equal(activeCue(cues,3.5,0)?.id,'two');
  assert.equal(activeCue(cues,1.5,0)?.id,'one');
  assert.equal(activeCue(cues,1,.1),undefined);
  assert.equal(activeCue(cues,1.1,.1)?.id,'one');
  assert.equal(activeCue(cues,.9,-.1)?.id,'one');
});
test('overlapping SRT returns last-starting active cue',()=>{
  const cues=[cue(1000,5000),cue(2000,3000,'two')];
  assert.equal(activeCue(cues,2.5,0)?.id,'two');
  assert.equal(activeCue(cues,3.5,0)?.id,'one');
});
test('extension rejects malformed or incomplete subtitle payloads',()=>{
  const bundle={version:1,project:{id:'p',youtube_video_id:'dQw4w9WgXcQ'},cues:[cue(1000,2000)]};
  assert.equal(validateBundle(bundle),true);
  assert.equal(validateBundle({...bundle,cues:[{...cue(0,1000),translated_text:null}]}),false);
  assert.equal(validateBundle({...bundle,cues:[cue(2000,1000)]}),false);
  assert.equal(validateBundle({...bundle,cues:[cue(2000,3000),cue(1000,2000)]}),false);
  assert.equal(validateBundle({...bundle,project:{id:'p'}}),false);
});
