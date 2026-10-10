const API = '';
let currentPage = 'dashboard';
let currentWorkflow = null;
let workflows = [];
let decomposeSteps = [];

const ICONS = {
  workflows: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  executions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  plus: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
};

function navigateTo(page) {
  currentPage = page;
  if (page !== 'execution-detail') stopLive();
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`[data-page="${page}"]`).classList.add('active');

  const titles = {
    dashboard: '仪表盘',
    workflows: '工作流',
    editor: '编辑器',
    templates: '模板中心',
    executions: '执行记录',
  };
  document.getElementById('page-title').textContent = titles[page] || page;

  const btnNew = document.getElementById('btn-new-workflow');
  btnNew.style.display = page === 'workflows' ? 'inline-flex' : 'none';

  renderPage();
}

async function renderPage() {
  const content = document.getElementById('content-area');

  switch (currentPage) {
    case 'dashboard':
      await renderDashboard(content);
      break;
    case 'workflows':
      await renderWorkflows(content);
      break;
    case 'editor':
      renderEditor(content);
      break;
    case 'templates':
      renderTemplates(content);
      break;
    case 'executions':
      await renderExecutions(content);
      break;
  }

  await updateStats();
}

async function renderDashboard(container) {
  const res = await fetch(`${API}/api/stats`);
  const stats = await res.json();

  const recentWf = stats.recent_workflows || [];
  const recentExec = stats.recent_executions || [];

  const statusLabels = { completed: '已完成', running: '运行中', error: '异常', pending: '等待中' };

  let wfRows = '';
  if (recentWf.length > 0) {
    recentWf.forEach(wf => {
      wfRows += `
        <div class="dash-row" onclick="openWorkflow(${wf.id})">
          <div style="display:flex;align-items:center;gap:10px;min-width:0;">
            <div class="dash-avatar">${escapeHtml((wf.name || '?')[0])}</div>
            <div style="min-width:0;">
              <div class="dash-row-title">${escapeHtml(wf.name)}</div>
              <div class="dash-row-sub">${wf.node_count} 个节点 · ${formatDate(wf.updated_at)}</div>
            </div>
          </div>
          <span class="dash-row-arrow">\u203A</span>
        </div>`;
    });
  } else {
    wfRows = '<div class="dash-empty">暂无工作流</div>';
  }

  let execRows = '';
  if (recentExec.length > 0) {
    recentExec.forEach(exec => {
      const label = statusLabels[exec.status] || exec.status;
      execRows += `
        <div class="dash-row" onclick="viewExecution(${exec.id})">
          <div style="min-width:0;">
            <div class="dash-row-title">执行 #${exec.id}</div>
            <div class="dash-row-sub">工作流 ${exec.workflow_id} · ${formatDate(exec.started_at)}</div>
          </div>
          <span class="exec-status ${exec.status}"><span class="exec-status-dot"></span>${label}</span>
        </div>`;
    });
  } else {
    execRows = '<div class="dash-empty">暂无执行记录</div>';
  }

  container.innerHTML = `
    <div class="dashboard">
      <div class="dash-welcome">
        <div>
          <h2 class="dash-welcome-title">AgentFlow</h2>
          <p class="dash-welcome-sub">AI 工作流编排平台 — 创建、编排、执行智能工作流</p>
        </div>
        <div class="dash-quick-actions">
          <button class="btn btn-primary" onclick="showCreateModal()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            新建工作流
          </button>
          <button class="btn" onclick="navigateTo('templates')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
            浏览模板
          </button>
        </div>
      </div>

      <div class="dash-stats-grid">
        <div class="dash-stat-card">
          <div class="dash-stat-icon" style="color:var(--accent);background:var(--accent-subtle);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          </div>
          <div class="dash-stat-value">${stats.workflows || 0}</div>
          <div class="dash-stat-label">工作流</div>
        </div>
        <div class="dash-stat-card">
          <div class="dash-stat-icon" style="color:var(--orange);background:var(--orange-subtle);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          </div>
          <div class="dash-stat-value">${stats.executions || 0}</div>
          <div class="dash-stat-label">执行次数</div>
        </div>
        <div class="dash-stat-card">
          <div class="dash-stat-icon" style="color:#f43f5e;background:rgba(244,63,94,0.08);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
          </div>
          <div class="dash-stat-value">${stats.today_executions || 0}</div>
          <div class="dash-stat-label">今日执行</div>
        </div>
        <div class="dash-stat-card">
          <div class="dash-stat-icon" style="color:var(--green);background:var(--green-subtle);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          </div>
          <div class="dash-stat-value">${stats.success_rate || 0}%</div>
          <div class="dash-stat-label">成功率</div>
        </div>
        <div class="dash-stat-card">
          <div class="dash-stat-icon" style="color:#8b5cf6;background:rgba(139,92,246,0.08);">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
          </div>
          <div class="dash-stat-value">${stats.running_count || 0}</div>
          <div class="dash-stat-label">运行中</div>
        </div>
      </div>

      <div class="dash-grid">
        <div class="dash-section">
          <div class="dash-section-header">
            <h3 class="dash-section-title">最近工作流</h3>
            <button class="btn btn-sm" onclick="navigateTo('workflows')">查看全部</button>
          </div>
          <div class="dash-list">${wfRows}</div>
        </div>
        <div class="dash-section">
          <div class="dash-section-header">
            <h3 class="dash-section-title">最近执行</h3>
            <button class="btn btn-sm" onclick="navigateTo('executions')">查看全部</button>
          </div>
          <div class="dash-list">${execRows}</div>
        </div>
      </div>
    </div>
  `;
}

