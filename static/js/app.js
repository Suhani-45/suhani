const COLORS = {
  Food:'#ea580c', Travel:'#2563eb', Shopping:'#7c3aed',
  Utilities:'#059669', Other:'#64748b'
};

const CHART_OPTS = {
  responsive:true, maintainAspectRatio:false,
  plugins:{
    legend:{labels:{color:'#0f172a',font:{family:"'Space Mono',monospace",size:10},padding:16,boxWidth:10,boxHeight:10}},
    tooltip:{backgroundColor:'#fff',borderColor:'#dce8ff',borderWidth:1,
      titleColor:'#1d4ed8',bodyColor:'#0f172a',padding:12,cornerRadius:10,
      callbacks:{label:ctx=>` ₹${(ctx.parsed.toFixed?ctx.parsed:ctx.parsed.y).toFixed(2)}`}}
  }
};

function getMonth(){
  const sel=document.getElementById('month-select');
  return sel?sel.value:'';
}

async function loadCatChart(){
  const c=document.getElementById('catChart'); if(!c)return;
  const m=getMonth();
  const url='/api/cats'+(m?`?month=${m}`:'');
  const data=await fetch(url).then(r=>r.json());
  if(!data.length){
    c.parentElement.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:.82rem;font-family:Space Mono,monospace">No expenses this month</div>';
    return;
  }
  if(window._catChart) window._catChart.destroy();
  const labels=data.map(d=>d.category),vals=data.map(d=>d.total),colors=labels.map(l=>COLORS[l]||'#94a3b8');
  window._catChart=new Chart(c.getContext('2d'),{
    type:'doughnut',
    data:{labels,datasets:[{data:vals,backgroundColor:colors.map(c=>c+'18'),borderColor:colors,borderWidth:2.5,hoverOffset:10}]},
    options:{...CHART_OPTS,cutout:'70%',plugins:{...CHART_OPTS.plugins,legend:{...CHART_OPTS.plugins.legend,position:'right'}}}
  });
}

async function loadMonthChart(){
  const c=document.getElementById('monthChart'); if(!c)return;
  const data=await fetch('/api/monthly').then(r=>r.json());
  if(!data.length){
    c.parentElement.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:.82rem;font-family:Space Mono,monospace">No monthly data yet</div>';
    return;
  }
  if(window._monthChart) window._monthChart.destroy();
  window._monthChart=new Chart(c.getContext('2d'),{
    type:'bar',
    data:{labels:data.map(d=>d.month),datasets:[{label:'Monthly Spending',data:data.map(d=>d.total),
      backgroundColor:'rgba(37,99,235,.12)',borderColor:'#2563eb',borderWidth:2,borderRadius:8,borderSkipped:false}]},
    options:{...CHART_OPTS,scales:{
      x:{ticks:{color:'#64748b',font:{family:"'Space Mono',monospace",size:9}},grid:{color:'#eef4ff',lineWidth:1}},
      y:{ticks:{color:'#64748b',font:{family:"'Space Mono',monospace",size:9},callback:v=>'₹'+v},grid:{color:'#eef4ff',lineWidth:1},beginAtZero:true}
    }}
  });
}

function initMonthSelect(){
  const sel=document.getElementById('month-select');
  if(!sel)return;
  sel.addEventListener('change',()=>{
    const url=new URL(window.location.href);
    url.searchParams.set('month',sel.value);
    window.location.href=url.toString();
  });
}

function initDrop(){
  const zone=document.querySelector('.drop-zone'),input=document.getElementById('file-input');
  const preview=document.querySelector('.preview'),img=preview?.querySelector('img');
  if(!zone||!input)return;
  zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag');});
  zone.addEventListener('dragleave',()=>zone.classList.remove('drag'));
  zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('drag');const f=e.dataTransfer.files[0];if(f){input.files=e.dataTransfer.files;showImg(f);}});
  input.addEventListener('change',()=>input.files[0]&&showImg(input.files[0]));
  function showImg(f){if(!preview||!img)return;const r=new FileReader();r.onload=e=>{img.src=e.target.result;preview.style.display='block';};r.readAsDataURL(f);}
}

function initManual(){
  const btn=document.getElementById('toggle-manual'),box=document.getElementById('manual-box');
  if(!btn||!box)return;
  btn.addEventListener('click',()=>{
    box.classList.toggle('show');
    btn.textContent=box.classList.contains('show')?'✕ Close Manual Entry':'+ Add Manually';
  });
}

