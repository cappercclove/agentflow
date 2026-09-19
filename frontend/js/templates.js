const WORKFLOW_TEMPLATES = [
  {
    icon: '',
    name: 'DOC_SUMMARIZER',
    desc: 'UPLOAD_DOC >> EXTRACT_KEY_INFO >> GENERATE_SUMMARY',
    nodes: [
      { id: 'start', type: 'start', title: 'START', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'EXTRACT_INFO', x: 280, y: 200, config: { prompt: 'Extract key information from:\n{{input}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'llm_2', type: 'llm', title: 'GENERATE_SUMMARY', x: 500, y: 200, config: { prompt: 'Generate concise summary (200 words max):\n{{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: 'END', x: 720, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'end' },
    ],
  },
  {
    icon: '',
    name: 'MULTI_LANG_TRANSLATOR',
    desc: 'INPUT_TEXT >> DETECT_LANG >> TRANSLATE >> QUALITY_CHECK',
    nodes: [
      { id: 'start', type: 'start', title: 'START', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'DETECT_LANG', x: 280, y: 200, config: { prompt: 'Detect language of (return only language name):\n{{input}}', model: 'qwen-turbo', temperature: 0.1 } },
      { id: 'llm_2', type: 'llm', title: 'TRANSLATE', x: 500, y: 200, config: { prompt: 'Translate to English:\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'llm_3', type: 'llm', title: 'QUALITY_CHECK', x: 720, y: 200, config: { prompt: 'Check translation quality:\nOriginal: {{input}}\nTranslation: {{llm_2}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'end', type: 'end', title: 'END', x: 940, y: 200, config: {} },
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
    name: 'DATA_ANALYST',
    desc: 'INPUT_DATA >> ANALYZE_TRENDS >> GENERATE_REPORT >> FORMAT',
    nodes: [
      { id: 'start', type: 'start', title: 'START', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'ANALYZE', x: 280, y: 200, config: { prompt: 'Analyze data trends and anomalies:\n{{input}}', model: 'qwen-plus', temperature: 0.3 } },
      { id: 'llm_2', type: 'llm', title: 'REPORT_GEN', x: 500, y: 200, config: { prompt: 'Generate insight report (overview, findings, recommendations):\n{{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'text_1', type: 'text', title: 'FORMAT_OUT', x: 720, y: 200, config: { operation: 'concat', texts: ['[DATA_ANALYSIS_REPORT]\n\n', '{{llm_2}}', '\n\n---\nGENERATED_BY_AGENTFLOW'] } },
      { id: 'end', type: 'end', title: 'END', x: 940, y: 200, config: {} },
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
    name: 'SMART_SUPPORT',
    desc: 'USER_QUERY >> INTENT_DETECT >> CLASSIFY >> GENERATE_REPLY',
    nodes: [
      { id: 'start', type: 'start', title: 'USER_INPUT', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'INTENT_DETECT', x: 280, y: 200, config: { prompt: 'Classify intent (inquiry/complaint/suggestion/other):\n{{input}}', model: 'qwen-turbo', temperature: 0.1 } },
      { id: 'condition_1', type: 'condition', title: 'IS_COMPLAINT?', x: 500, y: 200, config: { condition: "'{{llm_1}}' == 'complaint'" } },
      { id: 'llm_2', type: 'llm', title: 'HANDLE_COMPLAINT', x: 720, y: 120, config: { prompt: 'Handle complaint with empathy and solution:\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'llm_3', type: 'llm', title: 'STANDARD_REPLY', x: 720, y: 280, config: { prompt: 'Answer user question professionally:\n{{input}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: 'END', x: 940, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'condition_1' },
      { source: 'condition_1', target: 'llm_2' },
      { source: 'condition_1', target: 'llm_3' },
      { source: 'llm_2', target: 'end' },
      { source: 'llm_3', target: 'end' },
    ],
  },
  {
    icon: '',
    name: 'CONTENT_PIPELINE',
    desc: 'INPUT_TOPIC >> GENERATE_OUTLINE >> WRITE_SECTIONS >> POLISH',
    nodes: [
      { id: 'start', type: 'start', title: 'TOPIC_INPUT', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'OUTLINE_GEN', x: 280, y: 200, config: { prompt: 'Generate detailed outline (5-7 chapters):\n{{input}}', model: 'qwen-plus', temperature: 0.8 } },
      { id: 'llm_2', type: 'llm', title: 'WRITE_CONTENT', x: 500, y: 200, config: { prompt: 'Write full content (200-300 words per chapter):\n{{llm_1}}', model: 'qwen-plus', temperature: 0.8 } },
      { id: 'llm_3', type: 'llm', title: 'POLISH', x: 720, y: 200, config: { prompt: 'Polish text, improve expression and readability:\n{{llm_2}}', model: 'qwen-plus', temperature: 0.5 } },
      { id: 'end', type: 'end', title: 'COMPLETE', x: 940, y: 200, config: {} },
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
    name: 'RETRIEVAL_AUGMENT',
    desc: 'INPUT_QUERY >> GEN_KEYWORDS >> SIMULATE_SEARCH >> SYNTHESIZE',
    nodes: [
      { id: 'start', type: 'start', title: 'USER_QUERY', x: 80, y: 200, config: {} },
      { id: 'llm_1', type: 'llm', title: 'GEN_KEYWORDS', x: 280, y: 200, config: { prompt: 'Generate 3-5 search keywords (comma separated):\n{{input}}', model: 'qwen-turbo', temperature: 0.3 } },
      { id: 'llm_2', type: 'llm', title: 'SYNTHESIZE', x: 500, y: 200, config: { prompt: 'Provide comprehensive answer:\nQuery: {{input}}\nKeywords: {{llm_1}}', model: 'qwen-plus', temperature: 0.7 } },
      { id: 'end', type: 'end', title: 'END', x: 720, y: 200, config: {} },
    ],
    edges: [
      { source: 'start', target: 'llm_1' },
      { source: 'llm_1', target: 'llm_2' },
      { source: 'llm_2', target: 'end' },
    ],
  },
];

function renderTemplates(container) {
  let html = '<div class="template-grid">';

  WORKFLOW_TEMPLATES.forEach((tpl, i) => {
    html += `
      <div class="template-card" onclick="useTemplate(${i})">
        <div class="template-icon">${tpl.icon}</div>
        <div class="template-name">${tpl.name}</div>
        <div class="template-description">${tpl.desc}</div>
      </div>
    `;
  });

  html += '</div>';
  container.innerHTML = html;
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
  showToast(`> TEMPLATE_LOADED: ${tpl.name}`, 'success');
}