async function renderWorkflows(container) {
  const res = await fetch(`${API}/api/workflows`);
  workflows = await res.json();

  if (workflows.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${ICONS.workflows}</div>
        <h3 class="empty-title">暂无工作流</h3>
        <p>点击右上角「新建工作流」开始创建</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `<div class="workflow-grid" id="workflow-list"></div>`;
  const list = document.getElementById('workflow-list');

  workflows.forEach(wf => {
    const card = document.createElement('div');
    card.className = 'workflow-card';
    card.innerHTML = `
      <div class="workflow-header">
        <div style="display: flex; align-items: center; min-width: 0;">
          <div class="workflow-avatar">${escapeHtml((wf.name || '?')[0])}</div>
          <div class="workflow-name">${escapeHtml(wf.name)}</div>
        </div>
      </div>
      <div class="workflow-description">${escapeHtml(wf.description || '暂无描述')}</div>
      <div class="workflow-meta">
        <span>${wf.nodes?.length || 0} 个节点</span>
        <span>${wf.edges?.length || 0} 条连线</span>
        <span>${formatDate(wf.updated_at)}</span>
      </div>
      <div class="workflow-actions">
        <button class="btn btn-sm" onclick="openWorkflow(${wf.id})">打开</button>
        <button class="btn btn-sm btn-primary" onclick="executeWorkflow(${wf.id})">执行</button>
        <button class="btn btn-sm btn-danger" onclick="deleteWorkflow(${wf.id})">删除</button>
      </div>
    `;
    list.appendChild(card);
  });
}

function renderEditor(container) {
  container.innerHTML = `
    <div class="editor-layout">
      <div class="node-palette" id="node-palette">
        <div class="palette-header">节点类型</div>
      </div>
      <div class="canvas-container">
        <div class="canvas-toolbar">
          <input type="text" class="property-input" id="quick-decompose" placeholder="输入任务描述，AI 自动拆解为工作流..." style="flex:1;">
          <button class="btn btn-sm btn-primary" onclick="quickDecompose()">AI 分解</button>
          <button class="btn btn-sm" onclick="undo()" title="撤销 (Ctrl+Z)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 105.64-11.36L1 10"/></svg>
          </button>
          <button class="btn btn-sm" onclick="redo()" title="恢复 (Ctrl+Y)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-5.64-11.36L23 10"/></svg>
          </button>
          <button class="btn btn-sm" onclick="checkWorkflow()" title="检查节点与连线">检查</button>
          <button class="btn btn-sm btn-primary" onclick="runWorkflow()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 4 20 12 6 20 6 4"/></svg>
            运行
          </button>
          <button class="btn btn-sm" onclick="showModal('decompose-modal')">高级</button>
        </div>
        <div class="canvas" id="canvas">
          <svg id="svg-layer" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;"></svg>
        </div>
      </div>
      <div class="properties-panel" id="properties-panel">
        <div class="properties-header">属性面板</div>
        <div id="prop-content">
          <p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>
        </div>
      </div>
    </div>
  `;

  initEditor();
}

async function renderExecutions(container) {
  const res = await fetch(`${API}/api/executions`);
  const executions = await res.json();

  if (executions.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">${ICONS.executions}</div>
        <h3 class="empty-title">暂无执行记录</h3>
        <p>执行工作流后会在这里生成日志</p>
      </div>
    `;
    return;
  }

  const statusLabels = {
    completed: '已完成',
    running: '运行中',
    error: '异常',
    pending: '等待中',
  };

  let html = '<div style="display: flex; flex-direction: column; gap: 10px;">';
  executions.forEach((exec, i) => {
    const label = statusLabels[exec.status] || exec.status;
    html += `
      <div class="exec-card" style="animation-delay: ${i * 0.04}s">
        <div style="display: flex; align-items: center; gap: 14px;">
          <div>
            <div style="font-size: 14px; color: var(--text-primary); font-weight: 600;">执行 #${exec.id}</div>
            <div style="font-size: 12px; color: var(--text-tertiary); margin-top: 2px;">工作流 ${exec.workflow_id} · ${formatDate(exec.started_at)}</div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span class="exec-status ${exec.status}">
            <span class="exec-status-dot"></span>
            ${label}
          </span>
          <button class="btn btn-sm" onclick="viewExecution(${exec.id})">查看</button>
        </div>
      </div>
    `;
  });
  html += '</div>';
  container.innerHTML = html;
}

function showCreateModal() {
  document.getElementById('new-workflow-name').value = '';
  document.getElementById('new-workflow-desc').value = '';
  showModal('create-modal');
}

async function createWorkflow() {
  const name = document.getElementById('new-workflow-name').value.trim();
  const description = document.getElementById('new-workflow-desc').value.trim();

  if (!name) {
    showToast('请输入工作流名称', 'error');
    return;
  }

  const res = await fetch(`${API}/api/workflows`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description, nodes: [], edges: [] }),
  });

  if (res.ok) {
    const data = await res.json();
    closeModal('create-modal');
    showToast('工作流创建成功', 'success');
    currentWorkflow = { id: data.id, name, description, nodes: [], edges: [] };
    navigateTo('editor');
  } else {
    showToast('创建失败，请重试', 'error');
  }
}

async function openWorkflow(id) {
  const res = await fetch(`${API}/api/workflows/${id}`);
  if (res.ok) {
    currentWorkflow = await res.json();
    navigateTo('editor');
  }
}

async function deleteWorkflow(id) {
  if (!confirm('确定要删除这个工作流吗？')) return;

  const res = await fetch(`${API}/api/workflows/${id}`, { method: 'DELETE' });
  if (res.ok) {
    showToast('已删除', 'success');
    renderPage();
  }
}

async function executeWorkflow(id) {
  const wf = workflows.find(w => w.id === id);
  openRunModal(id, wf ? wf.name : `工作流 #${id}`);
}

let pendingRun = { workflowId: null, name: '' };

function openRunModal(workflowId, name) {
  pendingRun = { workflowId, name };
  document.getElementById('run-workflow-name').textContent = name || `工作流 #${workflowId}`;
  document.getElementById('run-input').value = '';
  showModal('run-modal');
  setTimeout(() => document.getElementById('run-input').focus(), 60);
}

async function confirmRun() {
  const input = document.getElementById('run-input').value;
  const res = await fetch(`${API}/api/workflows/${pendingRun.workflowId}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: { input } }),
  });

  if (res.ok) {
    const data = await res.json();
    closeModal('run-modal');
    showToast(`已开始执行 #${data.execution_id}`, 'success');
    viewExecution(data.execution_id);
    return;
  }

  let detail = '执行失败，请重试';
  try {
    const body = await res.json();
    if (body.detail) detail = body.detail;
  } catch (e) {}
  showToast(detail, 'error');
}

async function viewExecution(id) {
  const res = await fetch(`${API}/api/executions/${id}`);
  if (!res.ok) return;
  const exec = await res.json();

  const nodeTitles = {};
  try {
    const wfRes = await fetch(`${API}/api/workflows/${exec.workflow_id}`);
    if (wfRes.ok) {
      const wf = await wfRes.json();
      (wf.nodes || []).forEach(n => { nodeTitles[n.id] = n.title || n.type; });
    }
  } catch (e) {}

  showExecutionDetail(exec, nodeTitles);
}

let liveSocket = null;
let livePoller = null;

function stopLive() {
  if (liveSocket) {
    liveSocket.onmessage = null;
    liveSocket.onerror = null;
    try { liveSocket.close(); } catch (e) {}
    liveSocket = null;
  }
  if (livePoller) {
    clearInterval(livePoller);
    livePoller = null;
  }
}

function isFinished(status) {
  return status !== 'running' && status !== 'pending';
}

function watchExecution(exec) {
  stopLive();
  if (isFinished(exec.status)) return;

  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  try {
    liveSocket = new WebSocket(`${proto}//${location.host}/ws/execute/${exec.id}`);
    liveSocket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'log') {
        if (msg.data.status !== 'running') appendLogLine(msg.data);
      } else if (msg.type === 'complete') {
        stopLive();
        viewExecution(exec.id);
      }
    };
    liveSocket.onerror = () => pollExecution(exec.id);
  } catch (e) {
    pollExecution(exec.id);
  }
}

