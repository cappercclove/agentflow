# AgentFlow - AI 工作流编排平台

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Deployed](https://img.shields.io/badge/Deployed-Aliyun%20SWAS-FF6A00?logo=alibabacloud)

**可视化 AI 工作流编排平台** — 拖拽节点、连线编排，让 AI 代理自动执行复杂任务

[English](#english) | [中文](#中文)

---

## 🇨🇳 中文

### 📖 项目简介

AgentFlow 是一个基于可视化编排的 AI 工作流平台。用户通过拖拽节点、连线的方式构建自动化工作流，系统支持任务智能分解、多模型调度、条件分支、实时执行监控等功能。

**核心亮点：**
- 可视化工作流编辑器（拖拽 + 连线）
- AI 任务智能分解（复杂任务自动拆分为子任务）
- 多模型调度（qwen-turbo / qwen-plus / qwen-max）
- 条件分支 & 循环控制
- WebSocket 实时执行日志
- 预设工作流模板

### 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Glassmorphism UI)             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ Node Palette │  │   Canvas     │  │  Properties      │  │
│  │  (Drag)      │─▶│  (SVG Edges) │  │  Panel           │  │
│  └──────────────┘  ──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                    RESTful API + WebSocket
                              │
┌─────────────────────────────────────────────────────────────┐
│                      Backend (FastAPI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  Workflow    │  │   Execution  │  │    LLM Client    │  │
│  │  Engine      │─▶│   Engine     │─▶│  (Multi-Model)   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                          │                                    │
│                    ┌─────┴─────┐                              │
│                    │  SQLite   │                              │
│                    └───────────┘                              │
─────────────────────────────────────────────────────────────┘
```

### ✨ 功能特性

- **🎨 可视化编辑器** — 拖拽节点、SVG 连线、实时预览
- **🤖 AI 任务分解** — 输入复杂任务，自动拆分为可执行子任务
- **🔀 条件分支** — if/else 判断，不同路径执行不同逻辑
- **🌐 HTTP 请求** — 节点内直接调用外部 API
- **📝 文本处理** — 拼接、分割、替换等文本操作
- **⚡ 多模型调度** — 不同节点使用不同模型（turbo/plus/max）
- **📊 实时日志** — WebSocket 推送执行进度和结果
- **📋 工作流模板** — 预设常用模板，一键加载

### 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| 后端框架 | FastAPI + Uvicorn |
| 数据库 | SQLite + SQLAlchemy |
| 大语言模型 | 阿里云百炼 (qwen-turbo/plus/max) |
| 实时通信 | WebSocket |
| 前端 | 原生 HTML/CSS/JS (玻璃拟态暗色主题) |
| 部署 | Docker + Aliyun SWAS |

### 🚀 快速开始

#### 前置要求

- Python 3.11+
- 阿里云百炼 API Key（[获取地址](https://bailian.console.aliyun.com/)）

#### 本地运行

```bash
# 1. 克隆项目
git clone https://github.com/your-username/ai-agent-workflow.git
cd ai-agent-workflow

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r backend/requirements.txt

# 4. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入你的百炼 API Key

# 5. 启动服务
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 6. 访问
# 前端: http://localhost:8000
# API文档: http://localhost:8000/docs
```

#### Docker 部署

```bash
# 1. 配置环境变量
export BAILIAN_API_KEY=your-api-key-here
export BAILIAN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 2. 构建并启动
docker-compose up -d

# 3. 访问 http://localhost:8001
```

### 📡 API 文档

启动服务后访问 `http://localhost:8000/docs` 查看交互式 API 文档。

**主要接口：**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 前端页面 |
| GET | `/api/node-types` | 获取节点类型定义 |
| POST | `/api/workflows` | 创建工作流 |
| GET | `/api/workflows` | 获取工作流列表 |
| GET | `/api/workflows/{id}` | 获取工作流详情 |
| PUT | `/api/workflows/{id}` | 更新工作流 |
| DELETE | `/api/workflows/{id}` | 删除工作流 |
| POST | `/api/workflows/{id}/execute` | 执行工作流 |
| POST | `/api/decompose` | AI 任务分解 |
| GET | `/api/executions` | 获取执行记录 |
| GET | `/api/stats` | 获取统计信息 |
| WS | `/ws/execute/{id}` | WebSocket 实时日志 |

###  项目结构

```
ai-agent-workflow/
├── backend/
│   ├── main.py                 # FastAPI 应用入口
│   ├── models.py               # 数据库模型
│   ├── workflow_engine.py      # 工作流执行引擎
│   ├── llm_client.py           # 多模型 LLM 客户端
│   ├── node_types.py           # 节点类型定义
│   ├── requirements.txt        # Python 依赖
│   ── .env.example            # 环境变量模板
── frontend/
│   ├── index.html              # 主页面
│   ├── css/
│   │   └── style.css           # 玻璃拟态暗色主题
│   ── js/
│       ├── app.js              # 主应用逻辑
│       ├── editor.js           # 可视化编辑器
│       └── templates.js        # 工作流模板
├── docs/
│   └── sample_workflow.json    # 示例工作流
├── Dockerfile
├── docker-compose.yml
├── .gitignore
├── LICENSE
└── README.md
```

### 🔮 未来计划

- [ ] 接入独立 Embedding 模型
- [ ] 添加 Redis 缓存层
- [ ] 支持子工作流调用
- [ ] 用户认证与多用户管理
- [ ] 工作流版本控制
- [ ] Nginx 反向代理 + HTTPS

---

## 🇬🇧 English

###  Introduction

AgentFlow is a visual AI workflow orchestration platform. Users build automation workflows by dragging nodes and connecting edges. The system supports intelligent task decomposition, multi-model scheduling, conditional branching, and real-time execution monitoring.

### ✨ Features

- **🎨 Visual Editor** — Drag-and-drop nodes, SVG edges, live preview
- **🤖 AI Task Decomposition** — Automatically split complex tasks into subtasks
- **🔀 Conditional Branching** — if/else logic for different execution paths
- **🌐 HTTP Requests** — Call external APIs directly from nodes
- **📝 Text Processing** — Concatenate, split, replace text operations
- **⚡ Multi-Model Scheduling** — Use different models per node (turbo/plus/max)
- ** Real-time Logs** — WebSocket push for execution progress
- **📋 Workflow Templates** — Pre-built templates, one-click load

###  Quick Start

```bash
git clone https://github.com/your-username/ai-agent-workflow.git
cd ai-agent-workflow
python -m venv venv && source venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # Edit with your API Key
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` for the web UI.

### ️ Tech Stack

Python · FastAPI · SQLite · WebSocket · Alibaba Cloud Bailian LLM · Glassmorphism UI

### 📄 License

[MIT License](LICENSE)

⭐ If you find this project useful, consider giving it a star!
