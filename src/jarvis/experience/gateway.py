"""Transport-facing experience gateway and dependency-free HUD."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict

from .projections import ExperienceProjection


EXPERIENCE_HUD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS // Experience Console</title>
<style>
:root{color-scheme:dark;--bg:#080b10;--panel:#101720;--line:#243241;--cyan:#67e8f9;--muted:#8aa0b4;--green:#86efac;--amber:#fbbf24;--red:#f87171}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 75% 10%,#122637 0,#080b10 42%);font:14px ui-monospace,SFMono-Regular,Consolas,monospace;color:#d8e5ef}header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}h1{font-size:16px;letter-spacing:.16em;color:var(--cyan);margin:0}main{display:grid;grid-template-columns:1.1fr 1fr 1fr;gap:12px;padding:16px;max-width:1500px;margin:auto}.panel{background:linear-gradient(145deg,#111b25dd,#0b1118ee);border:1px solid var(--line);border-radius:8px;padding:14px;min-height:120px;box-shadow:0 10px 30px #0005}.wide{grid-column:1/-1}h2{font-size:12px;color:var(--muted);letter-spacing:.12em;margin:0 0 12px}.state{font-size:27px;color:var(--green);letter-spacing:.08em}.row{display:flex;justify-content:space-between;border-bottom:1px dashed #21303c;padding:6px 0}.row:last-child{border:0}.muted{color:var(--muted)}.ok{color:var(--green)}.warn{color:var(--amber)}.err{color:var(--red)}pre{white-space:pre-wrap;max-height:300px;overflow:auto;color:#b8cad8;margin:0}@media(max-width:900px){main{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><header><h1>JARVIS // EXPERIENCE CONSOLE</h1><span id="connection" class="muted">AUTHENTICATED API REQUIRED</span></header>
<main><section class="panel"><h2>SYSTEM STATE</h2><div id="state" class="state">OFFLINE</div><div id="system"></div></section><section class="panel"><h2>RUNS / WORKERS</h2><div id="runs"></div></section><section class="panel"><h2>DEVICES</h2><div id="devices"></div></section><section class="panel"><h2>GOALS / APPROVALS</h2><div id="goals"></div></section><section class="panel"><h2>RESEARCH / ENGINEERING</h2><div id="specialists"></div></section><section class="panel"><h2>INTELLIGENCE</h2><div id="intelligence"></div></section><section class="panel"><h2>VOICE / CONVERSATION</h2><div id="voice"></div></section><section class="panel"><h2>PERSONAL OPERATOR</h2><div id="personal"></div></section><section class="panel"><h2>COMMUNICATIONS / HOME</h2><div id="personal-context"></div></section><section class="panel wide"><h2>EVENT TIMELINE</h2><pre id="timeline">Waiting for authenticated state...</pre></section></main>
<script>
const q=new URLSearchParams(location.search), owner=q.get('owner_id');
const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
const rows=(obj)=>Object.entries(obj||{}).map(([k,v])=>`<div class="row"><span class="muted">${esc(k)}</span><span>${esc(v)}</span></div>`).join('');
function paint(x){document.querySelector('#state').textContent=String(x.state||'offline').toUpperCase();document.querySelector('#system').innerHTML=rows({runtime:x.system?.runtime_state,offline:x.system?.offline,model:x.system?.model_provider||'none',core:x.system?.topology?.node_id||'unknown',profile:x.system?.topology?.profile||'unknown',transport:x.system?.topology?.node_transport?.transport||'unknown',events:x.system?.event_count,errors:x.system?.error_count});document.querySelector('#runs').innerHTML=rows({active:(x.runs||[]).length,worker:(x.system?.active_workers||0),approval:(x.approvals||[]).length});document.querySelector('#devices').innerHTML=rows({registered:(x.devices||[]).length,online:(x.devices||[]).filter(d=>d.status==='online').length});document.querySelector('#goals').innerHTML=rows({goals:(x.goals||[]).length,approvals:(x.approvals||[]).length});document.querySelector('#specialists').innerHTML=rows({research:(x.research||[]).length,engineering:(x.engineering||[]).length});document.querySelector('#intelligence').innerHTML=rows({missions:(x.missions||[]).length,skills:(x.skills||[]).length,automations:(x.automations||[]).length,briefings:(x.briefings||[]).length,findings:(x.intelligence||[]).length,projects:(x.workspace||[]).length,evaluations:(x.evaluations||[]).length});document.querySelector('#voice').innerHTML=rows({state:x.voice?.state||'idle',conversation:x.conversation?.conversation_id||'none'});document.querySelector('#personal').innerHTML=rows({mode:x.presence?.mode||x.attention?.mode||x.operations?.mode?.mode||'normal',device:x.presence?.active_device_id||'none',room:x.presence?.room_id||'none',endpoint:x.presence?.voice_endpoint_id||'none',focus:x.focus?.status||'inactive',followups:(x.follow_ups||[]).length});document.querySelector('#personal-context').innerHTML=rows({followups:(x.follow_ups||[]).length,home:x.home?.available?'connected':'unavailable',home_entities:(x.home?.entities||[]).length});document.querySelector('#timeline').textContent=(x.timeline||[]).map(e=>`${e.timestamp} ${e.event_type} ${JSON.stringify(e.payload||{})}`).join('\n')||'No events';document.querySelector('#connection').textContent='LIVE / EVENT PROJECTION';document.querySelector('#connection').className='ok'}
const credential=sessionStorage.getItem('jarvis_credential'),deviceId=sessionStorage.getItem('jarvis_device_id'),identityId=sessionStorage.getItem('jarvis_identity_id');
const headers=()=>({Authorization:`Bearer ${credential||''}`,'X-JARVIS-Device-ID':deviceId||'','X-JARVIS-Identity-ID':identityId||''});
async function ticket(){if(!credential||!deviceId||!identityId){return null}const r=await fetch('/v1/auth/stream-ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential,device_id:deviceId,identity_id:identityId,scope:'experience.events'})});return r.ok?(await r.json()).stream_ticket:null}
async function load(){if(!owner||!credential){return}const r=await fetch(`/v1/experience/state?owner_id=${encodeURIComponent(owner)}`,{headers:headers()});if(r.ok)paint(await r.json())}load();if(owner){ticket().then(token=>{if(!token){return}const stream=new EventSource(`/v1/experience/events?owner_id=${encodeURIComponent(owner)}&stream_ticket=${encodeURIComponent(token)}`);stream.onmessage=e=>{try{paint(JSON.parse(e.data))}catch(_){}}})}
</script></body></html>"""


class ExperienceGatewayService:
    """Thin facade used by HTTP; it delegates to the read-only projection."""

    def __init__(self, projection: ExperienceProjection) -> None:
        self.projection = projection

    async def state(self, owner_id: str) -> dict[str, object]:
        return asdict(await self.projection.state(owner_id))

    async def system(self, owner_id: str) -> dict[str, object]:
        return asdict(await self.projection.system(owner_id))

    def timeline(self, owner_id: str, limit: int = 100) -> list[dict[str, object]]:
        return list(self.projection.timeline(owner_id, limit))

    def hud(self, query: Mapping[str, str] | None = None) -> str:
        del query
        return EXPERIENCE_HUD_HTML
