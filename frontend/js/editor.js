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

let saveTimer = null;
let saveChain = Promise.resolve();
let saveBroken = false;

// Property fields fire on every keystroke, and each one used to PUT the whole graph.
// Both the target and the graph are captured here: a save that lands after the user
// switched workflows must write the graph it was scheduled for, not whatever happens
// to be on the canvas by then.
function scheduleSave() {
  const target = currentWorkflow;
  const snapshot = {
    nodes: JSON.parse(JSON.stringify(editorNodes)),
    edges: JSON.parse(JSON.stringify(editorEdges)),
  };
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    saveTimer = null;
    queueSave(target, snapshot);
  }, 400);
}

function queueSave(target, snapshot) {
  // Callers that do not build one themselves still mean "the graph as it is right
  // now", not "whatever is on the canvas when this save finally gets its turn".
  const data = snapshot || {
    nodes: JSON.parse(JSON.stringify(editorNodes)),
    edges: JSON.parse(JSON.stringify(editorEdges)),
  };
  // One save at a time, oldest first: two overlapping PUTs can land out of order
  // and leave the older graph as the stored one.
  saveChain = saveChain
    .then(() => saveWorkflow(target, data))
    .then(() => {
      saveBroken = false;
    })
    .catch((e) => {
      // One toast per failure streak — the editor keeps retrying on every edit.
      if (!saveBroken) {
        saveBroken = true;
        showToast(`自动保存失败：${e.message}，改动目前只在本地`, 'error');
      }
    });
  return saveChain;
}

async function flushSave() {
  clearTimeout(saveTimer);
  saveTimer = null;
  await queueSave(currentWorkflow);
}

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
  // Ctrl+Z on another page used to run through with a stale stack: it fired a save of
  // the editor's graph and then threw on the property panel that was not there.
  if (currentPage !== 'editor') return;
  if (historyIndex <= 0) return;
  historyIndex--;
  restoreHistory();
}

function redo() {
  if (currentPage !== 'editor') return;
  if (historyIndex >= history.length - 1) return;
  historyIndex++;
  restoreHistory();
}

function restoreHistory() {
  const state = history[historyIndex];
  editorNodes = JSON.parse(JSON.stringify(state.nodes));
  editorEdges = JSON.parse(JSON.stringify(state.edges));
  selectedNode = null;
  cancelConnection();
  renderCanvas();
  queueSave(currentWorkflow);
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    cancelConnection();
    return;
  }
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

// Without this the arming survived a released drag, so the next click on any port
// completed a line the user meant to start instead — and the highlighted port kept
// looking selectable.
function cancelConnection() {
  if (!connectingPort) return;
  connectingPort = null;
  document.querySelectorAll('.node-port.connecting').forEach(p => p.classList.remove('connecting'));
  removeTempLine();
}

// A connection is a two-end gesture, and the ends can arrive in either order: a click
// on this port then a click on that one, or a press here and a release there. Both
// routes land here so the checks and the feedback are the same either way.
function completeConnection(end) {
  const start = connectingPort;
  if (!start) return;

  if (start.nodeId === end.nodeId) {
    showToast('不能连接节点自身', 'error');
    cancelConnection();
    return;
  }
  if (start.kind === end.kind) {
    showToast('请从输出端口连到另一个节点的输入端口', 'error');
    cancelConnection();
    return;
  }

  const out = start.kind === 'output' ? start : end;
  const source = out.nodeId;
  const target = start.kind === 'output' ? end.nodeId : start.nodeId;
  const sourcePort = out.portName;

  const exists = editorEdges.some(
    edge => edge.source === source && edge.target === target && (edge.sourcePort || 'output') === sourcePort
  );
  cancelConnection();
  if (exists) {
    showToast('这两个节点之间已经有连线', 'error');
    return;
  }

  editorEdges.push({ source, target, sourcePort });
  // Recorded after the change, like every other edit: a step that stores the
  // state before it is a state the canvas is never actually in, so redo had
  // nothing to land on.
  pushHistory();
  renderCanvas();
  queueSave(currentWorkflow);
}