function pollExecution(execId) {
  if (livePoller) return;
  livePoller = setInterval(async () => {
    const res = await fetch(`${API}/api/executions/${execId}`);
    if (!res.ok) return;
    const exec = await res.json();
    if (isFinished(exec.status)) {
      stopLive();
      viewExecution(execId);
    } else {
      renderLogs(exec.logs || []);
    }
  }, 1500);
}

function logLineHtml(log) {
  const color = log.status === 'completed' ? 'var(--green)' : log.status === 'error' ? 'var(--red)' : log.status === 'skipped' ? 'var(--orange)' : 'var(--text-tertiary)';
  const label = { completed: '完成', running: '运行', error: '错误', skipped: '跳过' }[log.status] || log.status;
  return `<div style="display:flex;gap:10px;align-items:baseline;"><span style="color:var(--text-tertiary);font-size:11px;flex-shrink:0;">${formatTime(log.timestamp)}</span><span style="color:${color};font-weight:500;flex-shrink:0;">${label}</span><span style="color:var(--text-secondary);">${escapeHtml(log.message)}</span></div>`;
}

function renderLogs(logs) {
  const box = document.getElementById('exec-logs');
  if (!box) return;
  box.innerHTML = logs.map(logLineHtml).join('');
  box.scrollTop = box.scrollHeight;
}

