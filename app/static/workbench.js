import {request} from './client.js';
import {snapshot, history, packages} from './view.js';
import {visualize} from './plots.js';

const form = document.querySelector('#source');
const file = document.querySelector('#file');
const profile = document.querySelector('#profile');
const status = document.querySelector('#notice');
const detail = document.querySelector('#review');
const evidence = document.querySelector('#evidence');
const coverageForm = document.querySelector('#coverage');
const dispatchButton = document.querySelector('#dispatch');
const stages = [...document.querySelectorAll('[data-stage]')];
let stage = 'balance';
let report, selected, batch, chosen, running = false;

function source() {
  const data = new FormData();
  if (file.files.length) data.append('file',file.files[0]);
  else data.append('sample',profile.value);
  return data;
}

function announce(text, failure = false) {
  status.textContent = text;
  status.dataset.failure = String(failure);
}

function draw() {
  if (!report) return;
  snapshot(report, selected, stage);
  packages(report, selected);
  visualize(report, selected);
  for (const button of stages) button.setAttribute('aria-pressed',String(button.dataset.stage===stage));
  document.querySelector('#panel-title').textContent = stages.find(button => button.dataset.stage===stage)?.textContent || '运行对账';
  detail.hidden = !batch;
  coverageForm.hidden = !batch || !chosen || !report.dispatch?.dispatchable;
  dispatchButton.disabled = !batch || !report.dispatch?.dispatchable
    || !(report.packages || []).some(item => item.status === 'PENDING');
  if (batch) {
    document.querySelector('#run-status').textContent = `${batch.id.slice(0,10)} · ${batch.status} · r${batch.revision}`;
    detail.querySelector('[value="APPROVED"]').disabled = !report.balance?.releasable || batch.status==='APPROVED';
    detail.querySelector('[value="HELD"]').disabled = batch.status==='APPROVED';
    evidence.href = `/api/runs/${batch.id}/evidence`;
    if (chosen) {
      const picked = (report.packages || []).find(item => item.id === chosen);
      document.querySelector('#package-state').textContent =
        `已选 ${chosen.slice(0,8)} · ${picked?.status ?? ''} · 净覆盖 ${picked?.net_cells ?? 0}/${picked?.cells ?? 0}`;
    }
  } else {
    document.querySelector('#package-state').textContent = '';
  }
}

function show(payload, committed = false) {
  batch = committed ? payload : null;
  report = committed ? payload.report : payload;
  detail.elements.note.value = batch?.note || '';
  selected = report.cases?.[0]?.case;
  chosen = null;
  draw();
}

async function storedPackages() {
  if (!batch) return;
  const data = await request(`/api/runs/${batch.id}/packages`);
  report.packages = data.items;
  draw();
}

async function refresh() {
  const data = await request('/api/runs');
  history(data.items, batch?.id);
}

async function perform(action) {
  if (running) return;
  running = true;
  document.body.setAttribute('aria-busy','true');
  announce('处理中…');
  try { await action(); }
  catch (error) { announce(error.message,true); }
  finally { running = false; document.body.removeAttribute('aria-busy'); }
}

function preview(next) {
  return perform(async () => {
    const payload = await request(`/api/stages/${next}`,{method:'POST',body:source()});
    stage = next;
    show(payload);
    announce('阶段预览已更新');
    await refresh();
  });
}

stages.forEach(button => button.addEventListener('click',()=>preview(button.dataset.stage)));
form.addEventListener('submit', event => {
  event.preventDefault();
  perform(async () => {
    const result = await request('/api/runs',{method:'POST',body:source()});
    stage = 'balance'; show(result,true);
    announce('批次已保存'); await storedPackages(); await refresh();
  });
});
const filename = document.querySelector('#file-name');
profile.addEventListener('change',()=>{file.value=''; filename.textContent=''; preview(stage);});
file.addEventListener('change',()=>{filename.textContent=file.files[0]?.name || ''; preview(stage);});
document.querySelector('#rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-case]');
  if (button) { selected = button.dataset.case; chosen = null; draw(); document.querySelector(`[data-case="${CSS.escape(selected)}"]`).focus(); }
});
document.querySelector('#package-rows').addEventListener('click',event=>{
  const button = event.target.closest('[data-package]');
  if (button) { chosen = button.dataset.package; draw(); }
});
dispatchButton.addEventListener('click',()=>{
  if (!batch) return;
  perform(async()=>{
    const pending = (report.packages || []).filter(item => item.status === 'PENDING').length;
    const data = await request(`/api/runs/${batch.id}/dispatch`,{method:'POST'});
    report.packages = data.items;
    announce(pending ? `已派发 ${pending} 个补测包` : '没有待派发的补测包');
    draw();
  });
});
coverageForm.addEventListener('submit',event=>{
  event.preventDefault();
  if (!chosen) { announce('请先选择补测包',true); return; }
  perform(async()=>{
    let rects;
    try { rects = JSON.parse(document.querySelector('#coverage-input').value); }
    catch { announce('覆盖范围需要 JSON 矩形数组',true); return; }
    const result = await request(`/api/packages/${chosen}/coverage`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rects})});
    document.querySelector('#package-state').textContent = `已登记 · 净覆盖 ${result.net_cells}/${result.cells} · 剩余 ${result.remaining_cells}`;
    announce(result.status==='CLOSED' ? '补测包已按最终净覆盖关闭' : '已登记新增覆盖');
    await storedPackages();
  });
});
document.querySelector('#history').addEventListener('click',event=>{
  const button = event.target.closest('[data-run]');
  if (button) perform(async()=>{
    const result = await request(`/api/runs/${button.dataset.run}`);
    stage='balance'; show(result,true); announce('已载入历史批次');
    await storedPackages(); await refresh();
  });
});
detail.addEventListener('submit',event=>{
  event.preventDefault();
  perform(async()=>{
    const payload={status:event.submitter.value,revision:batch.revision,note:detail.elements.note.value};
    const result=await request(`/api/runs/${batch.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    show(result,true); announce(result.status==='APPROVED'?'批次已签发':'批次已暂缓');
    await storedPackages(); await refresh();
  });
});
preview(stage);
