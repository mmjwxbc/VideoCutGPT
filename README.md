# 电商出海助手

一个专为电商出海设计的智能助手，提供视频字幕生成、多agent讨论系统和市场调研功能。

## 功能特点

### 1. 视频字幕生成
- 提取视频关键帧
- 利用多模态大模型分析关键帧内容
- 结合产品说明书或自动搜索相关信息
- 生成高质量字幕文件

### 2. 多Agent讨论系统
- 产品宣传小组多成员讨论
- 收集热点信息
- 分析热点视频
- 提出视频拍摄脚本和转场要求

### 3. Deep Research功能
- 市场调研
- 竞品分析
- 出海策略建议

## 技术栈

### 后端
- Python 3.9+
- LangChain
- LangGraph
- LlamaIndex
- FastAPI
- OpenCV (视频处理)

### 前端
- React 18
- Vite
- TailwindCSS
- shadcn/ui

## 项目结构

```
oversea-agent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── endpoints/
│   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── utils.py
│   │   ├── models/
│   │   ├── providers/
│   │   │   └── llm_providers.py
│   │   ├── services/
│   │   │   ├── caption_generator.py
│   │   │   ├── multi_agent.py
│   │   │   └── deep_research.py
│   │   └── workflow/
│   │       └── caption_workflow.py
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── api/
│   │   ├── hooks/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 快速开始

### 后端设置

1. 进入后端目录
```bash
cd backend
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，添加必要的API密钥
```

4. 启动后端服务
```bash
uvicorn main:app --reload
```

### 前端设置

1. 进入前端目录
```bash
cd frontend
```

2. 安装依赖
```bash
npm install
```

3. 启动前端开发服务器
```bash
npm run dev
```

## API文档

启动后端服务后，可以访问 `http://localhost:8000/docs` 查看API文档。

## 注意事项

- 确保配置了正确的API密钥（如OpenAI、Google等）
- 视频处理可能需要较大的内存和处理能力
- 某些功能可能需要较长的处理时间

## 贡献

欢迎提交Issue和Pull Request！