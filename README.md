# 物联网综合实训课程多智能体协同助教系统

面向物联网综合实训课程的本机演示系统。学生可依据课程资料提问、分析代码、完成任务验收并查看学习回顾；教师可管理资料、查看学习活动、编辑任务要求、复核提交和下载作品。前端使用 Vue 3 + Vite，后端使用 FastAPI + SQLAlchemy，默认使用 SQLite。

> 项目代码可以公开阅读；课程原始资料、索引、学生提交、数据库和密钥不包含在仓库中。克隆后需要自行提供课程资料和模型配置。当前是教学演示项目，没有正式账号体系，不适合直接部署到公网。

## 功能概览

| 区域 | 功能 |
| --- | --- |
| 课程问答 | 按模块检索 PPT、Word、PDF；课程问答与实验指导协同；显示依据、调用过程和课件页面预览；可结合现场图片提问 |
| 代码分析 | 自动识别常见语言，Python 本地语法检查，模型静态分析与追问；不执行学生代码 |
| 任务验收 | 从指导手册提取任务要求、表格、配图和评分点；提供对应报告模板；上传作品、代码、运行证据和报告；AI 给出作品 70% + 报告 30% 的初评 |
| 学生记录 | 按浏览器学生标识保存对话、代码分析、任务提交与学习回顾；可查看 AI 评分、教师复核和历史提交 |
| 教师作业管理 | 查看全部任务与提交统计，按任务、班级、学生、日期和复核状态筛选；查看原文、附件、AI 明细；分别下载作品、报告或整次提交；填写意见与最终分数；删除所选提交 |
| 任务版本 | 教师编辑任务要求和评分标准时生成新版本；新提交使用新版本，旧提交保存当时的任务快照；学生修订和教师复核保留历史记录 |
| 学情分析与资料管理 | 按班级、模块和日期统计学习活动；最近提交提供作业管理入口；导入 PPTX、DOCX、PDF，建立可检索文字和 PPT 页面图像索引 |

任务数由已导入的指导手册决定。本机演示资料当前提取出 38 个任务；全新仓库在未导入资料时不会自动出现这些任务。报告模板也来自导入的 Word 原件，不在本仓库发布。

## 快速开始

要求 Python 3.12、Node.js 20+、npm。Windows 是主要演示环境；完整 PPT 页面渲染需要本机 Microsoft PowerPoint。其他平台仍可使用文字资料检索和不依赖 PowerPoint 的功能。

```powershell
git clone https://github.com/fuzong01-cloud/MATA.git
cd MATA
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
cd frontend
npm ci
cd ..
```

在 `.env` 中至少配置 `TEACHER_ACCESS_CODE` 和 `MEDIA_SIGNING_KEY`。要使用 AI 问答、代码分析和任务评分，还需配置 `QWEN_API_KEY`。课程资料在 `.env` 的 `COURSE_MATERIALS_DIR` 指定目录中准备好后，运行：

```powershell
.\.venv\Scripts\python.exe scripts\import_course_materials.py
```

分别在两个终端启动：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

```powershell
cd frontend
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>，API 文档位于 <http://127.0.0.1:8001/docs>。Vite 会将 `/api` 请求转发至后端。首次使用本地向量模型时会下载模型文件，时间取决于网络。

Linux/macOS 可用 `python3.12 -m venv .venv`、`.venv/bin/python` 代替 Windows 的 Python 命令。PPT 图像渲染需要另行适配，不能照搬 Windows PowerPoint 流程。

详细操作见 [使用说明](docs/user-guide.md)，模块、数据与接口见 [技术说明](docs/architecture.md)。

## 配置

| 配置项 | 作用 |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy 数据库连接，默认 SQLite 文件 |
| `COURSE_ZIP` | PPT 课程资料 ZIP 路径 |
| `COURSE_MATERIALS_DIR` | 原始资料目录，供导入脚本读取 |
| `EMBEDDING_MODEL` | 本地中文向量模型，默认 `BAAI/bge-small-zh-v1.5` |
| `QWEN_API_KEY` / `QWEN_BASE_URL` / `QWEN_MODEL` | 通义千问兼容接口配置 |
| `TEACHER_ACCESS_CODE` | 教师工作台及教师接口访问码 |
| `MEDIA_SIGNING_KEY` | 学生上传图片链接签名密钥 |
| `FRONTEND_ORIGIN` / `BACKEND_PORT` | 前端来源及后端监听端口 |

`.env.example` 只有示例值；不要把真实 `.env`、学生资料或课程原件提交到 GitHub。模型请求可能包含当前问题、代码、上传图片及相关课程资料，并产生 API 用量。

## 常用命令

```powershell
# 导入课程原始资料
.\.venv\Scripts\python.exe scripts\import_course_materials.py

# 在已安装 PowerPoint 的 Windows 上建立 PPT 页面图像索引
.\.venv\Scripts\python.exe scripts\import_visuals.py

# 构建前端
cd frontend
npm run build
```

## 项目结构

```text
backend/app/agents/       问答调度、模型调用、离线回退
backend/app/api/          请求与响应结构
backend/app/database/     SQLAlchemy 模型、连接与轻量迁移
backend/app/knowledge/    资料解析、索引、检索、任务提取
backend/app/main.py       FastAPI 路由与业务流程
frontend/src/             Vue 界面、文档渲染与样式
scripts/                  课程资料及页面图像导入
tests/                    后端测试
frontend/test/            文档渲染测试
docs/                     使用说明、技术说明、界面设计
```

## 数据与适用范围

默认数据库、索引、上传文件、课程原件和 `.env` 都在 `.gitignore` 中。教师删除一条提交后，学生和教师界面均不再显示该条记录；为保留审计线索，数据库中的记录和附件不会立刻物理销毁。学生主动删除自己的提交只会从学生列表隐藏，教师仍可查看。

AI 评分是学习反馈，不是正式成绩。代码分析只做静态阅读；截图和代码无法证明实际硬件或运行效果。教师访问码与浏览器学生标识只适合本机演示，公开部署需要正式身份认证、权限控制、文件扫描和备份策略。
