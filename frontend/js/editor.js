let editorNodes = [];
let editorEdges = [];
let selectedNode = null;
let draggingNode = null;
let dragOffset = { x: 0, y: 0 };
let connectingPort = null;
let nodeTypes = {};
let history = [];
let historyIndex = -1;
const MAX_HISTORY = 50;

function pushHistory() {
  const state = {
    nodes: JSON.parse(JSON.stringify(editorNodes)),
    edges: JSON.parse(JSON.stringify(editorEdges)),
  };
  history = history.slice(0, historyIndex + 1);
  history.push(state);
  if (history.length > MAX_HISTORY) history.shift();
  historyIndex = history.length - 1;
}

function undo() {
  if (historyIndex <= 0) return;
  historyIndex--;
  const state = history[historyIndex];
  editorNodes = JSON.parse(JSON.stringify(state.nodes));
  editorEdges = JSON.parse(JSON.stringify(state.edges));
  selectedNode = null;
  renderCanvas();
  saveWorkflow();
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
}

function redo() {
  if (historyIndex >= history.length - 1) return;
  historyIndex++;
  const state = history[historyIndex];
  editorNodes = JSON.parse(JSON.stringify(state.nodes));
  editorEdges = JSON.parse(JSON.stringify(state.edges));
  selectedNode = null;
  renderCanvas();
  saveWorkflow();
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
    e.preventDefault();
    undo();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) {
    e.preventDefault();
    redo();
  }
});

async function initEditor() {
  const res = await fetch(`${API}/api/node-types`);
  nodeTypes = await res.json();
  renderPalette();

  if (currentWorkflow) {
    editorNodes = JSON.parse(JSON.stringify(currentWorkflow.nodes || []));
    editorEdges = JSON.parse(JSON.stringify(currentWorkflow.edges || []));
  } else {
    editorNodes = [];
    editorEdges = [];
  }

  renderCanvas();
  setupCanvasEvents();
  pushHistory();
}

function renderPalette() {
  const palette = document.getElementById('node-palette');
  if (!palette) return;

  palette.innerHTML = '<div class="palette-header">节点类型</div>';

  Object.entries(nodeTypes).forEach(([type, info]) => {
    const el = document.createElement('div');
    el.className = 'node-type-item';
    el.draggable = true;
    el.innerHTML = `
      <span class="node-type-icon" style="color: ${info.color}; background: ${info.color}14;">${info.icon}</span>
      <span>${info.label}</span>
    `;
    el.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('node-type', type);
    });
    palette.appendChild(el);
  });
}

function renderCanvas() {
  const canvas = document.getElementById('canvas');
  const svg = document.getElementById('svg-layer');
  if (!canvas || !svg) return;

  canvas.querySelectorAll('.workflow-node').forEach(n => n.remove());

  editorNodes.forEach(node => {
    const el = createNodeElement(node);
    canvas.appendChild(el);
  });

  renderEdges(svg);
}

