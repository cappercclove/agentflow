const API = '';
let currentPage = 'workflows';
let currentWorkflow = null;
let workflows = [];
let decomposeSteps = [];

function navigateTo(page) {
  currentPage = page;
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`[data-page="${page}"]`).classList.add('active');

  const titles = {
    workflows: '// WORKFLOWS',
    editor: '// EDITOR',
    templates: '// TEMPLATES',
    executions: '// EXECUTIONS',
  };
  document.getElementById('page-title').textContent = titles[page] || page;

  const btnNew = document.getElementById('btn-new-workflow');
  btnNew.style.display = page === 'workflows' ? 'inline-flex' : 'none';

  renderPage();
}

async function renderPage() {
  const content = document.getElementById('content-area');

  switch (currentPage) {
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

async function renderWorkflows(container) {
  const res = await fetch(`${API}/api/workflows`);
  workflows = await res.json();

  if (workflows.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon"></div>
        <h3 class="empty-title">NO_WORKFLOWS_FOUND</h3>
        <p>> EXECUTE "NEW_WORKFLOW" TO INITIALIZE</p>
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
        <div class="workflow-name">${escapeHtml(wf.name)}</div>
      </div>
      <div class="workflow-description">${escapeHtml(wf.description || 'NO_DESCRIPTION')}</div>
      <div class="workflow-meta">
        <span>${wf.nodes?.length || 0}_NODES</span>
        <span>${wf.edges?.length || 0}_EDGES</span>
        <span>${formatDate(wf.updated_at)}</span>
      </div>
      <div class="workflow-actions">
        <button class="btn btn-sm" onclick="openWorkflow(${wf.id})">OPEN</button>
        <button class="btn btn-sm btn-primary" onclick="executeWorkflow(${wf.id})">EXECUTE</button>
        <button class="btn btn-sm btn-danger" onclick="deleteWorkflow(${wf.id})">DELETE</button>
      </div>
    `;
    list.appendChild(card);
  });
}

function renderEditor(container) {
  container.innerHTML = `
    <div class="editor-layout">
      <div class="node-palette" id="node-palette">
        <div class="palette-header">> NODE_TYPES</div>
      </div>
      <div class="canvas-container">
        <div style="padding: 12px; border-bottom: 1px solid var(--accent-cyan); display: flex; gap: 12px; align-items: center;">
          <input type="text" class="property-input" id="quick-decompose" placeholder="> ENTER_TASK_FOR_AI_DECOMPOSE..." style="flex:1;">
          <button class="btn btn-sm btn-primary" onclick="quickDecompose()">DECOMPOSE</button>
          <button class="btn btn-sm" onclick="showModal('decompose-modal')">ADVANCED</button>
        </div>
        <div class="canvas" id="canvas">
          <svg id="svg-layer" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;"></svg>
        </div>
      </div>
      <div class="properties-panel" id="properties-panel">
        <div class="properties-header">> PROPERTIES</div>
        <div id="prop-content">
          <p style="font-size: 12px; color: var(--text-muted);">> SELECT_NODE_TO_INSPECT</p>
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
        <div class="empty-icon"></div>
        <h3 class="empty-title">NO_EXECUTIONS</h3>
        <p>> EXECUTE_WORKFLOW TO_GENERATE_LOGS</p>
      </div>
    `;
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 12px;">';
  executions.forEach(exec => {
    const statusColors = {
      completed: 'var(--accent-cyan)',
      running: 'var(--accent-yellow)',
      error: 'var(--accent-red)',
      pending: 'var(--text-muted)',
    };
    const color = statusColors[exec.status] || 'var(--text-muted)';
    html += `
      <div class="workflow-card" style="display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="width: 10px; height: 10px; background: ${color}; box-shadow: 0 0 10px ${color};"></div>
          <div>
            <div style="font-size: 14px; color: var(--accent-cyan);">EXECUTION#${exec.id}</div>
            <div style="font-size: 11px; color: var(--text-muted);">WF_ID:${exec.workflow_id} // ${formatDate(exec.started_at)}</div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span style="font-size: 11px; padding: 4px 10px; border: 1px solid ${color}; color: ${color}; text-transform: uppercase; letter-spacing: 1px;">${exec.status}</span>
          <button class="btn btn-sm" onclick="viewExecution(${exec.id})">INSPECT</button>
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
    showToast('> ERROR: NAME_REQUIRED', 'error');
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
    showToast('> WORKFLOW_CREATED_SUCCESSFULLY', 'success');
    currentWorkflow = { id: data.id, name, description, nodes: [], edges: [] };
    navigateTo('editor');
  } else {
    showToast('> ERROR: CREATION_FAILED', 'error');
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
  if (!confirm('> CONFIRM_DELETE?')) return;

  const res = await fetch(`${API}/api/workflows/${id}`, { method: 'DELETE' });
  if (res.ok) {
    showToast('> WORKFLOW_DELETED', 'success');
    renderPage();
  }
}

async function executeWorkflow(id) {
  const res = await fetch(`${API}/api/workflows/${id}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input: {} }),
  });

  if (res.ok) {
    const data = await res.json();
    showToast(`> EXECUTION_STARTED (ID: ${data.execution_id})`, 'success');
    navigateTo('executions');
  } else {
    showToast('> ERROR: EXECUTION_FAILED', 'error');
  }
}

async function viewExecution(id) {
  const res = await fetch(`${API}/api/executions/${id}`);
  if (res.ok) {
    const exec = await res.json();
    showExecutionDetail(exec);
  }
}

function showExecutionDetail(exec) {
  const container = document.getElementById('content-area');
  const logs = exec.logs || [];

  let logsHtml = '';
  if (logs.length > 0) {
    logsHtml = '<div style="background: var(--bg-card); border: 1px solid var(--accent-cyan); padding: 16px; font-family: monospace; font-size: 12px; max-height: 400px; overflow-y: auto;">';
    logs.forEach(log => {
      const color = log.status === 'success' ? 'var(--accent-cyan)' : log.status === 'error' ? 'var(--accent-red)' : 'var(--text-muted)';
      logsHtml += `<div style="margin-bottom: 8px;"><span style="color: var(--text-muted);">[${formatTime(log.timestamp)}]</span> <span style="color: ${color};">${log.status.toUpperCase()}</span> ${escapeHtml(log.message)}</div>`;
    });
    logsHtml += '</div>';
  }

  container.innerHTML = `
    <div style="margin-bottom: 20px;">
      <button class="btn" onclick="navigateTo('executions')" style="margin-bottom: 16px;">< BACK</button>
      <h2 style="font-size: 20px; color: var(--accent-cyan); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 2px;">EXECUTION#${exec.id}</h2>
      <div style="display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary);">
        <span>STATUS: <strong style="color: ${exec.status === 'completed' ? 'var(--accent-cyan)' : exec.status === 'error' ? 'var(--accent-red)' : 'var(--accent-yellow)'}">${exec.status.toUpperCase()}</strong></span>
        <span>WF_ID: ${exec.workflow_id}</span>
        <span>STARTED: ${formatDate(exec.started_at)}</span>
      </div>
    </div>
    ${logsHtml}
    <div style="margin-top: 20px;">
      <h3 style="font-size: 14px; color: var(--accent-cyan); margin-bottom: 8px; text-transform: uppercase;">> OUTPUT_DATA</h3>
      <div style="background: var(--bg-card); border: 1px solid var(--accent-cyan); padding: 16px; font-family: monospace; font-size: 12px; white-space: pre-wrap; max-height: 200px; overflow-y: auto;">
        ${escapeHtml(JSON.stringify(exec.output_data, null, 2))}
      </div>
    </div>
  `;
}

async function quickDecompose() {
  const input = document.getElementById('quick-decompose');
  const task = input.value.trim();
  if (!task) return;

  input.value = '';
  showToast('> AI_DECOMPOSING...', 'info');

  const res = await fetch(`${API}/api/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });

  if (res.ok) {
    const data = await res.json();
    decomposeSteps = data.steps;
    buildWorkflowFromDecompose(data.steps);
    showToast(`> DECOMPOSED_INTO_${data.steps.length}_STEPS`, 'success');
  } else {
    showToast('> ERROR: DECOMPOSE_FAILED', 'error');
  }
}

async function runDecompose() {
  const task = document.getElementById('decompose-input').value.trim();
  if (!task) {
    showToast('> ERROR: INPUT_REQUIRED', 'error');
    return;
  }

  const btn = document.getElementById('btn-decompose');
  btn.textContent = '> PROCESSING...';
  btn.disabled = true;

  const res = await fetch(`${API}/api/decompose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });

  btn.textContent = '> INITIATE_DECOMPOSE';
  btn.disabled = false;

  if (res.ok) {
    const data = await res.json();
    decomposeSteps = data.steps;
    renderDecomposeResult(data.steps);
  } else {
    showToast('> ERROR: DECOMPOSE_FAILED', 'error');
  }
}

function renderDecomposeResult(steps) {
  const container = document.getElementById('decompose-result');
  let html = '<div style="border: 1px solid var(--accent-cyan); padding: 12px;">';
  steps.forEach((step, i) => {
    html += `
      <div style="display: flex; gap: 12px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid rgba(0,255,255,0.2);">
        <div style="color: var(--accent-magenta); font-size: 14px; min-width: 30px;">[${step.step}]</div>
        <div>
          <div style="color: var(--accent-cyan); font-size: 13px; margin-bottom: 4px;">${escapeHtml(step.title)}</div>
          <div style="color: var(--text-secondary); font-size: 11px;">${escapeHtml(step.description)}</div>
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
    currentWorkflow = { id: null, name: 'AI_Decomposed_Workflow', nodes: [], edges: [] };
  }

  buildWorkflowFromDecompose(decomposeSteps);
  closeModal('decompose-modal');
  navigateTo('editor');
  showToast('> APPLIED_TO_EDITOR', 'success');
}

function buildWorkflowFromDecompose(steps) {
  if (!currentWorkflow) {
    currentWorkflow = { id: null, name: 'AI_Decomposed_Workflow', nodes: [], edges: [] };
  }

  const nodes = [];
  const edges = [];

  nodes.push({
    id: 'start',
    type: 'start',
    title: 'START',
    x: 100,
    y: 200,
    config: {},
  });

  let prevId = 'start';
  let x = 320;

  steps.forEach((step, i) => {
    const nodeId = `step_${i}`;
    nodes.push({
      id: nodeId,
      type: step.type || 'llm',
      title: step.title,
      x: x,
      y: 200,
      config: {
        prompt: step.description || step.input || '',
        model: 'qwen-plus',
        temperature: 0.7,
      },
    });

    edges.push({ source: prevId, target: nodeId });
    prevId = nodeId;
    x += 220;
  });

  nodes.push({
    id: 'end',
    type: 'end',
    title: 'END',
    x: x,
    y: 200,
    config: {},
  });

  edges.push({ source: prevId, target: 'end' });

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
  toast.innerHTML = `<span>${type === 'success' ? '>' : type === 'error' ? '!' : '*'}</span> ${escapeHtml(message)}`;
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
  div.textContent = text;
  return div.innerHTML;
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

document.addEventListener('DOMContentLoaded', () => {
  navigateTo('workflows');
});
