const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// Exercise the actual player with deterministic render/output clocks and
// delayed PCM delivery. No browser, model downloads, or wall-clock sleeps.
function player(latency = 0.2) {
  const timers = [];
  const sources = [];
  const sentences = [];
  let shown = null;
  let position = null;
  let context;
  const element = () => ({textContent:'', classList:{add(){}}, appendChild(){},
    addEventListener(){}, remove(){}, style:{}});
  const document = {addEventListener(){}, removeEventListener(){},
    createElement:element, body:{appendChild(){}}, querySelectorAll:()=>[]};
  const karaoke = {
    canLocate:()=>true,
    startSentence(start, text) {
      const s = {start, end:start, text}; sentences.push(s); return s;
    },
    extendSentence(s, end) { s.end = end; },
    update(p) { position = p; shown = sentences.find(s => p >= s.start && p < s.end)?.text; },
    prevStart:()=>0, nextStart:()=>null, clear(){},
  };
  class AudioContext {
    constructor() { context = this; this.currentTime=0; this.state='running'; }
    getOutputTimestamp() {
      return {contextTime:Math.max(0,this.currentTime-latency),
        performanceTime:10000+this.currentTime*1000};
    }
    createBuffer(_, n, sr) { return {duration:n/sr,getChannelData:()=>new Float32Array(n)}; }
    createBufferSource() {
      const src={connect(){},start(when,offset){this.when=when;this.offset=offset;},
        stop(){this.stopped=true;}};
      sources.push(src); return src;
    }
    resume(){} close(){}
  }
  let messageHandler;
  const port = {onMessage:{addListener(fn){messageHandler=fn;}},
    onDisconnect:{addListener(){}},postMessage(){},disconnect(){}};
  const sandbox = vm.createContext({chrome:{runtime:{onConnect:{addListener(){}},
    onMessage:{addListener(){}}}}, document, AudioContext, window:{addEventListener(){},removeEventListener(){}},
    setInterval(fn, ms){timers.push({fn,ms});return timers.length;},clearInterval(){},
    performance:{now:()=>10000+(context?.currentTime||0)*1000},
    atob:s=>Buffer.from(s,'base64').toString('binary'),console});
  const source=fs.readFileSync(path.join(__dirname,'../src/content.js'),'utf8');
  vm.runInContext(source, sandbox);
  Object.assign(sandbox,{testKaraoke:karaoke,testElement:element,testPort:port});
  vm.runInContext(`createKaraoke=()=>testKaraoke;
    createPlayerShell=()=>({host:testElement(),audioContainer:testElement()});
    makePlayerButton=()=>testElement();makeCloseButton=()=>testElement();
    createProgressBar=()=>({track:testElement(),isDragging:()=>false,setProgress(){}});
    adjustAudioPositions=()=>{};createStreamingPlayer(testPort,{roots:[]});`,sandbox);
  return {sources, context, send:message=>messageHandler(message),
    chunk(seconds){messageHandler({type:'chunk',sr:1000,
      pcm_b64:Buffer.alloc(Math.round(seconds*1000)*2).toString('base64')});},
    pump(){timers.find(t=>t.ms===150).fn();},
    ui(){timers.find(t=>t.ms===200).fn();return {position,shown};}};
}

test('late Pocket chunks remain sequential and highlighting follows audible output',()=>{
  const p=player();
  p.send({type:'sentence_start',text:'Nobody in math is ever going to forget the year 2026.'});
  p.chunk(0.1);
  // Main thread/network delivers the next chunk after the first ran out.
  p.context.currentTime=0.25;
  p.chunk(0.1);
  p.send({type:'sentence_end'});
  p.send({type:'sentence_start',text:'Unless this is really the end of the subject.'});
  p.chunk(0.1);
  assert.equal(p.sources[1].when,0.25);
  assert(Math.abs(p.sources[2].when-0.35)<1e-9, 'overdue audio must not overlap');
  p.context.currentTime=0.52; // output device is playing context time 0.32
  assert.match(p.ui().shown,/2026/);
  p.context.currentTime=0.56; // output has now reached the next sentence
  assert.match(p.ui().shown,/Unless/);
});

test('buffering does not stop or trim a chunk before its last sample',()=>{
  const p=player(0);
  p.chunk(0.1);
  p.context.currentTime=0.09;
  p.pump();
  assert(!p.sources[0].stopped, 'must not trim the last 20ms on underrun');
});

test('the final sentence stays highlighted until output, not rendering, finishes',()=>{
  const p=player();
  p.send({type:'sentence_start',text:'The year 2026.'});
  p.chunk(1);
  p.send({type:'sentence_end'});
  p.send({type:'end'});
  p.context.currentTime=1.02;
  p.pump();
  const state=p.ui();
  assert.match(state.shown,/2026/);
  assert(Math.abs(state.position-0.82)<1e-9);
});