function appendLogLine(log) {
  const box = document.getElementById('exec-logs');
  if (!box) return;
  const row = document.createElement('div');
  row.innerHTML = logLineHtml(log);
  box.appendChild(row.firstElementChild);
  box.scrollTop = box.scrollHeight;
}

function showExecutionDetail(exec, nodeTitles = {}) {
  const container = document.getElementById('content-area');
  const logs = exec.logs || [];
  const output = exec.output_data || {};

  const statusLabels = {
    completed: '已完成',
    running: '运行中',
    error: '异常',
    pending: '等待中',
  };

  let nodesHtml = '';
  const nodeOutputs = output.nodes || {};
  const entries = Object.entries(nodeOutputs);
  if (entries.length > 0) {
    nodesHtml = `
      <div style="margin-top: 20px;">
        <h3 style="font-size: 14px; color: var(--text-primary); margin-bottom: 10px; font-weight: 600;">各节点输出</h3>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${entries.map(([nodeId, text], i) => `
            <div class="node-output">
              <div class="node-output-title">
                <span class="node-output-index">${i + 1}</span>
                ${escapeHtml(nodeTitles[nodeId] || nodeId)}
                <span class="node-output-id">${escapeHtml(nodeId)}</span>
              </div>
              <div class="node-output-body">${escapeHtml(typeof text === 'string' ? text : JSON.stringify(text, null, 2))}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  const finalBlock = output.error
    ? `<div class="exec-error-box">${escapeHtml(String(output.error))}</div>`
    : `<div class="exec-output-box">${escapeHtml(typeof output.output === 'string' ? output.output : JSON.stringify(output.output, null, 2)) || '（无输出）'}</div>`;

  container.innerHTML = `
    <div style="margin-bottom: 24px;">
      <button class="btn" onclick="navigateTo('executions')" style="margin-bottom: 16px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
        返回
      </button>
      <h2 style="font-size: 20px; color: var(--text-primary); margin-bottom: 10px; font-weight: 700; letter-spacing: -0.3px;">执行 #${exec.id}</h2>
      <div style="display: flex; gap: 16px; font-size: 13px; color: var(--text-secondary); align-items: center;">
        <span class="exec-status ${exec.status}">
          <span class="exec-status-dot"></span>
          ${statusLabels[exec.status] || exec.status}
        </span>
        <span>工作流 ${exec.workflow_id}</span>
        <span>${formatDate(exec.started_at)}</span>
        ${isFinished(exec.status) ? '' : '<span class="live-dot"></span><span style="color: var(--text-tertiary); font-size: 12px;">实时日志</span>'}
      </div>
    </div>
    <div style="margin-bottom: 20px;">
      <h3 style="font-size: 14px; color: var(--text-primary); margin-bottom: 10px; font-weight: 600;">最终输出</h3>
      ${finalBlock}
    </div>
    <div>
      <h3 style="font-size: 14px; color: var(--text-primary); margin-bottom: 10px; font-weight: 600;">执行日志</h3>
      <div id="exec-logs" class="exec-logs">${logs.map(logLineHtml).join('') || '<div style="color:var(--text-tertiary);">暂无日志</div>'}</div>
    </div>
    ${nodesHtml}
  `;

  watchExecution(exec);
}

async function quickDecompose() {
  const input = document.getElementById('quick-decompose');
  const task = input.value.trim();
  if (!task) return;

  input.value = '';
  showToast('AI 正在分解任务...', 'info');

  const res = await fetch(`${API}/api/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });

  if (res.ok) {
    const data = await res.json();
    decomposeSteps = data.steps;
    buildWorkflowFromDecompose(data.steps);
    showToast(`已分解为 ${data.steps.length} 个步骤`, 'success');
  } else {
    showToast('分解失败，请重试', 'error');
  }
}

async function runDecompose() {
  const task = document.getElementById('decompose-input').value.trim();
  if (!task) {
    showToast('请输入任务描述', 'error');
    return;
  }

  const btn = document.getElementById('btn-decompose');
  btn.textContent = '分解中...';
  btn.disabled = true;

  const res = await fetch(`${API}/api/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });

  btn.textContent = '开始分解';
  btn.disabled = false;

  if (res.ok) {
    const data = await res.json();
    decomposeSteps = data.steps;
    renderDecomposeResult(data.steps);
  } else {
    showToast('分解失败，请重试', 'error');
  }
}