async function initEditor() {
  // The undo stack belongs to the graph that was open, not to the editor. Left over
  // from the previous workflow, one Ctrl+Z pasted that graph onto this one and the
  // autosave quietly wrote it to the server.
  history = [];
  historyIndex = -1;
  selectedNode = null;
  connectingPort = null;
  draggingNode = null;
  // A pending debounce is deliberately left running: it carries its own target and
  // graph, so cancelling it here would drop the last keystroke before a switch.

  nodeTypes = await fetchJson(`${API}/api/node-types`);
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
      <div class="node-port" data-node="${escapeAttr(node.id)}" data-kind="output" data-port="${escapeAttr(port)}"></div>
    </div>
  `).join('');

  el.innerHTML = `
    <div class="node-header">
      <span class="node-icon" style="color: ${info.color}; background: ${info.color}14; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border-radius: 7px; font-size: 14px;">${info.icon}</span>
      <span style="flex:1;">${escapeHtml(node.title || info.label)}</span>
    </div>
    ${configHint ? `<div class="node-body">${configHint}</div>` : ''}
    <div class="node-ports">
      ${hasInput ? '<div class="port-group"><div class="port-slot"><div class="node-port" data-node="' + escapeAttr(node.id) + '" data-kind="input" data-port="input"></div></div></div>' : '<div></div>'}
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
      const ref = {
        nodeId: port.dataset.node,
        kind: port.dataset.kind,
        portName: port.dataset.port,
      };

      if (!connectingPort) {
        connectingPort = ref;
        port.classList.add('connecting');
        return;
      }

      completeConnection(ref);
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

function removeTempLine() {
  const el = document.getElementById('edge-temp');
  if (el) el.remove();
}

// The documented gesture is press-and-drag, so the line has to follow the cursor: a
// drag that ends at the target with nothing drawn on the way looks like nothing
// happened, and the user releases the mouse believing the connection failed.
function drawTempLine(e) {
  const svg = document.getElementById('svg-layer');
  const canvas = document.getElementById('canvas');
  if (!svg || !canvas || !connectingPort) return;

  const nodeEl = document.querySelector(`.workflow-node[data-id="${connectingPort.nodeId}"]`);
  const anchor = nodeEl ? portAnchor(nodeEl, connectingPort.kind, connectingPort.portName) : null;
  if (!anchor) return;

  const rect = canvas.getBoundingClientRect();
  const x1 = anchor.x - rect.left;
  const y1 = anchor.y - rect.top;
  const x2 = e.clientX - rect.left;
  const y2 = e.clientY - rect.top;
  const dx = Math.max(40, Math.abs(x2 - x1) / 2);

  let path = document.getElementById('edge-temp');
  if (!path) {
    path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('id', 'edge-temp');
    path.setAttribute('class', 'edge-temp');
    svg.appendChild(path);
  }
  path.setAttribute('d', `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`);
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
      editorEdges.splice(i, 1);
      pushHistory();
      renderCanvas();
      queueSave(currentWorkflow);
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
    queueSave(currentWorkflow);
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
  if (connectingPort && !draggingNode) {
    drawTempLine(e);
    return;
  }
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

document.addEventListener('mouseup', (e) => {
  if (draggingNode) {
    pushHistory();
    queueSave(currentWorkflow);
  }
  draggingNode = null;

  const hit = e.target;
  const onPort = hit && hit.classList && hit.classList.contains('node-port');
  if (!connectingPort) return;
  // Releasing over the port that armed the connection is the tail of the first click
  // of a click-then-click, so it stays armed. Anywhere else the gesture is over: on a
  // different port it tries to connect, off the ports it cancels.
  const samePort = onPort
    && hit.dataset.node === connectingPort.nodeId
    && hit.dataset.kind === connectingPort.kind
    && hit.dataset.port === connectingPort.portName;
  if (samePort) return;
  if (onPort) {
    completeConnection({ nodeId: hit.dataset.node, kind: hit.dataset.kind, portName: hit.dataset.port });
    return;
  }
  cancelConnection();
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
      <input type="text" class="property-input" value="${escapeAttr(node.id)}" disabled style="opacity: 0.5;">
    </div>
    <div class="property-group">
      <label class="property-label">标题</label>
      <input type="text" class="property-input" id="prop-title" value="${escapeAttr(node.title || '')}" oninput="updateNodeProp('${escapeJsAttr(nodeId)}', 'title', this.value)">
    </div>
    <div class="property-group">
      <label class="property-label">类型</label>
      <input type="text" class="property-input" value="${escapeAttr(info.label || node.type)}" disabled style="opacity: 0.5;">
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
          <textarea class="property-textarea" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'prompt', this.value)">${escapeHtml(node.config.prompt)}</textarea>
        </div>
      `;
    }
    if (node.config.model !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">模型</label>
          <select class="property-select" id="prop-model" onchange="updateNodeConfig('${escapeJsAttr(nodeId)}', 'model', this.value)">
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
          <label class="property-label">温度：${escapeHtml(node.config.temperature)}</label>
          <input type="range" class="property-input" min="0" max="1" step="0.1" value="${escapeAttr(node.config.temperature)}"
            oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'temperature', parseFloat(this.value)); this.previousElementSibling.textContent = '温度：' + this.value">
        </div>
      `;
    }
    if (node.config.url !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">请求地址</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.url)}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'url', this.value)">
        </div>
      `;
    }
    if (node.config.method !== undefined) {
      const methods = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
      html += `
        <div class="property-group">
          <label class="property-label">请求方法</label>
          <select class="property-select" onchange="updateNodeConfig('${escapeJsAttr(nodeId)}', 'method', this.value)">
            ${methods.map(m => `<option value="${m}" ${node.config.method === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">请求头（JSON）</label>
          <textarea class="property-textarea property-mono" oninput="updateNodeJson('${escapeJsAttr(nodeId)}', 'headers', this.value, this)">${escapeHtml(JSON.stringify(node.config.headers ?? {}, null, 2))}</textarea>
          <div class="property-hint" hidden>不是合法的 JSON，这段改动没有保存。</div>
        </div>
        ${node.config.method === 'GET' ? '' : `
        <div class="property-group">
          <label class="property-label">请求体</label>
          <textarea class="property-textarea property-mono" placeholder='{"key": "{{input}}"}' oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'body', this.value)">${escapeHtml(node.config.body ?? '')}</textarea>
        </div>`}
        <label class="property-check">
          <input type="checkbox" ${node.config.fail_on_error !== false ? 'checked' : ''} onchange="updateNodeConfig('${escapeJsAttr(nodeId)}', 'fail_on_error', this.checked)">
          <span>4xx / 5xx 视为执行失败</span>
        </label>
      `;
    }
    if (node.config.condition !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">条件表达式</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.condition)}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'condition', this.value)">
          <div class="property-hint">支持 <code>==</code> <code>!=</code> <code>&gt;</code> <code>&gt;=</code> <code>contains</code> <code>and</code> <code>or</code>，变量直接写 ID，如 <code>llm_1 contains "投诉"</code>。结果走「是 / 否」两个出口。</div>
        </div>
      `;
    }
    if (node.config.operation !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">处理方式</label>
          <select class="property-select" onchange="updateNodeConfig('${escapeJsAttr(nodeId)}', 'operation', this.value)">
            ${['concat', 'split', 'replace'].map(op => `<option value="${op}" ${node.config.operation === op ? 'selected' : ''}>${{ concat: '拼接文本', split: '拆分为列表', replace: '查找替换' }[op]}</option>`).join('')}
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">文本片段（JSON 数组）</label>
          <textarea class="property-textarea property-mono" oninput="updateNodeJson('${escapeJsAttr(nodeId)}', 'texts', this.value, this)">${escapeHtml(JSON.stringify(node.config.texts ?? [], null, 2))}</textarea>
          <div class="property-hint" hidden>不是合法的 JSON，这段改动没有保存。</div>
        </div>
        ${node.config.operation === 'split' ? `
        <div class="property-group">
          <label class="property-label">分隔符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.separator ?? '\\n')}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'separator', this.value)">
        </div>` : ''}
        ${node.config.operation === 'replace' ? `
        <div class="property-group">
          <label class="property-label">查找</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.old ?? '')}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'old', this.value)">
        </div>
        <div class="property-group">
          <label class="property-label">替换为</label>
          <input type="text" class="property-input" value="${escapeAttr(node.config.new ?? '')}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'new', this.value)">
        </div>` : ''}
      `;
    }
    if (node.config.source !== undefined) {
      html += `
        <div class="property-group">
          <label class="property-label">列表来源</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.source)}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'source', this.value)">
          <div class="property-hint">可写 <code>{{input}}</code> 或上游节点 ID；JSON 数组会自动识别，否则按分隔符拆分。</div>
        </div>
        <div class="property-group">
          <label class="property-label">分隔符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.separator ?? '\\n')}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'separator', this.value)">
        </div>
        <div class="property-group">
          <label class="property-label">每项动作</label>
          <select class="property-select" onchange="updateNodeConfig('${escapeJsAttr(nodeId)}', 'action', this.value)">
            <option value="llm" ${node.config.action === 'llm' ? 'selected' : ''}>调用大模型</option>
            <option value="collect" ${node.config.action === 'collect' ? 'selected' : ''}>仅收集原项</option>
          </select>
        </div>
        <div class="property-group">
          <label class="property-label">最多处理条数</label>
          <input type="number" class="property-input" min="1" max="100" value="${Number(node.config.max_items ?? 20)}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'max_items', parseInt(this.value, 10))">
        </div>
        <div class="property-group">
          <label class="property-label">结果连接符（写 \\n 表示换行）</label>
          <input type="text" class="property-input property-mono" value="${escapeAttr(node.config.join ?? '\\n\\n')}" oninput="updateNodeConfig('${escapeJsAttr(nodeId)}', 'join', this.value)">
        </div>
      `;
    }
  }

  html += `
    <div style="margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border);">
      <button class="btn btn-danger" onclick="deleteNode('${escapeJsAttr(nodeId)}')" style="width: 100%;">删除节点</button>
    </div>
  `;

  panel.innerHTML = html;
}

