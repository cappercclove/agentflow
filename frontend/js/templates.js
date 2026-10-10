const WORKFLOW_TEMPLATES = [
  {
    icon: '',
    color: '#6366f1',
    bg: 'rgba(99, 102, 241, 0.08)',
    name: '文档摘要',
    desc: '上传文档，自动提取关键信息并生成精炼摘要',
    steps: ['提取信息', '生成摘要'],
    nodes: [
      { id: 'start', type: 'start', title: '开始', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '提取信息', x: 280, y: 200, config: { prompt: '请从以下内容中提取关键信息：\n{{input}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'llm_2', type: 'llm', title: '生成摘要', x: 500, y: 200, config: { prompt: '请生成简洁的摘要（不超过200字）：\n{{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: '结束', x: 720, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#06b6d4',
    bg: 'rgba(6, 182, 212, 0.08)',
    name: '多语言翻译',
    desc: '自动检测语言、翻译并进行质量检查',
    steps: ['语言检测', '翻译', '质量检查'],
    nodes: [
      { id: 'start', type: 'start', title: '开始', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '语言检测', x: 280, y: 200, config: { prompt: '请检测以下文本的语言（仅返回语言名称）：\n{{input}}', model: 'qwen-turbo', temperature: 0.1 } },
      { id: 'llm_2', type: 'llm', title: '翻译', x: 500, y: 200, config: { prompt: '请将以下文本翻译为英文：\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'llm_3', type: 'llm', title: '质量检查', x: 720, y: 200, config: { prompt: '请检查翻译质量：\n原文：{{input}}\n译文：{{llm_2}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'end', type: 'end', title: '结束', x: 940, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'llm_3' },
      { source: 'llm_3', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#f59e0b',
    bg: 'rgba(245, 158, 11, 0.08)',
    name: '数据分析',
    desc: '输入数据，自动分析趋势并生成洞察报告',
    steps: ['趋势分析', '报告生成', '格式化'],
    nodes: [
      { id: 'start', type: 'start', title: '开始', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '趋势分析', x: 280, y: 200, config: { prompt: '请分析以下数据的趋势和异常：\n{{input}}', model: 'qwen-plus', temperature: 0.3 } },
      { id: 'llm_2', type: 'llm', title: '报告生成', x: 500, y: 200, config: { prompt: '请生成一份包含概述、发现和建议的洞察报告：\n{{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'text_1', type: 'text', title: '格式化', x: 720, y: 200, config: { operation: 'concat', texts: ['数据分析报告\n\n', '{{llm_2}}', '\n\n---\n由 AgentFlow 生成'] } },
      { id: 'end', type: 'end', title: '结束', x: 940, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'text_1' },
      { source: 'text_1', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#22c55e',
    bg: 'rgba(34, 197, 94, 0.08)',
    name: '智能客服',
    desc: '识别用户意图，自动分类并生成专业回复',
    steps: ['意图识别', '分类处理', '回复生成'],
    nodes: [
      { id: 'start', type: 'start', title: '用户输入', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '意图识别', x: 280, y: 200, config: { prompt: '请分类以下用户意图（咨询/投诉/建议/其他）：\n{{input}}', model: 'qwen-turbo', temperature: 0.1 } },
      { id: 'condition_1', type: 'condition', title: '是否投诉', x: 500, y: 200, config: { condition: "'{{llm_1}}' == '投诉'" } },
      { id: 'llm_2', type: 'llm', title: '投诉处理', x: 720, y: 120, config: { prompt: '请以同理心和专业态度处理以下投诉，并提供解决方案：\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'llm_3', type: 'llm', title: '标准回复', x: 720, y: 280, config: { prompt: '请专业地回答以下用户问题：\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: '结束', x: 940, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'condition_1' },
      { source: 'condition_1', target: 'llm_2', sourcePort: 'true' },
      { source: 'condition_1', target: 'llm_3', sourcePort: 'false' },
      { source: 'llm_2', target: 'end' },
      { source: 'llm_3', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#ec4899',
    bg: 'rgba(236, 72, 153, 0.08)',
    name: '内容创作',
    desc: '从主题出发，自动生成大纲、撰写内容并润色',
    steps: ['大纲生成', '内容撰写', '润色优化'],
    nodes: [
      { id: 'start', type: 'start', title: '主题输入', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '大纲生成', x: 280, y: 200, config: { prompt: '请生成详细的大纲（5-7个章节）：\n{{input}}', model: 'qwen-plus', temperature: 0.8 } },
      { id: 'llm_2', type: 'llm', title: '内容撰写', x: 500, y: 200, config: { prompt: '请根据大纲撰写完整内容（每章200-300字）：\n{{llm_1}}', model: 'qwen-plus', temperature: 0.8 } },
      { id: 'llm_3', type: 'llm', title: '润色优化', x: 720, y: 200, config: { prompt: '请润色以下文本，提升表达和可读性：\n{{llm_2}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'end', type: 'end', title: '完成', x: 940, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'llm_3' },
      { source: 'llm_3', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#8b5cf6',
    bg: 'rgba(139, 92, 246, 0.08)',
    name: '检索增强',
    desc: '自动生成搜索关键词，综合检索结果回答问题',
    steps: ['关键词生成', '综合回答'],
    nodes: [
      { id: 'start', type: 'start', title: '用户提问', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: '关键词生成', x: 280, y: 200, config: { prompt: '请生成3-5个搜索关键词（逗号分隔）：\n{{input}}', model: 'qwen-turbo', temperature: 0.3 } },
      { id: 'llm_2', type: 'llm', title: '综合回答', x: 500, y: 200, config: { prompt: '请根据以下信息提供全面的回答：\n问题：{{input}}\n关键词：{{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: '结束', x: 720, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'end' },
    ],
  },
  {
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>',
    color: '#0ea5e9',
    bg: 'rgba(14, 165, 233, 0.08)',
    name: '秋招投递助手',
    desc: '分析岗位 JD，评估简历匹配度，生成求职信和面试建议',
    steps: ['JD 分析', '简历匹配', '求职信生成', '面试建议'],
    nodes: [
      { id: 'start', type: 'start', title: '输入岗位信息', x: 60, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'JD 分析', x: 260, y: 200, config: { prompt: '请分析以下招聘岗位要求，提取：1.核心技能要求 2.经验要求 3.学历门槛 4.加分项\n\n岗位信息：\n{{input}}', model: 'qwen-plus', temperature: 0.3 } },
      { id: 'llm_2', type: 'llm', title: '简历匹配评估', x: 480, y: 140, config: { prompt: '我有一份简历和一个岗位分析。请评估匹配度（0-100分），列出匹配项和缺失项，给出改进建议。\n\n岗位要求分析：\n{{llm_1}}\n\n我的简历：\n{{input}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'condition_1', type: 'condition', title: '匹配度判断', x: 700, y: 200, config: { condition: 'llm_2 contains "80" or llm_2 contains "90" or llm_2 contains "100"' } },
      { id: 'llm_3', type: 'llm', title: '生成求职信', x: 920, y: 120, config: { prompt: '基于以下信息，帮我写一封专业的求职信（200字以内），突出我的优势和与岗位的匹配点：\n\n岗位分析：{{llm_1}}\n匹配评估：{{llm_2}}\n原始信息：{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'llm_4', type: 'llm', title: '改进建议', x: 920, y: 300, config: { prompt: '匹配度不够理想。请给出具体改进建议：1.简历需要补充什么 2.需要学习哪些技能 3.如何突出现有经验的相关性\n\n岗位分析：{{llm_1}}\n匹配评估：{{llm_2}}', model: 'qwen-plus', temperature: 0.6 } },
      { id: 'llm_5', type: 'llm', title: '面试准备建议', x: 1140, y: 200, config: { prompt: '基于岗位分析和我的背景，预测可能的面试问题（5个），并给出回答要点：\n\n岗位分析：{{llm_1}}\n背景信息：{{input}}', model: 'qwen-plus', temperature: 0.6 } },
      { id: 'end', type: 'end', title: '完成', x: 1360, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'condition_1' },
      { source: 'condition_1', target: 'llm_3', sourcePort: 'true' },
      { source: 'condition_1', target: 'llm_4', sourcePort: 'false' },
      { source: 'llm_3', target: 'llm_5' },
      { source: 'llm_4', target: 'llm_5' },
      { source: 'llm_5', target: 'end' },
    ],
  },
  {
    icon: '',
    color: '#06b6d4',
    bg: 'rgba(6, 182, 212, 0.08)',
    name: '批量条目处理',
    desc: '把长文本按行拆成条目，逐项调用大模型，再汇总为一篇',
    steps: ['拆分为条目', '逐项生成摘要', '汇总成篇'],
    nodes: [
      { id: 'start', type: 'start', title: '原始文本', x: 60, y: 200, config: {} },
      { id: 'split_1', type: 'text', title: '按行拆分', x: 250, y: 200, config: { operation: 'split', texts: ['{{input}}'], separator: '\\n' } },
      { id: 'loop_1', type: 'loop', title: '逐项摘要', x: 460, y: 200, config: { source: '{{split_1}}', separator: '\\n', action: 'llm', prompt: '请为以下条目写一句 40 字以内的中文摘要：\n{{item}}', model: 'qwen-plus', temperature: 0.5, max_items: 20, join: '\\n\\n' } },
      { id: 'llm_1', type: 'llm', title: '汇总成篇', x: 690, y: 200, config: { prompt: '请把下面的逐条摘要整合为一段连贯的总述（不超过 200 字）：\n{{loop_1}}', model: 'qwen-plus', temperature: 0.6 } },
      { id: 'end', type: 'end', title: '结束', x: 910, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'split_1', sourcePort: 'output' },
      { source: 'split_1', target: 'loop_1', sourcePort: 'output' },
      { source: 'loop_1', target: 'llm_1', sourcePort: 'output' },
      { source: 'llm_1', target: 'end', sourcePort: 'output' },
    ],
  },
];

function renderTemplates(container) {
  let html = '<div class="template-grid">';

  WORKFLOW_TEMPLATES.forEach((tpl, i) => {
    const flowHtml = tpl.steps.map((s, si) =>
      `<span class="template-flow-step">${s}</span>` +
      (si < tpl.steps.length - 1 ? '<span class="template-flow-arrow">\u2192</span>' : '')
    ).join('');

    html += `
      <div class="template-card" onclick="useTemplate(${i})" style="animation-delay: ${i * 0.04}s; --tpl-color: ${tpl.color};">
        <div class="template-icon" style="background: ${tpl.bg}; color: ${tpl.color};">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            ${getTemplateIcon(i)}
          </svg>
        </div>
        <div class="template-name">${tpl.name}</div>
        <div class="template-description">${tpl.desc}</div>
        <div class="template-flow">${flowHtml}</div>
      </div>
    `;
  });

  html += '</div>';
  container.innerHTML = html;
}

function getTemplateIcon(index) {
  const icons = [
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
    '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    '<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><path d="M2 2l7.586 7.586"/>',
    '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/>',
    '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/>',
  ];
  return icons[index] || icons[0];
}

function useTemplate(index) {
  const tpl = WORKFLOW_TEMPLATES[index];

  currentWorkflow = {
    id: null,
    name: tpl.name,
    description: tpl.desc,
    nodes: JSON.parse(JSON.stringify(tpl.nodes)),
    edges: JSON.parse(JSON.stringify(tpl.edges)),
  };

  navigateTo('editor');
  showToast(`已加载模板：${tpl.name}`, 'success');
}
