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
  const hasOutput = info.outputs && info.outputs.length > 0;

  const configHint = node.config?.model ? node.config.model.replace('qwen-', 'Qwen ') : '';

  el.innerHTML = `
    <div class="node-header">
      <span class="node-icon" style="color: ${info.color}; background: ${info.color}14; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border-radius: 7px; font-size: 14px;">${info.icon}</span>
      <span style="flex:1;">${escapeHtml(node.title || info.label)}</span>
    </div>
    ${configHint ? `<div class="node-body">${configHint}</div>` : ''}
    <div class="node-ports">
      ${hasInput ? '<div class="node-port" data-node="' + node.id + '" data-port="input"></div>' : '<div></div>'}
      ${hasOutput ? '<div class="node-port" data-node="' + node.id + '" data-port="output"></div>' : '<div></div>'}
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
      const portType = port.dataset.port;

      if (!connectingPort) {
        connectingPort = { nodeId, portType };
        const nodeColor = el.style.getPropertyValue('--node-color');
        port.style.background = nodeColor;
      } else {
        if (connectingPort.nodeId !== nodeId && connectingPort.portType !== portType) {
          const source = connectingPort.portType === 'output' ? connectingPort.nodeId : nodeId;
          const target = connectingPort.portType === 'input' ? connectingPort.nodeId : nodeId;

          const exists = editorEdges.some(e => e.source === source && e.target === target);
          if (!exists) {
            pushHistory();
            editorEdges.push({ source, target });
            renderCanvas();
            saveWorkflow();
          }
        }
        connectingPort = null;
        el.querySelectorAll('.node-port').forEach(p => p.style.background = '');
      }
    });
  });

  if (selectedNode === node.id) {
    el.classList.add('selected');
  }

  return el;
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
    const sRect = sourceEl.getBoundingClientRect();
    const tRect = targetEl.getBoundingClientRect();

    const x1 = sRect.right - canvasRect.left;
    const y1 = sRect.top + sRect.height / 2 - canvasRect.top;
    const x2 = tRect.left - canvasRect.left;
    const y2 = tRect.top + tRect.height / 2 - canvasRect.top;

    const midX = (x1 + x2) / 2;
    const path = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;

    const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    pathEl.setAttribute('d', path);
    pathEl.setAttribute('class', 'edge');
    pathEl.dataset.index = i;

    pathEl.addEventListener('click', () => {
      pushHistory();
      editorEdges.splice(i, 1);
      renderCanvas();
      saveWorkflow();
    });

    svg.appendChild(pathEl);

    const flowEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    flowEl.setAttribute('d', path);
    flowEl.setAttribute('class', 'edge-flow');
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
      html += `
        <div class="property-group">
          <label class="property-label">提示词</label>
          <textarea class="property-textarea" id="prop-prompt" oninput="updateNodeConfig('${nodeId}', 'prompt', this.value)">${escapeHtml(node.config.prompt)}</textarea>
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
          <input type="text" class="property-input" value="${escapeHtml(node.config.url)}" oninput="updateNodeConfig('${nodeId}', 'url', this.value)">
        </div>
      `;
    }
    if (node.config.method !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">请求方法</label>
          <select class="property-select" onchange="updateNodeConfig('${nodeId}', 'method', this.value)">
            <option value="GET" ${node.config.method === 'GET' ? 'selected' : ''}>GET</option>
            <option value="POST" ${node.config.method === 'POST' ? 'selected' : ''}>POST</option>
          </select>
        </div>
      `;
    }
    if (node.config.condition !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">条件表达式</label>
          <input type="text" class="property-input" value="${escapeHtml(node.config.condition)}" oninput="updateNodeConfig('${nodeId}', 'condition', this.value)">
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

function deleteNode(nodeId) {
  pushHistory();
  editorNodes = editorNodes.filter(n => n.id !== nodeId);
  editorEdges = editorEdges.filter(e => e.source !== nodeId && e.target !== nodeId);
  selectedNode = null;
  renderCanvas();
  saveWorkflow();
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
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
