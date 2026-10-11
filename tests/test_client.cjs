const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../src/speech_gateway/web/index.html'),'utf8');
const script=html.match(/<script>([\s\S]+)<\/script>/)[1];
const dom=Object.fromEntries(['token','start','commit','stop','human','status','log'].map(id=>[id,{value:'t'.repeat(32),disabled:false,textContent:''}]));
class Context{constructor(){this.sampleRate=16000;this.state='running';this.currentTime=0;this.audioWorklet={addModule:async()=>{}};}async resume(){}async close(){this.state='closed';}createMediaStreamSource(){return {connect(){}};}createGain(){return {gain:{value:1},connect(){return this;}};}}
class Socket{constructor(){this.readyState=1;this.bufferedAmount=0;this.sent=[];}send(x){this.sent.push(x);}close(){this.readyState=3;}}
class Worklet{constructor(){this.port={};}connect(x){return x;}disconnect(){}}
const sandbox={document:{getElementById:id=>dom[id]},AudioContext:Context,AudioWorkletNode:Worklet,WebSocket:Socket,location:{protocol:'http:',host:'localhost'},navigator:{mediaDevices:{getUserMedia:async()=>({getTracks:()=>[{stop(){}}]})}},setInterval:()=>1,clearInterval:()=>{}};
vm.createContext(sandbox);vm.runInContext(script,sandbox);
(async()=>{
 await dom.start.onclick();const old=vm.runInContext('active',sandbox);old.ws.onopen();old.ws.onmessage({data:JSON.stringify({type:'ready',epoch:0})});
 dom.stop.onclick();dom.token.value='new-token';await dom.start.onclick();const fresh=vm.runInContext('active',sandbox);fresh.ws.onopen();fresh.ws.onmessage({data:JSON.stringify({type:'ready',epoch:0})});const before=fresh.ws.sent.length;
 old.ws.onclose();old.ws.onerror();old.ws.onclose();old.ws.onmessage({data:JSON.stringify({type:'handoff'})});old.capture.port.onmessage({data:new ArrayBuffer(640)});
 assert.equal(vm.runInContext('active',sandbox),fresh);assert.equal(fresh.ws.readyState,1);assert.equal(fresh.ctx.state,'running');assert.equal(fresh.ready,true);assert.equal(fresh.ws.sent.length,before);assert.equal(dom.start.disabled,true);
 dom.stop.onclick();assert.equal(fresh.ws.readyState,3);console.log('old callbacks isolated; repeated cleanup passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
