# AI Multi-Agent Cyberpunk Desktop Companion

一款由大语言模型驱动的多智能体桌面陪伴系统，探索下一代 AI 在端侧娱乐交互中的落地范式。

## ✨ 核心特性

| 特性 | 实现方式 |
|------|---------|
| 🧠 **多 NPC 并发** | 每个 NPC 独立 asyncio Task，互不阻塞 |
| 📡 **异步事件驱动引擎** | 自研 `EventBus` (pub/sub) + WebSocket 实时通信 |
| 🗃️ **向量长期记忆** | ChromaDB 余弦相似度检索，模拟真实人类记忆 |
| 🔀 **FSM 状态机** | 7 个 NPC 行为状态，严格转换规则，钩子机制 |
| 🛠️ **Function Calling** | 6 种工具：移动、动画、NPC 对话、记忆检索、情绪更新、叙事任务 |
| 🖥️ **Electron 桌面覆盖层** | 透明全屏窗口，赛博朋克 UI 风格 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Frontend                        │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │ NPC 精灵 │  │   聊天面板   │  │   通知/动作展示    │    │
│  └──────────┘  └──────────────┘  └────────────────────┘    │
│                      app.js (WebSocket Client)              │
└─────────────────────────┬───────────────────────────────────┘
                          │ WebSocket (JSON 消息协议)
┌─────────────────────────▼───────────────────────────────────┐
│                    Python Backend                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              EventBus (异步事件总线)                 │    │
│  └───────┬──────────────┬──────────────────────────────┘    │
│          │              │                                    │
│  ┌───────▼────┐  ┌──────▼────────────────────────────────┐  │
│  │ WebSocket  │  │         AgentManager                  │  │
│  │  Server    │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │  │
│  └────────────┘  │  │NPCAgent │ │NPCAgent │ │NPCAgent │ │  │
│                  │  │ ARIA    │ │ NEXUS   │ │  ECHO   │ │  │
│                  │  │ FSM     │ │ FSM     │ │ FSM     │ │  │
│                  │  │ Memory  │ │ Memory  │ │ Memory  │ │  │
│                  │  │ LLM     │ │ LLM     │ │ LLM     │ │  │
│                  │  └─────────┘ └─────────┘ └─────────┘ │  │
│                  └─────────────────┬──────────────────────┘  │
│                                    │                         │
│  ┌─────────────────────────────────▼─────────────────────┐  │
│  │  VectorMemory (ChromaDB)  │  LLMClient (OpenAI API)   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🗂️ 项目结构

```
.
├── backend/
│   ├── main.py                    # 后端入口
│   ├── requirements.txt
│   ├── engine/
│   │   ├── event_bus.py           # 异步 pub/sub 事件总线
│   │   └── websocket_server.py    # WebSocket 服务端
│   ├── agents/
│   │   ├── fsm.py                 # 有限状态机 (7 状态)
│   │   ├── npc_agent.py           # NPC 智能体核心
│   │   └── agent_manager.py       # 多智能体管理器
│   ├── memory/
│   │   └── vector_memory.py       # ChromaDB 向量记忆
│   └── llm/
│       ├── client.py              # LLM 异步客户端
│       └── function_calling.py    # 6 种 Function Calling 工具
├── frontend/
│   ├── main.js                    # Electron 主进程
│   ├── preload.js                 # 安全预加载脚本
│   ├── package.json
│   └── renderer/
│       ├── index.html             # 主界面
│       ├── style.css              # 赛博朋克风格样式
│       └── app.js                 # 前端应用逻辑
├── tests/
│   ├── test_event_bus.py
│   ├── test_fsm.py
│   ├── test_function_calling.py
│   └── test_vector_memory.py
├── .env.example
└── pytest.ini
```

---

## 🚀 快速开始

### 后端

```bash
# 1. 安装依赖
pip install -r backend/requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等

# 3. 启动后端
python -m backend.main
```

### 前端 (Electron)

```bash
cd frontend
npm install
npm start
```

---

## 🧩 NPC 状态机

```
IDLE ──► LISTENING ──► THINKING ──► RESPONDING ──► IDLE
  │                       │
  │                       └──► ACTING ──► IDLE
  │                                    └──► RESPONDING
  └──► MOVING ──► IDLE
  └──► INTERACTING ──► IDLE
                    └──► THINKING
```

---

## 🛠️ Function Calling 工具集

| 工具 | 作用 |
|------|------|
| `move_to(x, y)` | NPC 移动到屏幕坐标 |
| `play_animation(animation)` | 播放指定动画 |
| `send_message_to_npc(target, message)` | NPC 间直接通信 |
| `search_memory(query)` | 向量检索历史记忆 |
| `update_mood(mood, intensity)` | 更新 NPC 情绪状态 |
| `execute_narrative_task(task_id)` | 触发叙事任务/剧情 |

---

## 🧪 运行测试

```bash
python -m pytest tests/ -v
```

47 个单元测试覆盖：EventBus、FSM、Function Calling、VectorMemory。

---

## ⚙️ 配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `LLM_API_KEY` | — | LLM API 密钥 (必填) |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | 兼容 OpenAI 协议的 API 地址 |
| `LLM_MODEL` | `gpt-4o` | 模型名称 |
| `LLM_TEMPERATURE` | `0.8` | 采样温度 |
| `WS_HOST` | `localhost` | WebSocket 服务地址 |
| `WS_PORT` | `8765` | WebSocket 端口 |
| `CHROMA_DIR` | `./chroma_db` | ChromaDB 持久化目录 |

---

## 📐 WebSocket 消息协议

```jsonc
// Frontend → Backend
{ "type": "user:message", "data": { "text": "Hello ARIA", "target_npc_id": "aria" } }

// Backend → Frontend
{ "type": "npc:response",      "data": { "npc_id": "aria", "text": "...", "mood": "happy" } }
{ "type": "npc:state_changed", "data": { "npc_id": "aria", "state": "thinking" } }
{ "type": "npc:action",        "data": { "npc_id": "aria", "action": "move_to", "args": {...} } }
{ "type": "system:status",     "data": { "agents": [...], "agent_count": 3 } }
```