function renderDecomposeResult(steps) {
  const container = document.getElementById('decompose-result');
  let html = '<div style="border: 1px solid var(--border); border-radius: var(--radius); padding: 14px;">';
  steps.forEach((step, i) => {
    html += `
      <div style="display: flex; gap: 12px; margin-bottom: ${i < steps.length - 1 ? '12px' : '0'}; ${i < steps.length - 1 ? 'padding-bottom: 12px; border-bottom: 1px solid var(--border);' : ''}">
        <div style="width: 24px; height: 24px; border-radius: 50%; background: var(--accent-subtle); color: var(--accent); font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px;">${step.step}</div>
        <div>
          <div style="color: var(--text-primary); font-size: 13px; margin-bottom: 3px; font-weight: 500;">${escapeHtml(step.title)}</div>
          <div style="color: var(--text-secondary); font-size: 12px; line-height: 1.4;">${escapeHtml(step.description)}</div>
        </div>
      </div>
    `;
  });
  html += '</div>';
  container.innerHTML = html;
  document.getElementById('btn-apply-decompose').style.display = 'inline-flex';
}

function applyDecompose() {
  if (decomposeSteps.length === 0) return;

  if (!currentWorkflow) {
    currentWorkflow = { id: null, name: 'AI 分解工作流', nodes: [], edges: [] };
  }

  buildWorkflowFromDecompose(decomposeSteps);
  closeModal('decompose-modal');
  navigateTo('editor');
  showToast('已应用到编辑器', 'success');
}

