/* Dependency-free kinetic silk: simplex fBm surface, cubic Bézier weave.
   Add data-transparent to the canvas to draw over the page background instead of a dark fill.

   Speed: the ribbon is drawn in a background worker when the browser can (OffscreenCanvas), so the page
   itself never waits for it; at 30 frames a second, at 1× resolution (it is soft background art), and only
   while the hero is on screen. Without worker support it runs the same way on the page. */
(function(root){
'use strict';
class SimplexNoise {
  constructor(seed=8317){
    const p=Array.from({length:256},(_,i)=>i);let s=seed>>>0;
    for(let i=255;i>0;i--){s=(Math.imul(s,1664525)+1013904223)>>>0;const j=s%(i+1);[p[i],p[j]]=[p[j],p[i]];}
    this.p=Uint16Array.from({length:512},(_,i)=>p[i&255]);
    this.gx=Float64Array.from([1,-1,1,-1,1,-1,0,0]);this.gy=Float64Array.from([1,1,-1,-1,0,0,1,-1]);
  }
  noise(x,y){   // 2D simplex noise, written out without temporary arrays (it runs ~100k times a frame)
    const F=.36602540378443865,G=.21132486540518713,P=this.p,gx=this.gx,gy=this.gy,s=(x+y)*F;
    const i=Math.floor(x+s),j=Math.floor(y+s),t=(i+j)*G;
    const x0=x-(i-t),y0=y-(j-t),i1=x0>y0?1:0,j1=1-i1;
    const x1=x0-i1+G,y1=y0-j1+G,x2=x0-1+2*G,y2=y0-1+2*G,ii=i&255,jj=j&255;
    let n=0,q=.5-x0*x0-y0*y0;
    if(q>0){const g=P[ii+P[jj]]&7;q*=q;n+=q*q*(gx[g]*x0+gy[g]*y0);}
    q=.5-x1*x1-y1*y1;
    if(q>0){const g=P[ii+i1+P[jj+j1]]&7;q*=q;n+=q*q*(gx[g]*x1+gy[g]*y1);}
    q=.5-x2*x2-y2*y2;
    if(q>0){const g=P[ii+1+P[jj+1]]&7;q*=q;n+=q*q*(gx[g]*x2+gy[g]*y2);}
    return 70*n;
  }
  fbm(x,y){return .58*this.noise(x,y)+.28*this.noise(x*2.03+9,y*2.03)+.14*this.noise(x*4.11,y*4.11+17);}
}
// Catmull–Rom interpolation expressed as cubic Bézier segments.
function trace(ctx,points,move=true){
  if(move)ctx.moveTo(points[0].x,points[0].y);else ctx.lineTo(points[0].x,points[0].y);
  for(let i=0;i<points.length-1;i++){
    const a=points[Math.max(0,i-1)],b=points[i],c=points[i+1],d=points[Math.min(points.length-1,i+2)];
    ctx.bezierCurveTo(b.x+(c.x-a.x)/6,b.y+(c.y-a.y)/6,c.x-(d.x-b.x)/6,c.y-(d.y-b.y)/6,c.x,c.y);
  }
}
class SilkRenderer {
  constructor(canvas,transparent){this.canvas=canvas;this.transparent=!!transparent;this.ctx=canvas.getContext('2d',{alpha:this.transparent});this.noise=new SimplexNoise();this.width=1000;this.height=420;this.dpr=1;}
  resize(w,h,dpr=1){this.width=w;this.height=h;this.dpr=Math.min(dpr,1);this.canvas.width=Math.round(w*this.dpr);this.canvas.height=Math.round(h*this.dpr);}
  point(u,v,layer,time,pointer){
    const n=this.noise,w=this.width,h=this.height;
    const phase=u*Math.PI*2.1+time*.32+layer*.24;
    const flow=n.fbm(u*2.4+layer*.16,time*.13);
    const twist=Math.sin(u*8.1-time*.38+layer*.65);
    const taper=Math.pow(Math.sin(Math.PI*u),.58);
    let x=w*(.075+.85*u)+v*w*.052*Math.cos(phase+1.2)*taper;
    let y=h*(.5+.19*Math.sin(phase)+.065*flow)+(layer-1)*h*.052*taper;
    // Rotating fabric cross-section: wide illuminated faces, narrow turned edges.
    const spread=h*(.18+.10*Math.sin(u*3.8+.6))*(.22+.78*twist);
    y+=v*spread*taper;
    y+=h*.025*n.fbm(u*6.3+v*.55,time*.27+layer*.35)*taper;
    y+=h*.008*Math.sin(u*33-time*1.1+v*3.8)*taper;
    const dx=x/w-pointer.x,dy=y/h-pointer.y;
    const influence=pointer.strength?Math.exp(-(dx*dx*13+dy*dy*5))*pointer.strength:0;
    y+=influence*h*.105*Math.sin(u*9+v*1.8-time*.4);
    x+=influence*w*.026*Math.sin(v*2+time*.3);
    return {x,y};
  }
  render(time,pointer={x:.5,y:.5,strength:0},quality=1){
    if(!this.ctx)return;
    const c=this.ctx,w=this.width,h=this.height;c.setTransform(this.dpr,0,0,this.dpr,0,0);c.globalAlpha=1;c.globalCompositeOperation='source-over';if(this.transparent)c.clearRect(0,0,w,h);else{c.fillStyle='#080a12';c.fillRect(0,0,w,h);}
    const samples=quality<.8?64:96,threads=quality<.8?30:48;
    const palette=['#071654','#173ecd','#3939bc','#8c249f','#d140ac','#eeeaf6','#a4aecb','#31478f','#102579'];
    for(let layer=2;layer>=0;layer--){
      const lines=[];
      for(let j=0;j<=threads;j++){const v=j/threads*2-1,points=[];for(let i=0;i<=samples;i++)points.push(this.point(i/samples,v,layer,time,pointer));lines.push(points);}
      const grad=c.createLinearGradient(w*(.05+.06*Math.sin(time*.15)),h*.15,w*(.94+.04*Math.sin(time*.12)),h*.7);
      palette.forEach((color,k)=>grad.addColorStop(k/(palette.length-1),color));
      for(let j=0;j<threads;j++){
        const v=j/threads,face=.48+.52*Math.pow(Math.abs(Math.cos(v*Math.PI*2+time*.18+layer*.8)),8);
        c.beginPath();trace(c,lines[j]);trace(c,[...lines[j+1]].reverse(),false);c.closePath();c.fillStyle=grad;c.globalAlpha=(layer===0?.98:.73)*face;c.fill();
      }
      // Tightly spaced warp threads create moving silver specular ridges.
      c.globalCompositeOperation='screen';c.lineWidth=.55;
      const sheen=c.createLinearGradient(0,0,w,h*.55);sheen.addColorStop(0,'#2543d5');sheen.addColorStop(.32,'#8c69f1');sheen.addColorStop(.57,'#ffeaff');sheen.addColorStop(.78,'#e4e8f3');sheen.addColorStop(1,'#2543d5');
      for(let j=0;j<=threads;j++){
        const v=j/threads,spec=Math.pow(Math.max(0,Math.cos(v*12+time*.24+layer*.8)),18);
        c.globalAlpha=(.035+spec*.30)*(layer===0?1:.6);
        c.strokeStyle=sheen;
        c.beginPath();trace(c,lines[j]);c.stroke();
      }
      c.globalAlpha=.55;c.lineWidth=.85;c.strokeStyle='#b4bde9';c.beginPath();trace(c,lines[0]);c.stroke();
      c.globalCompositeOperation='source-over';
    }
    c.globalAlpha=1;
  }
}

/* The animation loop, shared by the worker and the on-page fallback. post(msg) drives it:
   {size:[w,h,dpr]}, {pointer:{x,y,strength}}, {run:true|false}. */
function makeLoop(canvas,transparent){
  const renderer=new SilkRenderer(canvas,transparent);
  if(!renderer.ctx)return null;
  const FRAME=1000/30,pointer={x:.5,y:.5,strength:0},target={x:.5,y:.5,strength:0};
  let running=false,timer=0,last=0,time=2.6,quality=1,cost=0;
  const now=()=>performance.now();
  function tick(){
    timer=0;const t=now(),dt=last?Math.min((t-last)/1000,.06):.033;last=t;time+=dt;
    const ease=1-Math.exp(-dt*4.5);for(const k of ['x','y','strength'])pointer[k]+=(target[k]-pointer[k])*ease;
    const start=now();renderer.render(time,pointer,quality);cost=cost*.9+(now()-start)*.1;if(cost>24)quality=.7;
    if(running)timer=setTimeout(tick,Math.max(4,FRAME-(now()-t)));
  }
  return function post(m){
    if(m.size){renderer.resize(m.size[0],m.size[1],m.size[2]);renderer.render(time,pointer,quality);}
    if(m.pointer)Object.assign(target,m.pointer);
    if('run' in m){running=m.run;if(running&&!timer){last=0;tick();}else if(!running&&timer){clearTimeout(timer);timer=0;}}
  };
}
const WORKER_SRC=`'use strict';const SimplexNoise=${SimplexNoise.toString()};const trace=${trace.toString()};const SilkRenderer=${SilkRenderer.toString()};const makeLoop=${makeLoop.toString()};
let post=null;onmessage=e=>{const m=e.data;if(m.canvas){post=makeLoop(m.canvas,m.transparent);if(!post)postMessage({failed:true});}if(post)post(m);};`;

function mount(){
  const canvas=document.getElementById('silk-canvas');if(!canvas)return;
  const container=canvas.closest('.morphing-canvas-container'),toggle=document.getElementById('silk-toggle');
  const transparent=canvas.dataset.transparent!==undefined;
  let post=null;
  if(canvas.transferControlToOffscreen&&typeof Worker!=='undefined'){
    try{
      const url=URL.createObjectURL(new Blob([WORKER_SRC],{type:'text/javascript'}));
      const worker=new Worker(url),off=canvas.transferControlToOffscreen();
      worker.postMessage({canvas:off,transparent},[off]);
      worker.onmessage=e=>{if(e.data.failed){container.classList.add('silk-unavailable');toggle.hidden=true;}};
      post=m=>worker.postMessage(m);
    }catch{post=null;}
  }
  if(!post)post=makeLoop(canvas,transparent);
  if(!post){container.classList.add('silk-unavailable');toggle.hidden=true;return;}
  const media=matchMedia('(prefers-reduced-motion: reduce)');
  let paused=media.matches,visible=true,pressed=false;
  const sync=()=>{toggle.textContent=paused?'Play motion':'Pause motion';toggle.setAttribute('aria-pressed',String(!paused));};
  const update=()=>post({run:!paused&&visible&&!document.hidden});
  const resize=()=>{const r=container.getBoundingClientRect();post({size:[Math.max(1,r.width),Math.max(1,r.height),devicePixelRatio||1]});};
  new ResizeObserver(resize).observe(container);
  // the silk is fixed behind the page, so it animates while the hero is in view and holds still below it
  const watch=document.querySelector('.hero')||container;
  new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;update();},{threshold:.02}).observe(watch);
  const aim=(e,strength)=>{const r=canvas.getBoundingClientRect();post({pointer:{x:(e.clientX-r.left)/r.width,y:(e.clientY-r.top)/r.height,strength}});};
  canvas.addEventListener('pointermove',e=>aim(e,pressed?1.7:.8));
  canvas.addEventListener('pointerdown',e=>{pressed=true;canvas.setPointerCapture(e.pointerId);aim(e,1.7);});
  const release=()=>{pressed=false;post({pointer:{strength:.4}});};canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('pointerleave',()=>{if(!pressed)post({pointer:{strength:0}});});
  toggle.addEventListener('click',()=>{paused=!paused;sync();update();});
  media.addEventListener('change',e=>{paused=e.matches;sync();update();});
  document.addEventListener('visibilitychange',update);
  window.addEventListener('pagehide',()=>post({run:false}));window.addEventListener('pageshow',update);
  resize();sync();update();
}
root.ChameleonSilk={SimplexNoise,SilkRenderer};
if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();}
})(typeof globalThis!=='undefined'?globalThis:this);