function createNodeElement(node) {
  const info = nodeTypes[node.type] || { label: node.type, color: '#888', icon: '', inputs: [], outputs: [] };
  const el = document.createElement('div');
  el.className = 'workflow-node';
  el.dataset.id = node.id;
  el.style.left = node.x + 'px';
  el.style.top = node.y + 'px';
  el.style.setProperty('--node-color', info.color);

  const hasInput = info.inputs && info.inputs.length > 0;
  const outputs = (info.outputs && info.outputs.length) ? info.outputs : [];

  const configHint = node.config?.model ? node.config.model.replace('qwen-', 'Qwen ') : '';

  const outPorts = outputs.map(port => `
    <div class="port-slot">
      ${port === 'output' ? '' : `<span class="port-label ${port}">${port === 'true' ? '是' : '否'}</span>`}
      <div class="node-port" data-node="${node.id}" data-kind="output" data-port="${port}"></div>
    </div>
  `).join('');

  el.innerHTML = `
    <div class="node-header">
      <span class="node-icon" style="color: ${info.color}; background: ${info.color}14; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border-radius: 7px; font-size: 14px;">${info.icon}</span>
      <span style="flex:1;">${escapeHtml(node.title || info.label)}</span>
    </div>
    ${configHint ? `<div class="node-body">${configHint}</div>` : ''}
    <div class="node-ports">
      ${hasInput ? '<div class="port-group"><div class="port-slot"><div class="node-port" data-node="' + node.id + '" data-kind="input" data-port="input"></div></div></div>' : '<div></div>'}
      ${outPorts ? `<div class="port-group">${outPorts}</div>` : '<div></div>'}
    </div>
  `;

  el.addEventListener('mousedown', (e) => {
    if (e.target.classList.contains('node-port')) return;
    draggingNode = node;
    const rect = el.getBoundingClientRect();
    dragOffset.x = e.clientX - rect.left;
    dragOffset.y = e.clientY - rect.top;
    selectNode(node.id);
    e.preventDefault();
  });

  el.querySelectorAll('.node-port').forEach(port => {
    port.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      const nodeId = port.dataset.node;
      const kind = port.dataset.kind;
      const portName = port.dataset.port;

      if (!connectingPort) {
        connectingPort = { nodeId, kind, portName };
        port.classList.add('connecting');
        return;
      }

      if (connectingPort.nodeId !== nodeId && connectingPort.kind !== kind) {
        const out = connectingPort.kind === 'output' ? connectingPort : { nodeId, kind, portName };
        const source = out.nodeId;
        const target = connectingPort.kind === 'output' ? nodeId : connectingPort.nodeId;
        const sourcePort = out.portName;

        const exists = editorEdges.some(
          edge => edge.source === source && edge.target === target && (edge.sourcePort || 'output') === sourcePort
        );
        if (!exists) {
          pushHistory();
          editorEdges.push({ source, target, sourcePort });
          renderCanvas();
          saveWorkflow();
        }
      } else if (connectingPort.nodeId === nodeId) {
        showToast('不能连接节点自身', 'error');
      } else {
        showToast('请从输出端口连到另一个节点的输入端口', 'error');
      }

      connectingPort = null;
      document.querySelectorAll('.node-port.connecting').forEach(p => p.classList.remove('connecting'));
    });
  });

  if (selectedNode === node.id) {
    el.classList.add('selected');
  }

  return el;
}