function buildWorkflowFromDecompose(steps) {
  if (!currentWorkflow) {
    currentWorkflow = { id: null, name: 'AI 分解工作流', nodes: [], edges: [] };
  }

  const nodes = [];
  const edges = [];

  nodes.push({
    id: 'start',
    type: 'start',
    title: '开始',
    x: 100,
    y: 200,
    config: {},
  });

  let prevId = 'start';
  let x = 320;

  steps.forEach((step, i) => {
    const nodeId = `step_${i}`;
    const type = nodeTypes[step.type] ? step.type : 'llm';
    const defaults = (nodeTypes[type] && nodeTypes[type].config) || { prompt: '', model: 'qwen-plus', temperature: 0.7 };
    const config = JSON.parse(JSON.stringify(defaults));
    if (type === 'llm' || type === 'loop') {
      config.prompt = step.description || config.prompt;
    }

    nodes.push({
      id: nodeId,
      type,
      title: step.title,
      x: x,
      y: 200,
      config,
    });

    edges.push({ source: prevId, target: nodeId, sourcePort: 'output' });
    prevId = nodeId;
    x += 220;
  });

  nodes.push({
    id: 'end',
    type: 'end',
    title: '结束',
    x: x,
    y: 200,
    config: {},
  });

  edges.push({ source: prevId, target: 'end', sourcePort: 'output' });

  currentWorkflow.nodes = nodes;
  currentWorkflow.edges = edges;

  if (currentPage === 'editor') {
    renderCanvas();
  }
}

function showModal(id) {
  document.getElementById(id).classList.add('active');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('active');
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

async function updateStats() {
  try {
    const res = await fetch(`${API}/api/stats`);
    const stats = await res.json();
    document.getElementById('stat-workflows').textContent = stats.workflows || 0;
    document.getElementById('stat-executions').textContent = stats.executions || 0;
  } catch (e) {}
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = typeof text === 'string' ? text : JSON.stringify(text, null, 2);
  return div.innerHTML;
}

function escapeAttr(value) {
  if (value === undefined || value === null) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatDate(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatTime(dateStr) {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

let deferredPrompt = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const btn = document.getElementById('btn-install');
  if (btn) btn.style.display = 'inline-flex';
});

function installApp() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then((choice) => {
    if (choice.outcome === 'accepted') {
      showToast('已安装 AgentFlow', 'success');
    }
    deferredPrompt = null;
    const btn = document.getElementById('btn-install');
    if (btn) btn.style.display = 'none';
  });
}

window.addEventListener('appinstalled', () => {
  deferredPrompt = null;
  const btn = document.getElementById('btn-install');
  if (btn) btn.style.display = 'none';
});

function registerSW() {
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((reg) => {
    if (reg.waiting) {
      showUpdateToast();
    }

    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
          showUpdateToast();
        }
      });
    });
  });

  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload();
  });
}

function showUpdateToast() {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'toast info';
  toast.innerHTML = '<span style="flex:1">发现新版本</span><button onclick="applyUpdate()" style="background:rgba(255,255,255,0.2);border:none;color:white;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:500;">更新</button>';
  container.appendChild(toast);
}

function applyUpdate() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistration().then((reg) => {
      if (reg && reg.waiting) {
        reg.waiting.postMessage({ type: 'SKIP_WAITING' });
      }
    });
  }
}

window.addEventListener('online', () => showToast('已恢复网络连接', 'success'));
window.addEventListener('offline', () => showToast('当前处于离线模式', 'error'));

document.addEventListener('DOMContentLoaded', () => {
  registerSW();
  navigateTo('dashboard');
});
