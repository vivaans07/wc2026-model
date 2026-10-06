#!/usr/bin/env python3
"""Generate the CLV audit tearsheet HTML from clv_full_audit.csv."""
import csv, json, os, numpy as np
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "outputs")
os.makedirs(OUT, exist_ok=True)
rows = list(csv.DictReader(open("outputs/clv_full_audit.csv")))
for r in rows:
    for k in ("clv_pct","model_prob","open_prob","close_prob"): r[k]=float(r[k])
rows.sort(key=lambda r:r["date"])
clvs=[r["clv_pct"] for r in rows]
cum=[]; s=0
for r in rows: s+=r["clv_pct"]; cum.append(round(s,1))
best=max(rows,key=lambda r:r["clv_pct"]); worst=min(rows,key=lambda r:r["clv_pct"])
stats=dict(n=len(rows), mean=round(np.mean(clvs),1), median=round(np.median(clvs),2),
           std=round(np.std(clvs),1), beat=sum(c>0 for c in clvs),
           beatpct=round(sum(c>0 for c in clvs)/len(clvs)*100), best=best["clv_pct"],
           worst=worst["clv_pct"], bestg=best["match"], worstg=worst["match"],
           d0=rows[0]["date"], d1=rows[-1]["date"], cumtotal=round(s,0))
bins=[("< −10%",lambda c:c<-10),("−10–0%",lambda c:-10<=c<0),("0–10%",lambda c:0<=c<10),
      ("10–25%",lambda c:10<=c<25),("25–50%",lambda c:25<=c<50),("50%+",lambda c:c>=50)]
hist=[{"label":lbl,"count":sum(1 for c in clvs if f(c)),"neg":lbl.startswith("<") or lbl.startswith("−1")} for lbl,f in bins]
games=[{"date":r["date"][5:],"match":r["match"],"pick":r["pick"],
        "open":round(r["open_prob"]*100),"close":round(r["close_prob"]*100),
        "clv":round(r["clv_pct"],1)} for r in rows]
data=dict(stats=stats,cum=cum,hist=hist,games=games)
J=json.dumps(data)

