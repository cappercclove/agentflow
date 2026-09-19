let editorNodes = [];
let editorEdges = [];
let selectedNode = null;
let draggingNode = null;
let dragOffset = { x: 0, y: 0 };
let connectingPort = null;
let nodeTypes = {};

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
}

function renderPalette() {
  const palette = document.getElementById('node-palette');
  if (!palette) return;

  palette.innerHTML = '<div class="palette-header">> NODE_TYPES</div>';

  Object.entries(nodeTypes).forEach(([type, info]) => {
    const el = document.createElement('div');
    el.className = 'node-type-item';
    el.draggable = true;
    el.innerHTML = `
      <span class="node-type-icon" style="color: ${info.color}; text-shadow: 0 0 10px ${info.color};">${info.icon}</span>
      <span>[${info.label}]</span>
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
  renderEdges(svg);

  editorNodes.forEach(node => {
    const el = createNodeElement(node);
    canvas.appendChild(el);
  });
}

function createNodeElement(node) {
  const info = nodeTypes[node.type] || { label: node.type, color: '#888', icon: '', inputs: [], outputs: [] };
  const el = document.createElement('div');
  el.className = 'workflow-node';
  el.dataset.id = node.id;
  el.style.left = node.x + 'px';
  el.style.top = node.y + 'px';
  el.style.borderColor = info.color;
  el.style.color = info.color;

  const hasInput = info.inputs && info.inputs.length > 0;
  const hasOutput = info.outputs && info.outputs.length > 0;

  el.innerHTML = `
    <div class="node-header" style="border-bottom-color: ${info.color}40;">
      <span class="node-icon" style="color: ${info.color}; text-shadow: 0 0 10px ${info.color};">${info.icon}</span>
      <span>${escapeHtml(node.title || info.label)}</span>
    </div>
    <div class="node-body">[${info.label}]</div>
    <div class="node-ports">
      ${hasInput ? '<div class="node-port" data-node="' + node.id + '" data-port="input" style="border-color: ' + info.color + ';"></div>' : '<div></div>'}
      ${hasOutput ? '<div class="node-port" data-node="' + node.id + '" data-port="output" style="border-color: ' + info.color + ';"></div>' : '<div></div>'}
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
        port.style.background = port.style.borderColor;
      } else {
        if (connectingPort.nodeId !== nodeId && connectingPort.portType !== portType) {
          const source = connectingPort.portType === 'output' ? connectingPort.nodeId : nodeId;
          const target = connectingPort.portType === 'input' ? connectingPort.nodeId : nodeId;

          const exists = editorEdges.some(e => e.source === source && e.target === target);
          if (!exists) {
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
      editorEdges.splice(i, 1);
      renderCanvas();
      saveWorkflow();
    });

    svg.appendChild(pathEl);
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
    renderCanvas();
    saveWorkflow();
  });

  document.addEventListener('mousemove', (e) => {
    if (!draggingNode) return;

    const canvas = document.getElementById('canvas');
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
      saveWorkflow();
    }
    draggingNode = null;
  });

  canvas.addEventListener('click', (e) => {
    if (e.target === canvas || e.target.id === 'svg-layer') {
      selectedNode = null;
      document.querySelectorAll('.workflow-node').forEach(n => n.classList.remove('selected'));
      document.getElementById('prop-content').innerHTML = '<p style="font-size: 12px; color: var(--text-muted);">> SELECT_NODE_TO_INSPECT</p>';
    }
  });
}

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
      <label class="property-label">NODE_ID</label>
      <input type="text" class="property-input" value="${node.id}" disabled style="opacity: 0.5;">
    </div>
    <div class="property-group">
      <label class="property-label">TITLE</label>
      <input type="text" class="property-input" id="prop-title" value="${escapeHtml(node.title || '')}" oninput="updateNodeProp('${nodeId}', 'title', this.value)">
    </div>
    <div class="property-group">
      <label class="property-label">TYPE</label>
      <input type="text" class="property-input" value="${info.label || node.type}" disabled style="opacity: 0.5;">
    </div>
  `;

  if (node.config) {
    if (node.config.prompt !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">PROMPT</label>
          <textarea class="property-textarea" id="prop-prompt" oninput="updateNodeConfig('${nodeId}', 'prompt', this.value)">${escapeHtml(node.config.prompt)}</textarea>
        </div>
      `;
    }
    if (node.config.model !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">MODEL</label>
          <select class="property-select" id="prop-model" onchange="updateNodeConfig('${nodeId}', 'model', this.value)">
            <option value="qwen-turbo" ${node.config.model === 'qwen-turbo' ? 'selected' : ''}>QWEN-TURBO [FAST]</option>
            <option value="qwen-plus" ${node.config.model === 'qwen-plus' ? 'selected' : ''}>QWEN-PLUS [BALANCED]</option>
            <option value="qwen-max" ${node.config.model === 'qwen-max' ? 'selected' : ''}>QWEN-MAX [POWER]</option>
          </select>
        </div>
      `;
    }
    if (node.config.temperature !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">TEMPERATURE: ${node.config.temperature}</label>
          <input type="range" class="property-input" min="0" max="1" step="0.1" value="${node.config.temperature}" 
            oninput="updateNodeConfig('${nodeId}', 'temperature', parseFloat(this.value)); this.previousElementSibling.textContent = 'TEMPERATURE: ' + this.value">
        </div>
      `;
    }
    if (node.config.url !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">URL</label>
          <input type="text" class="property-input" value="${escapeHtml(node.config.url)}" oninput="updateNodeConfig('${nodeId}', 'url', this.value)">
        </div>
      `;
    }
    if (node.config.method !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">METHOD</label>
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
          <label class="property-label">CONDITION_EXPR</label>
          <input type="text" class="property-input" value="${escapeHtml(node.config.condition)}" oninput="updateNodeConfig('${nodeId}', 'condition', this.value)">
        </div>
      `;
    }
  }

  html += `
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--accent-cyan);">
      <button class="btn btn-danger" onclick="deleteNode('${nodeId}')" style="width: 100%;">> DELETE_NODE</button>
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
  editorNodes = editorNodes.filter(n => n.id !== nodeId);
  editorEdges = editorEdges.filter(e => e.source !== nodeId && e.target !== nodeId);
  selectedNode = null;
  renderCanvas();
  saveWorkflow();
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 12px; color: var(--text-muted);">> SELECT_NODE_TO_INSPECT</p>';
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
        name: currentWorkflow.name || 'UNNAMED_WORKFLOW',
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
