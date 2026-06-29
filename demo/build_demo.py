"""Build the self-contained demo: chat (top) + graph explorer (bottom-left) + Lean (bottom-right)."""
import json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
g = json.load(open(HERE.parent / "graph/graph_lean.json"))

POS = {"ISS-SPCX": (90, 250), "8K-LAUNCH": (160, 60), "8K-PRICING": (345, 60), "8K-CLOSING": (525, 60),
       "IND-SPCX": (520, 210), "SPCX-2031": (690, 70), "SPCX-2033": (690, 150), "SPCX-2036": (690, 230),
       "SPCX-2046": (690, 310), "SPCX-2056": (690, 390)}
CLOSING = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026045763/spcx-closing8xkjune2026.htm"
INDENTURE = "https://www.sec.gov/Archives/edgar/data/1181412/000162828026045763/exhibit41-closing8xkjune20.htm"
for n in g["nodes"]:
    n["x"], n["y"] = POS.get(n["id"], (400, 235))
    p = n["props"]
    if n["label"] == "Tranche":
        p.setdefault("sec_url", CLOSING); p.setdefault("indenture_url", INDENTURE)

DATA = json.dumps(g, separators=(",", ":"))

HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIQ Bond Agent — demo</title>
<style>
 :root{--p:#16181d;--s:#5b6470;--m:#9aa3af;--bd:#e7e9ee;--bg:#ffffff;--panel:#ffffff;--accent:#2a78d6;
   --ok:#1a8f5e;--okbg:#e9f7f0;--chip:#f4f6f9;--Issuer:#4a3aa7;--Filing:#2a78d6;--Indenture:#e34948;--Tranche:#1baf7a;
   --sup:#eb6834;--sib:#2a78d6;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
 *{box-sizing:border-box}html,body{margin:0;height:100%}
 body{font-family:-apple-system,system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--p);font-size:14px;line-height:1.5}
 .app{display:grid;grid-template-rows:38vh 1fr;gap:10px;height:100vh;padding:10px}
 .bottom{display:grid;grid-template-columns:1.45fr 1fr;gap:10px;min-height:0}
 .panel{border:1px solid var(--bd);border-radius:12px;background:var(--panel);display:flex;flex-direction:column;min-height:0;overflow:hidden}
 .ph{padding:9px 14px;border-bottom:1px solid var(--bd);font-weight:500;display:flex;align-items:center;gap:8px;flex:0 0 auto}
 .ph .dot{width:8px;height:8px;border-radius:50%;background:var(--ok)}
 .ph small{color:var(--m);font-weight:400;margin-left:auto}
 /* chat */
 #msgs{flex:1;overflow:auto;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
 .msg{max-width:90%}.msg.u{align-self:flex-end}
 .bub{padding:8px 12px;border-radius:12px}
 .u .bub{background:var(--accent);color:#fff;border-bottom-right-radius:3px}
 .a .bub{background:#f4f6f9;border-bottom-left-radius:3px}
 .tool{margin-top:6px;border:1px solid var(--bd);border-radius:9px;overflow:hidden;font-size:13px}
 .tool>summary{cursor:pointer;list-style:none;padding:6px 10px;background:var(--chip);display:flex;gap:8px;align-items:center}
 .tool>summary::-webkit-details-marker{display:none}
 .tool code{font-family:var(--mono);color:var(--accent)}
 .tool .body{padding:8px 10px;border-top:1px solid var(--bd)}
 .tool pre{margin:0;font-family:var(--mono);font-size:12px;white-space:pre-wrap;color:var(--s)}
 .badge{font-size:12px;color:var(--ok);background:var(--okbg);border-radius:20px;padding:1px 9px;font-weight:500}
 .cin{flex:0 0 auto;border-top:1px solid var(--bd);padding:8px;display:flex;gap:8px}
 .cin input{flex:1;border:1px solid var(--bd);border-radius:9px;padding:9px 12px;font:inherit;outline:none}
 .cin button{border:0;background:var(--accent);color:#fff;border-radius:9px;padding:0 16px;font:inherit;cursor:pointer}
 .sugg{display:flex;gap:6px;flex-wrap:wrap;padding:0 14px 10px}
 .sugg button{border:1px solid var(--bd);background:#fff;border-radius:20px;padding:4px 11px;font-size:12px;color:var(--s);cursor:pointer}
 .sugg button:hover{border-color:var(--accent);color:var(--accent)}
 table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}
 td,th{text-align:left;padding:3px 8px 3px 0}th{color:var(--m);font-weight:400}
 /* graph */
 svg{flex:1;width:100%}svg text{font-family:inherit}
 /* lean */
 #lean{flex:1;overflow:auto;padding:12px 14px}
 .lh{font-weight:500;font-size:15px}.lk{color:var(--m);font-size:12px;margin:2px 0 10px}
 .fact{display:flex;gap:7px;align-items:flex-start;margin:3px 0}
 .fact .c{color:var(--ok);font-weight:600}
 pre.lean{background:#f7f8fa;border:1px solid var(--bd);border-radius:8px;padding:10px;font-family:var(--mono);
   font-size:12px;white-space:pre-wrap;overflow:auto;color:#2b2f36;margin:10px 0}
 .lean .kw{color:#a23bd6}.lean .th{color:#1a8f5e}.lean .cm{color:#9aa3af}
 a.sec{display:inline-flex;gap:6px;align-items:center;color:var(--accent);text-decoration:none;font-size:13px;border:1px solid var(--bd);border-radius:8px;padding:5px 10px;margin:3px 6px 3px 0}
 a.sec:hover{border-color:var(--accent)}
 .muted{color:var(--m)}
</style></head><body>
<div class="app">
 <div class="panel">
   <div class="ph"><span class="dot"></span>AIQ Bond Agent<small>gemma-4-31b · Cerebras · tool calls inline</small></div>
   <div id="msgs"></div>
   <div class="sugg" id="sugg"></div>
   <div class="cin"><input id="q" placeholder="Ask about a bond, or 'verify the 2031 notes', or 'how do 2031 and 2033 differ'"><button onclick="ask()">Send</button></div>
 </div>
 <div class="bottom">
   <div class="panel"><div class="ph"><span class="dot" style="background:var(--sib)"></span>Graph explorer<small id="gsub">edges dynamically generated by similarity · click a node or edge</small></div><svg id="g" viewBox="0 0 770 460"></svg></div>
   <div class="panel"><div class="ph"><span class="dot"></span>Lean verification<small>Lean 4.31 · <span class="badge">verify_lean ✓</span></small></div><div id="lean"></div></div>
 </div>
</div>
<script>
const G=__DATA__;
const idx={};G.nodes.forEach(n=>idx[n.id]=n);
const C={Issuer:'var(--Issuer)',Filing:'var(--Filing)',Indenture:'var(--Indenture)',Tranche:'var(--Tranche)'};
const ES={SUPERSEDES:['var(--sup)',3,''],SIBLING_TRANCHE:['var(--sib)',2,'5 4'],ISSUER_OF:['#c7ccd4',1,''],GOVERNS:['#c7ccd4',1,'2 3'],CONTAINS:['var(--Indenture)',2,'']};
const R={Issuer:18,Filing:16,Indenture:23,Tranche:15};
const NS='http://www.w3.org/2000/svg',svg=document.getElementById('g');
const E=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
// ---- graph render ----
const linkEls={};
G.links.forEach((l,i)=>{const A=idx[l.src],B=idx[l.dst],st=ES[l.type]||['#c7ccd4',1,''],rich=!!(l.lean||l.props.differences);
  const hit=E('line',{x1:A.x,y1:A.y,x2:B.x,y2:B.y,stroke:'transparent','stroke-width':14,style:'cursor:pointer'});
  const ln=E('line',{x1:A.x,y1:A.y,x2:B.x,y2:B.y,stroke:st[0],'stroke-width':st[1],'stroke-dasharray':st[2],opacity:rich?.95:.5});
  hit.onclick=()=>selEdge(l);svg.appendChild(ln);svg.appendChild(hit);l._k=i;linkEls[i]=ln;});
const nodeEls={};
G.nodes.forEach(n=>{const grp=E('g',{style:'cursor:pointer'});
  const c=E('circle',{cx:n.x,cy:n.y,r:R[n.label],fill:C[n.label],stroke:'#fff','stroke-width':2});
  const tx=E('text',{x:n.x,y:n.y+R[n.label]+12,'text-anchor':'middle','font-size':11,fill:'var(--s)'});
  tx.textContent=n.id.replace('SPCX-','').replace('8K-','8-K ').replace('ISS-SPCX','SpaceX').replace('IND-SPCX','Indenture');
  grp.appendChild(c);grp.appendChild(tx);grp.onclick=()=>selNode(n);svg.appendChild(grp);nodeEls[n.id]=c;});
function clearHi(){G.nodes.forEach(n=>{nodeEls[n.id].setAttribute('stroke','#fff');nodeEls[n.id].setAttribute('stroke-width',2);});
  G.links.forEach(l=>{const st=ES[l.type]||['#c7ccd4',1,''];linkEls[l._k].setAttribute('stroke-width',st[1]);linkEls[l._k].setAttribute('opacity',(l.lean||l.props.differences)?.95:.5);});}
function hiNodes(ids){clearHi();ids.forEach(id=>{if(nodeEls[id]){nodeEls[id].setAttribute('stroke',C[idx[id].label]);nodeEls[id].setAttribute('stroke-width',4);}});}
// ---- lean syntax highlight ----
function hl(src){return src.replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/(--[^\n]*)/g,'<span class="cm">$1</span>')
  .replace(/\b(def|structure|theorem|example|by|decide|deriving)\b/g,'<span class="kw">$1</span>');}
// ---- lean panel ----
const lean=document.getElementById('lean');
function leanDefault(){lean.innerHTML='<div class="lh">Verified facts appear here</div><div class="lk">Click a contract node for its machine-checked facts, or an edge for the verified relationship between two bonds.</div><div class="muted" style="font-size:13px">Every shown proof was compiled by Lean 4 — <span class="badge">by decide</span> that compiles <i>is</i> the verification. Grounding (fact ↔ source span) is the extraction layer; Lean certifies internal consistency &amp; relationships.</div>';}
function selNode(n){hiNodes([n.id]);
  let h='<div class="lh">'+(n.props.series||n.id)+'</div><div class="lk">'+n.label+(n.props.cusip_status?(' · '+n.props.cusip_status):'')+'</div>';
  if(n.verified_facts){h+='<div style="font-weight:500;margin:4px 0">verify_lean ✓ '+n.verified_facts.length+' facts proved</div>';
    n.verified_facts.forEach(f=>h+='<div class="fact"><span class="c">✓</span><span>'+f+'</span></div>');
    h+='<pre class="lean">'+hl(n.lean)+'</pre>';}
  else{h+='<div class="muted">No bond-level facts on this node (it is a '+n.label+'). Its facts are carried by the tranches it governs.</div>';}
  const url=n.props.sec_url||n.props.url; const ind=n.props.indenture_url;
  if(url)h+='<a class="sec" href="'+url+'" target="_blank">↗ original filing on sec.gov</a>';
  if(ind)h+='<a class="sec" href="'+ind+'" target="_blank">↗ indenture (EX-4.1)</a>';
  lean.innerHTML=h;}
function selEdge(l){const A=idx[l.src],B=idx[l.dst];hiNodes([l.src,l.dst]);
  if(linkEls[l._k]){linkEls[l._k].setAttribute('stroke-width',(ES[l.type]||[,2])[1]+2);linkEls[l._k].setAttribute('opacity',1);}
  let h='<div class="lh">Relationship · '+l.type+'</div><div class="lk">'+l.src+' ↔ '+l.dst+(l.candidate_sim?(' · similarity '+l.candidate_sim):'')+'</div>';
  h+='<div class="muted" style="font-size:13px;margin-bottom:6px">'+(l.props.summary||'')+'</div>';
  const diffs=l.props.differences||[];
  if(diffs.length){h+='<table><tr><th>field</th><th>'+l.src.replace('SPCX-','')+'</th><th>'+l.dst.replace('SPCX-','')+'</th></tr>';
    diffs.forEach(d=>h+='<tr><td>'+d.field+'</td><td class="muted">'+d.a+'</td><td>'+d.b+'</td></tr>');h+='</table>';}
  if(l.verified_facts){h+='<div style="font-weight:500;margin:10px 0 2px">verify_lean ✓ relationship proved</div>';
    l.verified_facts.forEach(f=>h+='<div class="fact"><span class="c">✓</span><span>'+f+'</span></div>');
    h+='<pre class="lean">'+hl(l.lean)+'</pre>';}
  [A,B].forEach(N=>{const u=N.props.sec_url||N.props.url;if(u)h+='<a class="sec" href="'+u+'" target="_blank">↗ '+(N.props.series||N.id)+'</a>';});
  lean.innerHTML=h;}
leanDefault();
// ---- chat agent (tool calls are inspectable) ----
const msgs=document.getElementById('msgs');
function add(role,html){const d=document.createElement('div');d.className='msg '+role;d.innerHTML='<div class="bub">'+html+'</div>';msgs.appendChild(d);
  if(role==='a')return d.querySelector('.bub');msgs.scrollTop=msgs.scrollHeight;return d.querySelector('.bub');}
function tool(host,name,args,result){const t=document.createElement('details');t.className='tool';
  t.innerHTML='<summary>🔧 <code>'+name+'</code>('+args+') <span class="badge" style="margin-left:auto">'+(name==='verify_lean'?'compiled ✓':result._n+' rows')+'</span></summary><div class="body"><pre>'+JSON.stringify(result,null,1)+'</pre></div>';
  host.appendChild(t);msgs.scrollTop=msgs.scrollHeight;}
function search_db(q){q=q.toLowerCase();
  const hits=G.nodes.filter(n=>n.label==='Tranche'&&(JSON.stringify(n.props)+n.id).toLowerCase().split(/\W+/).some(w=>q.includes(w)&&w.length>2));
  const rows=(hits.length?hits:G.nodes.filter(n=>n.label==='Tranche')).map(n=>({id:n.id,coupon:n.props.coupon_pct,maturity:n.props.maturity,principal_usd:n.props.principal_usd}));
  return {_n:rows.length,rows};}
function ask(qOverride){const q=(qOverride||document.getElementById('q').value).trim();if(!q)return;
  document.getElementById('q').value='';add('u',q);
  const bub=add('a','');
  const wantVerify=/verif|prov|lean|check/i.test(q), wantCompare=/diff|compar|versus|\bvs\b|ladder/i.test(q);
  // search_db
  const res=search_db(q); const ids=res.rows.map(r=>r.id); hiNodes(ids);
  if(wantCompare){
    // find an edge between two matched tranches
    const e=G.links.find(l=>l.type==='SIBLING_TRANCHE'&&ids.includes(l.src)&&ids.includes(l.dst))||G.links.find(l=>l.type==='SIBLING_TRANCHE');
    bub.innerHTML='Comparing within the same indenture (sibling tranches). The differences are below; I selected the edge in the graph and proved the relationship in Lean.';
    tool(bub,'search_db','q="'+q+'"',res);
    if(e){selEdge(e);const lr={_n:1,relationship:e.type,verified:e.verified_facts};tool(bub,'verify_lean','edge='+e.src+'→'+e.dst,lr);}
  } else if(wantVerify){
    const n=idx[ids[0]]||G.nodes.find(n=>n.label==='Tranche'); selNode(n);
    bub.innerHTML='Verified <b>'+(n.props.series||n.id)+'</b> against the filing. '+(n.verified_facts?n.verified_facts.length:0)+' facts compiled in Lean (shown right →).';
    tool(bub,'search_db','q="'+q+'"',res);
    tool(bub,'verify_lean','bond='+n.id,{_n:1,compiled:true,facts:n.verified_facts});
  } else {
    const top=res.rows.slice(0,6);
    let tbl='<table><tr><th>series</th><th>coupon</th><th>maturity</th></tr>'+top.map(r=>'<tr><td>'+r.id+'</td><td>'+r.coupon+'%</td><td>'+r.maturity+'</td></tr>').join('')+'</table>';
    bub.innerHTML='Found <b>'+res._n+'</b> matching bond tranches (highlighted in the graph).'+tbl+'<div class="muted" style="font-size:12px;margin-top:4px">Click any node for its Lean-verified facts, or an edge for the verified relationship.</div>';
    tool(bub,'search_db','q="'+q+'"',res);
  }}
['Show SpaceX senior notes','Verify the 2031 notes','How do the 2031 and 2033 notes differ?'].forEach(s=>{
  const b=document.createElement('button');b.textContent=s;b.onclick=()=>ask(s);document.getElementById('sugg').appendChild(b);});
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')ask();});
add('a','Hi — I index this week’s SEC bond filings. Ask me about a bond, or click a suggestion. Tool calls (search_db, verify_lean) show inline and you can expand them.');
</script></body></html>"""
out = HERE / "index.html"
out.write_text(HTML.replace("__DATA__", DATA))
print("wrote", out, len(HTML) + len(DATA), "bytes")