function initPopup(){
  const o=document.getElementById('overlay'),c=document.getElementById('close-popup');
  if(!o)return;
  if(o.dataset.show==='true')o.classList.add('show');
  c?.addEventListener('click',()=>o.classList.remove('show'));
  o.addEventListener('click',e=>{if(e.target===o)o.classList.remove('show');});
}

function initBars(){
  document.querySelectorAll('.bar-fill').forEach(b=>{
    const p=parseFloat(b.dataset.pct||0);b.style.width='0%';
    requestAnimationFrame(()=>setTimeout(()=>{
      b.style.width=Math.min(p,100)+'%';
      if(p>=100)b.classList.add('over');
      else if(p>=75)b.classList.add('warn');
    },200));
  });
}

function initAlerts(){
  document.querySelectorAll('.alert').forEach(el=>{
    setTimeout(()=>{el.style.transition='opacity .6s';el.style.opacity='0';setTimeout(()=>el.remove(),600);},6000);
  });
}

// Saving / Invest modal
function openModal(type){
  const modal=document.getElementById('options-modal');
  const title=document.getElementById('modal-title');
  const desc=document.getElementById('modal-desc');
  const list=document.getElementById('modal-list');
  if(!modal)return;

  if(type==='save'){
    title.textContent='💰 Where to Save Your Money';
    desc.textContent='You have a budget surplus this month! Here are the best ways to save your extra money:';
    list.innerHTML=`
      <div class="option-item"><div class="option-icon">🏦</div><div><div class="option-title">High-Interest Savings Account</div><div class="option-desc">Open a savings account with 6–7% interest. Best options: SBI, HDFC, ICICI, Kotak 811. Keep 3–6 months of expenses as emergency fund.</div></div></div>
      <div class="option-item"><div class="option-icon">📬</div><div><div class="option-title">Post Office / PPF</div><div class="option-desc">Public Provident Fund (PPF) gives 7.1% tax-free returns. Lock-in of 15 years but very safe. Great for long-term savings.</div></div></div>
      <div class="option-item"><div class="option-icon">🔒</div><div><div class="option-title">Fixed Deposit (FD)</div><div class="option-desc">Bank FDs give 6.5–8% returns with zero risk. Choose tenure from 7 days to 10 years based on your goal.</div></div></div>
      <div class="option-item"><div class="option-icon">📱</div><div><div class="option-title">Digital Savings (Jar, Fi, Jupiter)</div><div class="option-desc">Apps like Jar auto-save your spare change. Fi Money and Jupiter offer smart savings pots with good interest rates.</div></div></div>
    `;
  } else {
    title.textContent='📈 Where to Invest Your Money';
    desc.textContent='Smart investing can grow your wealth. Here are the best investment options for you:';
    list.innerHTML=`
      <div class="option-item"><div class="option-icon">📊</div><div><div class="option-title">Stock Market (Shares)</div><div class="option-desc">Buy shares of top Indian companies like Reliance, TCS, Infosys via Zerodha, Groww, or Upstox. Higher risk but potentially 12–15% annual returns.</div></div></div>
      <div class="option-item"><div class="option-icon">💛</div><div><div class="option-title">Digital Gold & Silver</div><div class="option-desc">Buy 24K pure gold/silver digitally via Google Pay, PhonePe, or Groww starting from just ₹1. No storage worries. Great hedge against inflation.</div></div></div>
      <div class="option-item"><div class="option-icon">📈</div><div><div class="option-title">Mutual Funds (SIP)</div><div class="option-desc">Start a SIP from ₹500/month in index funds. NIFTY 50 index funds historically give 12% average annual returns. Use Groww, Zerodha Coin, or Paytm Money.</div></div></div>
      <div class="option-item"><div class="option-icon">🏠</div><div><div class="option-title">REITs (Real Estate)</div><div class="option-desc">Invest in real estate without buying property. REITs like Embassy Office Parks, Mindspace give 7–8% dividend yield plus capital appreciation.</div></div></div>
    `;
  }
  modal.classList.add('show');
}

function closeModal(){
  const modal=document.getElementById('options-modal');
  if(modal)modal.classList.remove('show');
}

document.addEventListener('DOMContentLoaded',()=>{
  loadCatChart();
  loadMonthChart();
  initMonthSelect();
  initDrop();
  initManual();
  initPopup();
  initBars();
  initAlerts();
  document.getElementById('options-modal')?.addEventListener('click',e=>{
    if(e.target===document.getElementById('options-modal'))closeModal();
  });
});