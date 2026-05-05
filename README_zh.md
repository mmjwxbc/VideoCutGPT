# VideoCutGPT

一个基于**剪辑状态**驱动的对话流剪辑 Agent。

它不是普通的字幕生成器，也不是把大模型接到视频工具上的聊天壳。VideoCutGPT 的核心设计是：用户通过对话提出剪辑意图，Agent 不直接“重做一遍视频”，而是持续更新一份可追踪的 **全局剪辑状态**，再由这份状态推动下一步剪辑动作。

换句话说，这个项目的工作方式不是“输入一句话，吐一个结果”，而是：

**通过剪辑状态流转剪辑步骤。**

## 项目定位

VideoCutGPT 面向短视频、电商出海、投放创意这类高频迭代场景。用户上传视频、补充产品信息或投放要求后，Agent 会在同一个会话里持续推进剪辑任务：

- 先理解视频
- 再生成字幕草稿
- 再整理镜头级剪辑方案
- 再把方案映射成可执行片段
- 最后执行导出

后续所有“改 hook”“压节奏”“重写字幕”“重新导出一个更适合 TikTok 的版本”这类要求，都不是重新开一个新任务，而是在同一个 session 内继续推进。

这让它更像一个可追踪的剪辑运行时，而不是一个一次性内容生成工具。

## 核心理念：对话改的不是文本，而是状态

项目内部维护三层核心结构：

- `turns`：记录每一轮用户输入、Agent 思考、工具调用与最终回复。
- `global_editing_state`：记录当前会话已经沉淀下来的剪辑资产。
- `workflow`：记录每个剪辑步骤当前处于 `idle / doing / done / blocked / needs_refresh` 等什么状态。

因此，用户每一次追问，真正改变的是这条剪辑链路中的某个状态节点，而不是简单地让模型“再生成一次答案”。

这也是这个项目最重要的产品能力：

**把剪辑流程显式化，把状态变更作为 Agent 推动工作的依据。**

## 剪辑状态模型

当前系统围绕一组明确的剪辑产物组织状态：

- `keyframe_analysis`：关键帧分析状态
- `video_summary`：视频内容摘要
- `subtitle_draft`：字幕草稿
- `editing_plan`：镜头级剪辑方案
- `clip_segments`：从原视频时间线映射出的可执行片段
- `english_title`：发布标题
- `tags`：分发标签
- `edited_video`：导出成片与下载信息

这些产物统一挂载在 `global_editing_state` 上，并且每个产物都带有：

- `status`
- `requested`
- `needs_refresh`
- `updated_at`

这意味着 Agent 可以清楚知道：

- 哪些内容已经可用
- 哪些内容是旧的，需要刷新
- 哪些步骤还没做
- 哪些步骤被阻塞了
- 当前能否进入导出

这正是“剪辑状态流转剪辑步骤”的工程化表达。

## Agent 如何推进剪辑

系统不是单次推理，而是一个会话式运行时。典型链路如下：

1. 创建会话，上传视频并提供平台、提示词、产品说明等上下文。
2. 运行视频理解，对关键帧或逐秒画面做视觉分析。
3. 产出视频摘要、字幕草稿和剪辑方案。
4. 将剪辑方案映射成源视频片段，形成可执行的时间线。
5. 调用导出子 Agent，基于 `ffmpeg` 执行裁切、拼接、字幕烧录与成片导出。
6. 用户继续在原会话中追问，系统仅更新相关状态，而不是盲目全量重做。

因此，像下面这些指令都能自然落到对应状态层：

- “把开头 3 秒改得更强一点”
- “字幕改成更像 TikTok 口播”
- “压缩一下节奏，减少空镜”
- “直接给我导出一个带字幕版本”

## 当前产品形态

当前前端是一个会话式字幕与剪辑工作台，核心体验包括：