function updateNodeProp(nodeId, prop, value) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (node) {
    node[prop] = value;
    renderCanvas();
    scheduleSave();
  }
}

function updateNodeConfig(nodeId, key, value) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (node) {
    node.config[key] = value;
    scheduleSave();
  }
}

function updateNodeJson(nodeId, key, raw, field) {
  const node = editorNodes.find(n => n.id === nodeId);
  if (!node) return;
  const hint = field ? field.parentElement.querySelector('.property-hint') : null;
  try {
    node.config[key] = JSON.parse(raw);
  } catch (e) {
    // The box still shows what the user typed, so without this the field looks
    // configured while the saved graph keeps the previous value.
    if (field) field.classList.add('invalid');
    if (hint) hint.hidden = false;
    return;
  }
  if (field) field.classList.remove('invalid');
  if (hint) hint.hidden = true;
  scheduleSave();
}

function deleteNode(nodeId) {
  editorNodes = editorNodes.filter(n => n.id !== nodeId);
  editorEdges = editorEdges.filter(e => e.source !== nodeId && e.target !== nodeId);
  selectedNode = null;
  // Its ports disappear with it, and a connection armed to one of them would now
  // create a line out of a node id that no longer exists.
  if (connectingPort && connectingPort.nodeId === nodeId) cancelConnection();
  pushHistory();
  renderCanvas();
  queueSave(currentWorkflow);
  document.getElementById('prop-content').innerHTML = '<p style="font-size: 13px; color: var(--text-tertiary);">选择节点查看属性</p>';
}

