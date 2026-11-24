import {element, pretty} from './client.js';

const labels = {READY:'通过', MISMATCH:'差异待复核', PENDING:'待复核', APPROVED:'已签发', HELD:'已暂缓'};
const packageLabels = {PENDING:'待派发', DISPATCHED:'已派发', CLOSED:'已关闭', SUPERSEDED:'已失效'};
const headers = ['业务分组', '输入行', '计算值', '参考值', '判定'];

export function badge(status) {
  return element('span', labels[status] || status, {class:'badge', 'data-result':status, title: status});
}

export function packageBadge(status) {
  return element('span', packageLabels[status] || status, {class:'badge', 'data-result':status, title: status});
}

export function packages(report, selected) {
  const checks = report.dispatch?.checks || {};
  const target = document.querySelector('#package-rows');
  const state = document.querySelector('#dispatch-state');
  const summary = document.querySelector('#dispatch-checks');
  target.replaceChildren();
  state.textContent = report.dispatch
    ? (report.dispatch.dispatchable ? '四项对平，可派发' : `阻止派发：${report.dispatch.blocked_by.join('、')}`)
    : '';
  summary.textContent = Object.values(checks)
    .map(check => `${check.label} ${check.value}/${check.expected} ${check.ok ? '✓' : '✗'}`)
    .join(' · ');
  const items = (report.packages || []).filter(item => item.case === selected);
  const body = target.createTBody();
  const head = target.createTHead().insertRow();
  head.append(...['补测包', '业务分组', '缺口像元', '净覆盖', '范围', '状态'].map(title => element('th', title, {scope:'col'})));
  for (const item of items) {
    const row = body.insertRow();
    const button = element('button', item.id.slice(0, 8), {type:'button','data-package':item.id});
    row.insertCell().append(button);
    row.insertCell().textContent = item.case;
    row.insertCell().textContent = item.cells;
    row.insertCell().textContent = item.net_cells ?? '—';
    row.insertCell().textContent = item.bounds.join(',');
    row.insertCell().append(packageBadge(item.status || 'PENDING'));
  }
  if (!items.length) body.insertRow().insertCell().textContent = '该分组没有缺口';
}

export function snapshot(report, selected, stage) {
  const stats = report.intake;
  document.querySelector('[data-metric="input"]').textContent = stats.input;
  document.querySelector('[data-metric="accepted"]').textContent = stats.accepted;
  document.querySelector('[data-metric="isolated"]').textContent = stats.rejected;
  document.querySelector('[data-metric="cases"]').textContent = report.cases?.length ?? '—';
  const table = document.querySelector('#rows');
  table.replaceChildren();
  const head = element('tr');
  const body = table.createTBody();
  if (stage === 'intake') {
    head.append(...['源行', '记录键', '业务分组', '原因码'].map(title => element('th', title, {scope:'col'})));
    for (const item of stats.isolation) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    if (!stats.isolation.length) body.insertRow().insertCell().textContent = '当前文件没有隔离行';
  } else {
    head.append(...headers.map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      [row.records.length, row.measure?.value ?? '—', row.measure?.expected ?? '—'].forEach(value=>tr.insertCell().textContent=value);
      tr.insertCell().append(badge(row.status));
    }
  }
  table.createTHead().append(head);
  const picked = report.cases?.find(row=>row.case===selected);
  document.querySelector('#detail-title').textContent = picked ? `分组 ${picked.case}` : '采信摘要';
  const shown = picked ? picked.measure?.evidence ?? picked.prep?.details ?? {原因:picked.status} : stats.reasons;
  document.querySelector('#detail').textContent = pretty(shown);
  document.querySelector('#counts').textContent = report.dispatch
    ? `补测包 ${report.dispatch.packages} 个 · 缺口 ${report.dispatch.cells} 像元`
    : report.balance
      ? `行数 ${report.balance.accounted}/${report.balance.input} · ${report.balance.ready} 组通过`
      : `采信 ${stats.accepted} 行 · 隔离 ${stats.rejected} 行`;
}

export function history(items, active) {
  const target = document.querySelector('#history');
  target.replaceChildren();
  for (const run of items) {
    const button = element('button', run.id.slice(0,10), {'data-run':run.id,'aria-pressed':String(run.id===active),type:'button'});
    const item = element('li');
    item.append(button, badge(run.status));
    target.append(item);
  }
  if (!items.length) target.append(element('li','尚无执行批次'));
}