- 上传视频
- 选择目标平台
- 选择分析模式
- 填写产品说明或创作要求
- 在单线程对话中持续改稿
- 通过 SSE 实时查看任务推进和状态更新
- 在同一会话内下载最终导出的视频

这套交互设计很重要，因为它与传统“表单提交 -> 等待结果”的视频工具完全不同。这里的重点不是一次生成，而是**连续编辑**。

## 架构概览

### 后端

后端基于 `FastAPI`，核心不是简单 API 聚合，而是一个面向会话的剪辑 Agent runtime：

- 会话创建与继续对话
- SSE 推送会话快照与轮次事件
- 多模态关键帧分析
- 字幕、剪辑方案、标题、标签等产物生成
- 片段映射与导出任务编排
- `ffmpeg` / `ffprobe` 驱动的成片导出

关键文件：

- [backend/app/api/endpoints/caption.py](/home/jhli/oversea-agent/backend/app/api/endpoints/caption.py)
- [backend/app/models/caption.py](/home/jhli/oversea-agent/backend/app/models/caption.py)
- [backend/app/services/caption_assistant_runtime/assistant.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/assistant.py)
- [backend/app/services/caption_assistant_runtime/tools.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/tools.py)
- [backend/app/services/caption_assistant_runtime/video_export.py](/home/jhli/oversea-agent/backend/app/services/caption_assistant_runtime/video_export.py)

### 前端

前端基于 `React + Vite + TypeScript`，围绕“会话驱动的剪辑工作台”组织：

- 对话面板：承载用户指令和 Agent 输出
- 工作区侧栏：展示字幕、方案、导出结果等当前状态
- 历史侧栏：管理会话历史
- SSE 订阅：实时同步后台状态，而不是依赖轮询

关键文件：

- [frontend/src/pages/CaptionGenerator.tsx](/home/jhli/oversea-agent/frontend/src/pages/CaptionGenerator.tsx)
- [frontend/src/components/caption-studio/ConversationPanel.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/ConversationPanel.tsx)
- [frontend/src/components/caption-studio/WorkspaceSidebar.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/WorkspaceSidebar.tsx)
- [frontend/src/components/caption-studio/HistorySidebar.tsx](/home/jhli/oversea-agent/frontend/src/components/caption-studio/HistorySidebar.tsx)

## API 形态

核心接口围绕 session 展开：

- `POST /api/caption/assistant/session`
- `GET /api/caption/assistant/session/{session_id}`
- `GET /api/caption/assistant/session/{session_id}/events`
- `POST /api/caption/assistant/session/{session_id}/message`
- `GET /api/caption/assistant/session/{session_id}/exported-video`

这组接口对应的是一个长生命周期的剪辑会话，而不是若干彼此独立的生成请求。

## 本地开发

### 依赖要求

- Python `3.12+`
- Node.js `18+`
- 系统已安装 `ffmpeg` 与 `ffprobe`
- 已配置模型提供方 API Key

### 启动后端

安装依赖：

```bash
uv sync
```

启动服务：

```bash
cd backend
uv run uvicorn main:app --reload
```

### 启动前端

安装依赖：

```bash
cd frontend
npm install
```

启动开发环境：

```bash
npm run dev
```

## 配置说明

主要运行时配置位于 [backend/app/core/config.py](/home/jhli/oversea-agent/backend/app/core/config.py)。

重点配置包括：

- 模型凭证：`OPENAI_API_KEY`、`GLM_API_KEY`、`DEEPSEEK_API_KEY`
- 多模态路由：`MULTIMODAL_PROVIDER`、`MULTIMODAL_MODEL`
- 视频分析参数：`KEYFRAME_INTERVAL_SECONDS`、`MAX_KEYFRAMES`
- 导出参数：`EXPORT_DIR`、`FFMPEG_EXECUTION_TIMEOUT_SECONDS`

项目会从 `.env` 读取环境变量。


## English Version

英文版见 [README.md](/home/jhli/oversea-agent/README.md)。
