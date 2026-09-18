"""Offline closing-price view using the report's saved, contemporaneous states."""


def add_price_panel(page: str, default_color: str = "phase") -> str:
    if default_color not in {"phase", "signal"}:
        raise ValueError("Unsupported default price color mode")
    anchor = '<h2>Kiểm tra mục tiêu trên toàn rổ — 10 nến</h2>'
    if page.count(anchor) != 1:
        raise ValueError("Expected one basket summary after the compass")
    panel = '''<section id="price-panel" aria-labelledby="price-heading">
<div class="price-heading"><h2 id="price-heading">Giá thực tế và hướng la bàn</h2><div class="price-controls">
<label>Mã <select id="price-symbol" aria-label="Mã trên biểu đồ giá"></select></label>
<label>Tô màu <select id="price-color"><option value="phase" selected>4 trạng thái la bàn</option><option value="signal">Tín hiệu Long / Short / Chờ</option></select></label>
<label>Khoảng xem <select id="price-window"><option value="60">60 nến</option><option value="180" selected>180 nến</option><option value="360">360 nến</option><option value="all">Toàn kỳ</option></select></label></div></div>
<div class="price-legend" id="price-legend"></div>
<p id="price-scope"></p><p id="price-color-note"></p><div class="price-scroll"><svg id="price" viewBox="0 0 1200 390" role="img" tabindex="0" aria-label="Giá đóng cửa D1 và trạng thái tại từng ngày; dùng phím trái phải để xem từng điểm"></svg></div>
<p id="price-readout" aria-live="polite"></p>
<p class="price-help">Đường giá đóng cửa · Thang log · Màu theo chế độ đang chọn, dùng dữ liệu đến đóng nến T; không tô theo kết quả đúng/sai sau đó. Chấm xanh/đỏ chỉ xuất hiện khi có tín hiệu Long/Short thực tế. Di chuột, chạm hoặc dùng phím ← → để xem từng ngày.</p>
</section>'''
    css = '''<style>
#price-panel{margin-top:24px;padding:16px;background:#101a2b;border:1px solid #334155;border-radius:8px}
.price-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.price-heading h2{margin:0}.price-controls,.price-legend{display:flex;gap:14px;flex-wrap:wrap;align-items:center}.price-legend{margin-top:12px;font-size:12px;color:#bfd0e5}.price-legend span{display:flex;align-items:center;gap:7px}.price-legend i{width:9px;height:9px;border-radius:50%;display:inline-block}
.price-scroll{overflow-x:auto}#price{display:block;min-width:680px;touch-action:pan-y;box-sizing:border-box}#price:focus-visible{outline:2px solid #73cfff;outline-offset:-3px}#price-scope,.price-help{font-size:12px}#price-readout{min-height:22px;font-variant-numeric:tabular-nums;color:#e0e9f5;margin-bottom:0}.asset[role=button]{cursor:pointer;border-radius:4px;padding:4px}.asset[aria-pressed=true]{background:#25364c;outline:1px solid #6685aa}.asset[role=button]:focus-visible{outline:2px solid #73cfff}
@media(max-width:500px){#price-panel{padding:10px}.price-controls{gap:6px}.price-legend{gap:10px}}
</style>'''
    script = '''<script>
(() => {
  const colors={LONG:'#55dca3',SHORT:'#fa789a',WAIT:'#8794aa',MISSING:'#536174',IMPROVING:'#38bdf8',LEADING:'#55dca3',WEAKENING:'#fb923c',LAGGING:'#f87171',CENTER:'#8794aa'};
  const labels={LONG:'Long',SHORT:'Short',WAIT:'Chờ',MISSING:'Chưa đủ dữ liệu',IMPROVING:'Improving',LEADING:'Leading',WEAKENING:'Weakening',LAGGING:'Lagging',CENTER:'Trên trục trung tâm'};
  const selector=$('price-symbol'), svg=$('price'), windowSelector=$('price-window');
  $('price-color').value='__DEFAULT_PRICE_COLOR__';
  if(D.phase_only){
    $('price-color').value='phase';$('price-color').closest('label').hidden=true;
    $('price-heading').textContent='Giá thực tế và chu kỳ xu hướng';
    $('price-panel').querySelector('.price-help').textContent='Đường giá đóng cửa · Thang log · Màu là trạng thái xu hướng tại đóng nến T, không phải kết quả giá sau đó. Improving vẫn thuộc xu hướng giảm; Weakening vẫn thuộc xu hướng tăng. Di chuột, chạm hoặc dùng phím ← → để xem từng ngày.';
  }
  const symbols=[...new Set(D.groups.flatMap(g=>g[1]))];
  for(const symbol of symbols) selector.add(new Option(symbol,symbol));
  selector.value=symbols.includes(D.price_default_symbol)?D.price_default_symbol:D.assets.US500?'US500':symbols[0];
  const format=v=>Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
  const make=(tag,attrs,parent=svg)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e;};
  const text=(value,attrs,parent=svg)=>{const e=make('text',attrs,parent);e.textContent=value;return e;};
  let points=[],model='',x=()=>0,y=()=>0,hoverGroup=null,active=0,phases=new Map();
  const signal=r=>{const f=r.forecasts[model];return f&&['LONG','SHORT','WAIT'].includes(f.bias)?f.bias:'MISSING';};
  const state=r=>D.phase_only?(r.forecasts[model]?.phase||'MISSING'):$('price-color').value==='phase'?(phases.get(r.date)||'MISSING'):signal(r);
  function inspect(index){
    if(!points.length)return;
    active=Math.max(0,Math.min(points.length-1,index));
    const r=points[active],s=state(r),p=r.forecasts[model]?.p_up;
    hoverGroup.replaceChildren();
    make('line',{x1:x(active),x2:x(active),y1:26,y2:320,stroke:'#cbd5e1','stroke-dasharray':'4 4',opacity:.65},hoverGroup);
    make('circle',{cx:x(active),cy:y(Math.log(r.close)),r:5,fill:colors[s],stroke:'#e3eaf4','stroke-width':1.5},hoverGroup);
    $('price-readout').textContent=r.date+' · '+selector.value+' · Close '+format(r.close)+' · '+labels[s]+(!D.phase_only&&$('price-color').value==='phase'?' · Tín hiệu: '+labels[signal(r)]:'')+(p==null?'':' · Điểm tăng '+pct(p));
    if(D.phase_only){const f=r.forecasts[model];$('price-readout').textContent+=' · X '+f.score.toFixed(3)+' · Y '+f.momentum.toFixed(3);}
    $('price-readout').style.color=colors[s];
    svg.dataset.inspectedDate=r.date;
  }
  function wireCards(){
    for(const el of $('cards').querySelectorAll('.asset')){
      const symbol=el.firstChild?.textContent;
      if(!symbols.includes(symbol))continue;
      el.dataset.symbol=symbol;el.tabIndex=0;el.setAttribute('role','button');
      el.setAttribute('aria-label','Xem giá '+symbol);el.setAttribute('aria-pressed',String(symbol===selector.value));
      const select=()=>{selector.value=symbol;render();};
      el.onclick=select;el.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}};
    }
  }
  function render(){
    const asof=dates[Number($('range').value)],symbol=selector.value;
    model=$('model').value;
    const history=(D.assets[symbol]?.history||[]).filter(r=>r.date<=asof&&Number.isFinite(r.close)&&r.close>0);
    phases=new Map();
    history.forEach((r,i)=>{
      const forecast=r.forecasts[model];
      if(Number.isFinite(forecast?.score)&&Number.isFinite(forecast?.momentum)){
        const dx=forecast.score,dy=forecast.momentum;
        phases.set(r.date,dx===0||dy===0?'CENTER':dx>0?(dy>0?'LEADING':'WEAKENING'):(dy>0?'IMPROVING':'LAGGING'));
        return;
      }
      const prev=history[i-5],p=r.forecasts[model]?.p_up,q=prev?.forecasts[model]?.p_up;
      if(!prev||p==null||q==null||r.index-prev.index!==5||r.epochs[model]!==prev.epochs[model])return;
      const dx=p-.5,dy=p-q;
      phases.set(r.date,dx===0||dy===0?'CENTER':dx>0?(dy>0?'LEADING':'WEAKENING'):(dy>0?'IMPROVING':'LAGGING'));
    });
    points=windowSelector.value==='all'?history:history.slice(-Number(windowSelector.value));
    const phaseMode=$('price-color').value==='phase';
    $('price-legend').replaceChildren();
    for(const s of phaseMode?['IMPROVING','LEADING','WEAKENING','LAGGING','CENTER','MISSING']:['LONG','SHORT','WAIT','MISSING']){
      const item=document.createElement('span'),dot=document.createElement('i');dot.style.background=colors[s];item.append(dot,labels[s]);$('price-legend').append(item);
    }
    const waiting=points.filter(r=>signal(r)==='WAIT').length;
    $('price-color-note').textContent=phaseMode?(D.phase_description||'Màu theo vị trí trên la bàn: điểm tăng so với 50% và thay đổi qua 5 nến. Trạng thái này không phải tín hiệu Long/Short. Xám khi trên trục hoặc chưa đủ 5 nến cùng thư viện.'):
      points.length&&waiting===points.length?'Toàn bộ '+waiting+' nến đang xem là Chờ theo mô hình này, nên đường giá màu xám. Chọn “4 trạng thái la bàn” để xem diễn biến trạng thái.':
      'Màu theo tín hiệu thực tế đã lưu: '+points.filter(r=>signal(r)==='LONG').length+' Long · '+points.filter(r=>signal(r)==='SHORT').length+' Short · '+waiting+' Chờ.';
    svg.replaceChildren();delete svg.dataset.inspectedDate;
    svg.dataset.symbol=symbol;svg.dataset.model=model;svg.dataset.colorMode=$('price-color').value;svg.dataset.lastDate=points.at(-1)?.date||'';
    wireCards();
    if(!points.length){
      $('price-scope').textContent=symbol+' · '+names[model]+' · Xem đến '+(asof||'—');
      $('price-readout').textContent='';
      text('Chưa có dữ liệu giá hợp lệ cho mã/ngày này.',{x:600,y:190,fill:'#aebfd5','text-anchor':'middle','font-size':18});
      return;
    }
    const first=points[0],last=points.at(-1),stale=(Date.parse(asof)-Date.parse(last.date))/86400000>5;
    $('price-scope').textContent=symbol+' · '+names[model]+' · '+first.date+' → '+last.date+' · '+points.length+' nến D1'+(stale?' · Dữ liệu cũ':'');
    const L=88,R=1150,T=26,B=292,logs=points.map(r=>Math.log(r.close));
    const low=Math.min(...logs),high=Math.max(...logs),padding=Math.max((high-low)*.08,.002),lo=low-padding,hi=high+padding;
    x=i=>points.length===1?(L+R)/2:L+i*(R-L)/(points.length-1);
    y=v=>B-(v-lo)/(hi-lo)*(B-T);
    for(let j=0;j<5;j++){
      const v=lo+(hi-lo)*j/4;
      make('line',{x1:L,x2:R,y1:y(v),y2:y(v),stroke:'#28394f'});
      text(format(Math.exp(v)),{x:L-12,y:y(v)+4,fill:'#9aafc9','font-size':12,'text-anchor':'end'});
    }
    const step=points.length>1?(R-L)/(points.length-1):12;
    points.forEach((r,i)=>{
      const s=state(r),color=colors[s],px=x(i),py=y(logs[i]);
      if(i>0&&r.index===points[i-1].index+1){
        make('line',{class:'price-segment','data-date':r.date,'data-state':s,x1:x(i-1),y1:y(logs[i-1]),x2:px,y2:py,stroke:color,'stroke-width':2.3,'stroke-linecap':'round'});
      }
      const stripLeft=Math.max(L,px-step/2),stripRight=Math.min(R,px+step/2);
      make('rect',{class:'price-state','data-date':r.date,'data-state':s,x:stripLeft,y:308,width:Math.max(1,stripRight-stripLeft),height:7,fill:color,opacity:.8});
      const actualSignal=signal(r);
      if(actualSignal==='LONG'||actualSignal==='SHORT'){
        const marker=make('circle',{class:'price-signal','data-date':r.date,'data-state':actualSignal,cx:px,cy:py,r:3.6,fill:colors[actualSignal]});
        make('title',{},marker).textContent=r.date+' · Tín hiệu '+labels[actualSignal]+' · Close '+format(r.close);
      }
    });
    if(points.length===1)make('circle',{cx:x(0),cy:y(logs[0]),r:4,fill:colors[state(first)]});
    const ticks=[...new Set([0,Math.floor((points.length-1)/2),points.length-1])];
    for(const i of ticks)text(points[i].date,{x:x(i),y:347,fill:'#9aafc9','font-size':12,'text-anchor':i===0?'start':i===points.length-1?'end':'middle'});
    text(phaseMode?'Trạng thái la bàn tại đóng nến':'Tín hiệu tại đóng nến',{x:L,y:377,fill:'#93a8c1','font-size':12});
    const lastState=state(last),badge=make('g',{'aria-label':labels[lastState]});
    make('rect',{x:970,y:354,width:180,height:27,rx:5,fill:colors[lastState],opacity:.15},badge);
    text(last.date+' · '+labels[lastState],{x:1060,y:372,fill:colors[lastState],'font-size':12,'text-anchor':'middle'},badge);
    hoverGroup=make('g',{'pointer-events':'none'});
    inspect(points.length-1);
  }
  svg.addEventListener('pointermove',event=>{
    const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
    const position=point.matrixTransform(svg.getScreenCTM().inverse());
    inspect(Math.round((position.x-88)/(1150-88)*Math.max(0,points.length-1)));
  });
  svg.addEventListener('pointerleave',()=>inspect(points.length-1));
  svg.addEventListener('keydown',event=>{
    if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();inspect(active+(event.key==='ArrowLeft'?-1:1));}
    else if(event.key==='Home'||event.key==='End'){event.preventDefault();inspect(event.key==='Home'?0:points.length-1);}
  });
  selector.addEventListener('change',render);windowSelector.addEventListener('change',render);
  $('price-color').addEventListener('change',render);
  $('range').addEventListener('input',render);$('model').addEventListener('change',render);
  render();
})();
</script>'''
    script = script.replace('__DEFAULT_PRICE_COLOR__', default_color)
    return page.replace('</style>', '</style>' + css, 1).replace(anchor, panel + anchor).replace('</html>', script + '</html>')