function portAnchor(nodeEl, kind, portName) {
  const sel = `.node-port[data-kind="${kind}"][data-port="${portName}"]`;
  const portEl = nodeEl.querySelector(sel) || nodeEl.querySelector(`.node-port[data-kind="${kind}"]`);
  if (!portEl) return null;
  const r = portEl.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

function renderEdges(svg) {
  svg.innerHTML = '';

  editorEdges.forEach((edge, i) => {
    const sourceNode = editorNodes.find(n => n.id === edge.source);
    const targetNode = editorNodes.find(n => n.id === edge.target);
    if (!sourceNode || !targetNode) return;

    const sourceEl = document.querySelector(`.workflow-node[data-id="${edge.source}"]`);
    const targetEl = document.querySelector(`.workflow-node[data-id="${edge.target}"]`);
    if (!sourceEl || !targetEl) return;

    const canvasRect = svg.parentElement.getBoundingClientRect();
    const out = portAnchor(sourceEl, 'output', edge.sourcePort || 'output');
    const inn = portAnchor(targetEl, 'input', 'input');
    if (!out || !inn) return;

    const x1 = out.x - canvasRect.left;
    const y1 = out.y - canvasRect.top;
    const x2 = inn.x - canvasRect.left;
    const y2 = inn.y - canvasRect.top;

    const dx = Math.max(40, Math.abs(x2 - x1) / 2);
    const path = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;

    const branchClass = edge.sourcePort === 'true' || edge.sourcePort === 'false' ? ` edge-${edge.sourcePort}` : '';

    const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    pathEl.setAttribute('d', path);
    pathEl.setAttribute('class', `edge${branchClass}`);
    pathEl.dataset.index = i;

    pathEl.addEventListener('click', () => {
      pushHistory();
      editorEdges.splice(i, 1);
      renderCanvas();
      saveWorkflow();
      showToast('已删除连线', 'success');
    });

    svg.appendChild(pathEl);

    const flowEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    flowEl.setAttribute('d', path);
    flowEl.setAttribute('class', `edge-flow${branchClass}`);
    svg.appendChild(flowEl);
  });
}

function setupCanvasEvents() {
  const canvas = document.getElementById('canvas');
  if (!canvas) return;

  canvas.addEventListener('dragover', (e) => {
    e.preventDefault();
  });

  canvas.addEventListener('drop', (e) => {
    e.preventDefault();
    const type = e.dataTransfer.getData('node-type');
    if (!type) return;

    const canvasRect = canvas.getBoundingClientRect();
    const x = e.clientX - canvasRect.left - 80;
    const y = e.clientY - canvasRect.top - 30;

    const info = nodeTypes[type];
    const node = {
      id: `${type}_${Date.now()}`,
      type,
      title: info.label,
      x: Math.max(0, x),
      y: Math.max(0, y),
      config: JSON.parse(JSON.stringify(info.config || {})),
    };

    editorNodes.push(node);
    pushHistory();
    renderCanvas();
    saveWorkflow();
  });

  canvas.addEventListener('click', (e) => {
    if (e.target === canvas || e.target.id === 'svg-layer') {
      selectedNode = null;
      document.querySelectorAll('.workflow-node').forEach(n => n.classList.remove('selected'));
      document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
    }
  });
}

document.addEventListener('mousemove', (e) => {
  if (!draggingNode) return;

  const canvas = document.getElementById('canvas');
  if (!canvas) return;
  const canvasRect = canvas.getBoundingClientRect();
  const x = e.clientX - canvasRect.left - dragOffset.x;
  const y = e.clientY - canvasRect.top - dragOffset.y;

  draggingNode.x = Math.max(0, x);
  draggingNode.y = Math.max(0, y);

  const el = document.querySelector(`.workflow-node[data-id="${draggingNode.id}"]`);
  if (el) {
    el.style.left = draggingNode.x + 'px';
    el.style.top = draggingNode.y + 'px';
  }

  renderEdges(document.getElementById('svg-layer'));
});

document.addEventListener('mouseup', () => {
  if (draggingNode) {
    pushHistory();
    saveWorkflow();
  }
  draggingNode = null;
});

function selectNode(nodeId) {
  selectedNode = nodeId;
  document.querySelectorAll('.workflow-node').forEach(n => n.classList.remove('selected'));
  const el = document.querySelector(`.workflow-node[data-id="${nodeId}"]`);
  if (el) el.classList.add('selected');

  const node = editorNodes.find(n => n.id === nodeId);
  if (!node) return;

  const info = nodeTypes[node.type] || {};
  const panel = document.getElementById('prop-content');

  let html = `
    <div class="property-group">
      <label class="property-label">节点 ID</label>
      <input type="text" class="property-input" value="${node.id}" disabled style="opacity: 0.5;">
    </div>
    <div class="property-group">
      <label class="property-label">标题</label>
      <input type="text" class="property-input" id="prop-title" value="${escapeHtml(node.title || '')}" oninput="updateNodeProp('${nodeId}', 'title', this.value)">
    </div>
    <div class="property-group">
      <label class="property-label">类型</label>
      <input type="text" class="property-input" value="${info.label || node.type}" disabled style="opacity: 0.5;">
    </div>
  `;

  if (node.config) {
    if (node.config.prompt !== undefined) {
      const promptLabel = node.config.source !== undefined
        ? '每项提示词（{{item}} / {{index}}）'
        : '提示词';
      html += `
        <div class="property-group">
          <label class="property-label">${promptLabel}</label>
          <textarea class="property-textarea" oninput="updateNodeConfig('${nodeId}', 'prompt', this.value)">${escapeHtml(node.config.prompt)}</textarea>
        </div>
      `;
    }
    if (node.config.model !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">模型</label>
          <select class="property-select" id="prop-model" onchange="updateNodeConfig('${nodeId}', 'model', this.value)">
            <option value="qwen-turbo" ${node.config.model === 'qwen-turbo' ? 'selected' : ''}>Qwen Turbo（快速）</option>
            <option value="qwen-plus" ${node.config.model === 'qwen-plus' ? 'selected' : ''}>Qwen Plus（均衡）</option>
            <option value="qwen-max" ${node.config.model === 'qwen-max' ? 'selected' : ''}>Qwen Max（强力）</option>
          </select>
        </div>
      `;
    }
    if (node.config.temperature !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">温度：${node.config.temperature}</label>
          <input type="range" class="property-input" min="0" max="1" step="0.1" value="${node.config.temperature}"
            oninput="updateNodeConfig('${nodeId}', 'temperature', parseFloat(this.value)); this.previousElementSibling.textContent = '温度：' + this.value">
        </div>
      `;
    }
    if (node.config.url !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">请求地址</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.url)}" oninput="updateNodeConfig('${nodeId}', 'url', this.value)">
        </div>
      `;
    }
    if (node.config.method !== undefined) {
      const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
      html += `
        <div class="property-group">
          <label class="property-label">请求方法</label>
          <select class="property-select" onchange="updateNodeConfig('${nodeId}', 'method', this.value)">
            ${methods.map(m => `<option value="${m}" ${node.config.method === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">请求头（JSON）</label>
          <textarea class="property-textarea property-mono" oninput="updateNodeJson('${nodeId}', 'headers', this.value)">${escapeHtml(JSON.stringify(node.config.headers ?? {}, null, 2))}</textarea>
        </div>
        ${node.config.method === 'GET' ? '' : `
        <div class="property-group">
          <label class="property-label">请求体</label>
          <textarea class="property-textarea property-mono" placeholder='{"key": "{{input}}"}' oninput="updateNodeConfig('${nodeId}', 'body', this.value)">${escapeHtml(node.config.body ?? '')}</textarea>
        </div>`}
        <label class="property-check">
          <input type="checkbox" ${node.config.fail_on_error !== false ? 'checked' : ''} onchange="updateNodeConfig('${nodeId}', 'fail_on_error', this.checked)">
          <span>4xx / 5xx 视为执行失败</span>
        </label>
      `;
    }
    if (node.config.condition !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">条件表达式</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.condition)}" oninput="updateNodeConfig('${nodeId}', 'condition', this.value)">
          <div class="property-hint">支持 <code>==</code> <code>!=</code> <code>&gt;</code> <code>&gt;=</code> <code>contains</code> <code>and</code> <code>or</code>，变量直接写 ID，如 <code>llm_1 contains "投诉"</code>。结果走「是 / 否」两个出口。</div>
        </div>
      `;
    }
    if (node.config.operation !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">处理方式</label>
          <select class="property-select" onchange="updateNodeConfig('${nodeId}', 'operation', this.value)">
            ${['concat', 'split', 'replace'].map(op => `<option value="${op}" ${node.config.operation === op ? 'selected' : ''}>${{ concat: '拼接文本', split: '拆分为列表', replace: '查找替换' }[op]}</option>`).join('')}
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">文本片段（JSON 数组）</label>
          <textarea class="property-textarea property-mono" oninput="updateNodeJson('${nodeId}', 'texts', this.value)">${escapeHtml(JSON.stringify(node.config.texts ?? [], null, 2))}</textarea>
        </div>
        ${node.config.operation === 'split' ? `
        <div class="property-group">
          <label class="property-label">分隔符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.separator ?? '\\n')}" oninput="updateNodeConfig('${nodeId}', 'separator', this.value)">
        </div>` : ''}
        ${node.config.operation === 'replace' ? `
        <div class="property-group">
          <label class="property-label">查找</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.old ?? '')}" oninput="updateNodeConfig('${nodeId}', 'old', this.value)">
        </div>
        <div class="property-group">
          <label class="property-label">替换为</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.new ?? '')}" oninput="updateNodeConfig('${nodeId}', 'new', this.value)">
        </div>` : ''}
      `;
    }
    if (node.config.source !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">列表来源</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.source)}" oninput="updateNodeConfig('${nodeId}', 'source', this.value)">
          <div class="property-hint">可写 <code>{{input}}</code> 或上游节点 ID；JSON 数组会自动识别，否则按分隔符拆分。</div>
        </div>
        <div class="property-group">
          <label class="property-label">分隔符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.separator ?? '\\n')}" oninput="updateNodeConfig('${nodeId}', 'separator', this.value)">
        </div>
        <div class="property-group">
          <label class="property-label">每项动作</label>
          <select class="property-select" onchange="updateNodeConfig('${nodeId}', 'action', this.value)">
            <option value="llm" ${node.config.action === 'llm' ? 'selected' : ''}>调用大模型</option>
            <option value="collect" ${node.config.action === 'collect' ? 'selected' : ''}>仅收集原项</option>
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">最多处理条数</label>
          <input type="number" class="property-input" min="1" max="100" value="${Number(node.config.max_items ?? 20)}" oninput="updateNodeConfig('${nodeId}', 'max_items', parseInt(this.value, 10))">
        </div>
        <div class="property-group">
          <label class="property-label">结果连接符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.join ?? '\\n\\n')}" oninput="updateNodeConfig('${nodeId}', 'join', this.value)">
        </div>
      `;
    }
  }

  html += `
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border);">
      <button class="btn btn-danger" onclick="deleteNode('${nodeId}')" style="width: 100%;">删除节点</button>
    </div>
  `;

  panel.innerHTML = html;
}

function updateNodeProp(nodeId, prop, value) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (node) {
    node[prop] = value;
    renderCanvas();
    saveWorkflow();
  }
}

function updateNodeConfig(nodeId, key, value) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (node) {
    node.config[key] = value;
    saveWorkflow();
  }
}

function updateNodeJson(nodeId, key, raw) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (!node) return;
  try {
    node.config[key] = JSON.parse(raw);
  } catch (e) {
    return;
  }
  saveWorkflow();
}

function deleteNode(nodeId) {
  pushHistory();
  editorNodes = editorNodes.filter(n => n.id !== nodeId);
  editorEdges = editorEdges.filter(e => e.source !== nodeId && e.target !== nodeId);
  selectedNode = null;
  renderCanvas();
  saveWorkflow();
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
}

async function checkWorkflow() {
  const res = await fetch(`${API}/api/workflows/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes: editorNodes, edges: editorEdges }),
  });
  if (!res.ok) {
    showToast('检查失败，请重试', 'error');
    return false;
  }
  const data = await res.json();
  if (data.valid) {
    showToast('检查通过，可以直接运行', 'success');
    return true;
  }
  showToast(data.problems.join('；'), 'error');
  return false;
}

async function runWorkflow() {
  if (editorNodes.length === 0) {
    showToast('画布为空，请先拖入节点', 'error');
    return;
  }
  if (!(await checkWorkflow())) return;

  if (!currentWorkflow) {
    currentWorkflow = { id: null, name: '未命名工作流', description: '', nodes: [], edges: [] };
  }
  await saveWorkflow();
  if (!currentWorkflow.id) {
    showToast('保存失败，无法执行', 'error');
    return;
  }
  openRunModal(currentWorkflow.id, currentWorkflow.name);
}

async function saveWorkflow() {
  if (!currentWorkflow) return;

  const data = {
    nodes: editorNodes,
    edges: editorEdges,
  };

  if (currentWorkflow.id) {
    await fetch(`${API}/api/workflows/${currentWorkflow.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  } else {
    const res = await fetch(`${API}/api/workflows`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: currentWorkflow.name || '未命名工作流',
        description: currentWorkflow.description || '',
        nodes: editorNodes,
        edges: editorEdges,
      }),
    });
    if (res.ok) {
      const wf = await res.json();
      currentWorkflow.id = wf.id;
    }
  }
}