async function checkWorkflow() {
  let data;
  try {
    data = await requestJson(`${API}/api/workflows/validate`, {
      method: 'POST',
      body: JSON.stringify({ nodes: editorNodes, edges: editorEdges }),
    });
  } catch (e) {
    showToast(e.message, 'error');
    return false;
  }
  if (data.valid) {
    showToast('检查通过，可以直接运行', 'success');
    return true;
  }
  showToast((data.problems || []).join('；'), 'error');
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
  await flushSave();
  if (!currentWorkflow.id) {
    showToast('保存失败，无法执行', 'error');
    return;
  }
  openRunModal(currentWorkflow.id, currentWorkflow.name);
}

async function saveWorkflow(target = currentWorkflow, data) {
  if (!target) return;

  const graph = data || {
    nodes: JSON.parse(JSON.stringify(editorNodes)),
    edges: JSON.parse(JSON.stringify(editorEdges)),
  };

  if (target.id) {
    try {
      await requestJson(`${API}/api/workflows/${target.id}`, { method: 'PUT', body: JSON.stringify(graph) });
    } catch (e) {
      throw new Error(e.status === 404 ? '这份工作流已被删除' : e.message);
    }
    return;
  }

  // A brand new workflow has nothing stored yet, so the canvas goes with the name.
  const wf = await requestJson(`${API}/api/workflows`, {
    method: 'POST',
    body: JSON.stringify({
      name: target.name || '未命名工作流',
      description: target.description || '',
      nodes: graph.nodes,
      edges: graph.edges,
    }),
  });
  target.id = wf.id;
}