html = """<style>
:root{
  --bg:#0d1320; --panel:#141c2c; --panel2:#1a2333; --line:#26304459;
  --ink:#e9edf6; --muted:#8b96ab; --faint:#5f6a80;
  --gold:#d8b44b; --gold-dim:#b8963a;
  --pos:#54c98a; --neg:#e8636b; --pos-dim:#2f6b4c; --neg-dim:#6b333a;
  --grid:#20293c;
}
@media (prefers-color-scheme:light){:root{
  --bg:#eef1f6; --panel:#ffffff; --panel2:#f6f8fb; --line:#d4dae6;
  --ink:#131a29; --muted:#5c6577; --faint:#8a93a5;
  --gold:#9a7a1e; --gold-dim:#b8963a; --pos:#1f9d5c; --neg:#cf3b45;
  --grid:#e2e7ef;
}}
:root[data-theme="dark"]{--bg:#0d1320;--panel:#141c2c;--panel2:#1a2333;--line:#26304459;--ink:#e9edf6;--muted:#8b96ab;--faint:#5f6a80;--gold:#d8b44b;--pos:#54c98a;--neg:#e8636b;--grid:#20293c;}
:root[data-theme="light"]{--bg:#eef1f6;--panel:#ffffff;--panel2:#f6f8fb;--line:#d4dae6;--ink:#131a29;--muted:#5c6577;--faint:#8a93a5;--gold:#9a7a1e;--pos:#1f9d5c;--neg:#cf3b45;--grid:#e2e7ef;}
*{box-sizing:border-box}
.sheet{--mono:ui-monospace,"SF Mono",Menlo,"Cascadia Mono",monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  background:var(--bg);color:var(--ink);font-family:var(--sans);
  max-width:1080px;margin:0 auto;padding:44px 30px 60px;line-height:1.5;
  font-feature-settings:"ss01";-webkit-font-smoothing:antialiased;}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--gold);margin:0 0 14px;font-weight:600;}
h1{font-size:clamp(28px,4.6vw,44px);line-height:1.04;letter-spacing:-.02em;margin:0 0 14px;
  font-weight:800;text-wrap:balance;}
.thesis{color:var(--muted);font-size:16px;max-width:62ch;margin:0 0 6px;}
.thesis b{color:var(--ink);font-weight:600;}
.rule{height:1px;background:var(--line);border:0;margin:30px 0;}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:26px 0 8px;}
@media(max-width:820px){.kpis{grid-template-columns:repeat(3,1fr)}}
@media(max-width:520px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:11px;padding:15px 15px 13px;}
.kpi .k{font-family:var(--mono);font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--faint);margin-bottom:9px;}
.kpi .v{font-family:var(--mono);font-size:26px;font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums;}
.kpi .s{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:3px;}
.pos{color:var(--pos)} .neg{color:var(--neg)} .gold{color:var(--gold)}
h2{font-size:13px;font-family:var(--mono);letter-spacing:.13em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:0 0 4px;display:flex;align-items:baseline;gap:12px;}
h2 .sub{font-size:12px;letter-spacing:0;text-transform:none;color:var(--faint);font-weight:400;}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 22px 18px;margin-top:14px;}
.hero-wrap{margin-top:34px;}
canvas{width:100%;display:block;}
.cap{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:12px;line-height:1.6;}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:34px;}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.bars{display:flex;flex-direction:column;gap:11px;margin-top:18px;}
.bar-row{display:grid;grid-template-columns:64px 1fr 28px;align-items:center;gap:12px;font-family:var(--mono);font-size:12px;}
.bar-track{height:16px;background:var(--panel2);border-radius:4px;overflow:hidden;}
.bar-fill{height:100%;border-radius:4px;}
.bar-row .n{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums;}
.method p{font-size:13.5px;color:var(--muted);margin:0 0 12px;}
.method b{color:var(--ink);font-weight:600;}
.method code{font-family:var(--mono);font-size:12px;background:var(--panel2);padding:2px 6px;border-radius:5px;color:var(--gold);}
.tbl-wrap{margin-top:14px;border:1px solid var(--line);border-radius:14px;overflow:hidden;}
.tbl-scroll{max-height:460px;overflow:auto;}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12.5px;}
thead th{position:sticky;top:0;background:var(--panel2);color:var(--faint);text-align:left;
  font-weight:500;font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:11px 14px;
  border-bottom:1px solid var(--line);z-index:2;}
th.r,td.r{text-align:right;font-variant-numeric:tabular-nums;}
tbody td{padding:9px 14px;border-bottom:1px solid var(--line);white-space:nowrap;}
tbody tr:hover{background:var(--panel2);}
td.match{white-space:normal;font-family:var(--sans);}
td.pick{color:var(--muted);}
.chip{display:inline-block;min-width:52px;text-align:right;padding:2px 7px;border-radius:5px;font-variant-numeric:tabular-nums;}
.chip.pos{background:#54c98a1f;color:var(--pos);} .chip.neg{background:#e8636b1f;color:var(--neg);}
.foot{margin-top:34px;display:grid;grid-template-columns:1.15fr .85fr;gap:22px;}
@media(max-width:820px){.foot{grid-template-columns:1fr}}
.note{font-size:12.5px;color:var(--muted);line-height:1.65;}
.note b{color:var(--ink);}
.resume{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);
  border-left:3px solid var(--gold);border-radius:12px;padding:18px 20px;}
.resume .k{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);margin-bottom:10px;}
.resume li{font-size:13px;color:var(--ink);margin:0 0 9px;padding-left:2px;line-height:1.5;}
.resume ul{margin:0;padding-left:18px;}
.legend{font-family:var(--mono);font-size:11px;color:var(--faint);display:flex;gap:18px;margin-top:6px;flex-wrap:wrap;}
.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px;vertical-align:middle;}
</style>

<div class="sheet">
  <p class="eyebrow">Quantitative Forecasting · Closing-Line-Value Audit</p>
  <h1>World Cup 2026 Forecasting Model<br>CLV Tearsheet</h1>
  <p class="thesis">A time-decayed <b>Dixon-Coles</b> bivariate-Poisson engine with a <b>Monte-Carlo</b> tournament simulator, graded on <b>Closing Line Value</b> — the standard measure of forecast edge — against real <b>Kalshi/Polymarket</b> closing lines.</p>
  <p class="thesis">Fixed rule, no cherry-picking: for every match, bet the model's predicted reg-time outcome at the market's <b>opening</b> price; CLV = how far the line moved in our favor by the <b>close</b>.</p>

  <section class="kpis" id="kpis"></section>

  <div class="hero-wrap">
    <h2>Cumulative CLV <span class="sub">— edge accrual across the tournament, in points of closing-line value</span></h2>
    <div class="panel"><canvas id="equity" height="300"></canvas>
      <div class="legend"><span><span class="dot" style="background:var(--gold)"></span>cumulative CLV (pts)</span><span><span class="dot" style="background:var(--pos)"></span>positive game</span><span><span class="dot" style="background:var(--neg)"></span>negative game</span></div>
    </div>
    <p class="cap" id="heromcap"></p>
  </div>

  <div class="cols">
    <div>
      <h2>Distribution <span class="sub">— per-game CLV</span></h2>
      <div class="panel"><div class="bars" id="bars"></div></div>
    </div>
    <div>
      <h2>How it's computed</h2>
      <div class="panel method">
        <p><b>Model.</b> Dixon-Coles attack/defence ratings over 40k+ international matches (5-yr half-life decay, ridge-regularized), fed into a 400k-draw Monte-Carlo per match for calibrated win / scoreline / total distributions.</p>
        <p><b>Benchmark.</b> Real prediction-market closing lines pulled from the <code>Kalshi</code> candlestick API (free, no-auth) and <code>Polymarket</code> via Oddpool — the price the sharpest money converges on by kickoff.</p>
        <p><b>Metric.</b> <code>CLV = close ÷ open − 1</code> on the model's picked side. Beating the close is the cleanest evidence a forecast held information the market had not yet priced.</p>
      </div>
    </div>
  </div>

  <div style="margin-top:34px">
    <h2>Every graded match <span class="sub" id="tblsub"></span></h2>
    <div class="tbl-wrap"><div class="tbl-scroll"><table>
      <thead><tr><th>Date</th><th>Match</th><th>Model pick</th><th class="r">Entry</th><th class="r">Close</th><th class="r">CLV</th></tr></thead>
      <tbody id="tbody"></tbody>
    </table></div></div>
  </div>

  <div class="foot">
    <div class="note">
      <p><b>Read it honestly.</b> n = 92 of the tournament's 103 played matches (the final is upcoming; ~10 lacked matched market data). CLV in samples this size is noisy, and the mean is pulled up by a right tail of large edges — the <b>median (+4.5%)</b> is the more conservative read of the typical game. This demonstrates the <b>methodology has signal</b>; it is not a claim of a guaranteed repeatable edge, and it isn't a betting P&amp;L.</p>
      <p style="color:var(--faint)">Built in Python (NumPy) · Kalshi &amp; Polymarket API integration · out-of-sample calibration via Brier score, log-loss &amp; reliability curves.</p>
    </div>
    <div class="resume">
      <div class="k">Résumé bullet — copy ready</div>
      <ul>
        <li>Built a Dixon-Coles + Monte-Carlo football forecasting engine (Python/NumPy) over 40k+ matches; validated against live Kalshi/Polymarket <b>closing lines</b>, beating the close on <b>64% of 92 World Cup matches</b> (+4.5% median CLV).</li>
        <li>Engineered a free Kalshi candlestick API pipeline to auto-grade forecasts on <b>Closing Line Value</b>, and diagnosed model bias via out-of-sample calibration (Brier / log-loss).</li>
      </ul>
    </div>
  </div>
</div>

<script>
const D = __DATA__;
const $=(s)=>document.querySelector(s);
const s=D.stats;
const sign=(x)=>(x>0?"+":"")+x;
// KPIs
const kpis=[
  {k:"Matches graded",v:s.n,cl:"",sub:s.d0.slice(5)+" → "+s.d1.slice(5)},
  {k:"Mean CLV",v:sign(s.mean)+"%",cl:"pos",sub:"per game"},
  {k:"Median CLV",v:sign(s.median)+"%",cl:"pos",sub:"typical game"},
  {k:"Beat the close",v:s.beatpct+"%",cl:"gold",sub:s.beat+" of "+s.n},
  {k:"Best",v:sign(s.best)+"%",cl:"pos",sub:s.bestg.length>22?s.bestg.slice(0,22)+"…":s.bestg},
  {k:"Worst",v:sign(s.worst)+"%",cl:"neg",sub:s.worstg.length>22?s.worstg.slice(0,22)+"…":s.worstg},
];
$("#kpis").innerHTML=kpis.map(t=>`<div class="kpi"><div class="k">${t.k}</div><div class="v ${t.cl}">${t.v}</div><div class="s">${t.sub}</div></div>`).join("");
$("#heromcap").textContent=`Running total across ${s.n} matches: +${s.cumtotal} points of cumulative CLV. The curve's slope is the edge; its dips are the games the market moved against the model.`;
$("#tblsub").textContent=`— ${s.n} matches, sorted chronologically`;
// histogram
const mx=Math.max(...D.hist.map(h=>h.count));
$("#bars").innerHTML=D.hist.map(h=>`<div class="bar-row"><span style="color:var(--muted)">${h.label}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(3,h.count/mx*100)}%;background:${h.neg?'var(--neg)':'var(--pos)'}"></div></div><span class="n">${h.count}</span></div>`).join("");
// table
$("#tbody").innerHTML=D.games.map(g=>`<tr><td>${g.date}</td><td class="match">${g.match}</td><td class="pick">${g.pick}</td><td class="r">${g.open}%</td><td class="r">${g.close}%</td><td class="r"><span class="chip ${g.clv>=0?'pos':'neg'}">${sign(g.clv)}%</span></td></tr>`).join("");
// equity curve
function draw(){
  const cv=$("#equity"), dpr=window.devicePixelRatio||1;
  const W=cv.clientWidth, H=300; cv.width=W*dpr; cv.height=H*dpr;
  const ctx=cv.getContext("2d"); ctx.scale(dpr,dpr); ctx.clearRect(0,0,W,H);
  const cs=getComputedStyle(document.querySelector(".sheet"));
  const gold=cs.getPropertyValue("--gold"),pos=cs.getPropertyValue("--pos"),neg=cs.getPropertyValue("--neg"),grid=cs.getPropertyValue("--grid"),faint=cs.getPropertyValue("--faint");
  const cum=D.cum, n=cum.length, padL=44,padR=12,padT=14,padB=22;
  const mxv=Math.max(...cum,0), mnv=Math.min(...cum,0);
  const X=(i)=>padL+(W-padL-padR)*(i/(n-1));
  const Y=(v)=>padT+(H-padT-padB)*(1-(v-mnv)/(mxv-mnv||1));
  ctx.font="10px ui-monospace,monospace"; ctx.fillStyle=faint; ctx.strokeStyle=grid; ctx.lineWidth=1;
  for(let g=0;g<=4;g++){const v=mnv+(mxv-mnv)*g/4;const y=Y(v);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.fillText(Math.round(v),4,y+3);}
  // per-game markers
  let prev=0;
  for(let i=0;i<n;i++){const up=cum[i]>=prev;ctx.fillStyle=up?pos:neg;ctx.globalAlpha=.5;ctx.beginPath();ctx.arc(X(i),Y(cum[i]),1.6,0,7);ctx.fill();prev=cum[i];}
  ctx.globalAlpha=1;
  // area + line
  const grad=ctx.createLinearGradient(0,padT,0,H-padB);grad.addColorStop(0,gold+"33");grad.addColorStop(1,gold+"00");
  ctx.beginPath();ctx.moveTo(X(0),Y(cum[0]));for(let i=1;i<n;i++)ctx.lineTo(X(i),Y(cum[i]));
  ctx.lineTo(X(n-1),Y(mnv));ctx.lineTo(X(0),Y(mnv));ctx.closePath();ctx.fillStyle=grad;ctx.fill();
  ctx.beginPath();ctx.moveTo(X(0),Y(cum[0]));for(let i=1;i<n;i++)ctx.lineTo(X(i),Y(cum[i]));
  ctx.strokeStyle=gold;ctx.lineWidth=2;ctx.lineJoin="round";ctx.stroke();
  ctx.fillStyle=gold;ctx.beginPath();ctx.arc(X(n-1),Y(cum[n-1]),3.5,0,7);ctx.fill();
}
draw(); new ResizeObserver(draw).observe($("#equity"));
new MutationObserver(draw).observe(document.documentElement,{attributes:true,attributeFilter:["data-theme"]});
window.matchMedia("(prefers-color-scheme:dark)").addEventListener("change",draw);
</script>
""".replace("__DATA__", J)

path=os.path.join(OUT,"clv_tearsheet.html")
open(path,"w").write(html)
print("wrote", path, len(html), "bytes |", stats["n"], "games")
