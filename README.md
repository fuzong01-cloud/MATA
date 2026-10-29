# 《物联网综合实训课程》多智能体协同助教系统

本仓库按照开题报告建设本机演示版。课程资料、对话、代码分析记录、学习回顾与教师审核均使用 SQLite。本机演示知识库包含 44 份 PPT（628 页）、88 份 DOCX（指导手册、题库、课程讲义、实操脚本、任务说明、报告模板与评分标准）；628 页 PPT 均已建立文字与页面图像索引。已将根目录 `任务.pptx` 纳入跨模块任务资料，并以修改版第 4 讲替换旧版；尚未进行论文中的单 Agent／多 Agent 对比实验。课程原始文件、索引、数据库和上传内容不随代码仓库发布。

## 已实现

- 从课程资料 ZIP 导入 PPTX，保留课程模块、文件名、页码与每页提取状态（文字、空白、部分提取、失败）
- 按资料路径、模块、资料类别与课次整理课程脚本和补充文档；任务类检索会优先参考实操脚本与课程任务布置，模块检索同时包含通用课程任务
- 教师端可额外上传 PDF、DOCX；PDF 按真实页码、Word 按可追溯的文字片段建立索引。上传扫描 PDF 时可选用模型识别图片页文字，每次最多 20 页
- 同模块同名的教师上传资料更新后替换旧版及其向量索引，记录版本哈希变更；内容未变化时跳过重复处理。更新记录保留版本信息，不保留旧文件副本
- 使用本地 `BAAI/bge-small-zh-v1.5` 中文向量模型和 SQLite 向量表建立精确余弦检索索引
- 问题识别与调度：普通问题交由课程问答或实验指导 Agent；同时涉及原理和操作的问题分别调用两者，再由结果校验模块整合。调用过程保存在对话记录中
- 课程资料优先问答；证据不足时使用模型通用知识继续分析，课件候选页会与已确认依据区分。模型不可用时回退本地整理
- PPT 完整页面图像索引，以及学生现场图片上传。视觉问题可结合关联 PPT 页图像、学生图片和文字回答；图片随对话保存在本机，删除对话时清理
- 代码分析 Agent：Python 本地 AST 语法检查；Python、C、C++、Java、JavaScript、HTML、CSS 可用模型做静态阅读分析。代码不会运行或编译
- 学习评价 Agent：根据对话与代码检查记录生成过程性学习回顾，不输出正式成绩
- Vue 学生端：多轮对话、模块筛选、课件来源与弹窗预览、删除对话、代码分析、学习回顾
- 教师工作台：课件统计、资料导入、最近回答审核，以及任务提交的原文与附件复核、教师意见和最终分数
- 学生可登记姓名、学号和班级；同一浏览器后续提问、代码分析、任务提交与学习回顾按学生标识归集。教师端可按班级、模块和日期查看活动、任务提交及学生进度
- 学生“学习回顾”页汇总跨对话的提问、代码分析、模块活动和已提交任务的最新结果
- 教师资料管理、图像索引与回答审核使用访问码保护；资料列表显示内容哈希版本和导入日期
- 代码分析可自动识别常见语言并关联课程模块；Python 额外提取函数、类、赋值变量与调用的静态结构
- SQLite 数据库；此阶段不依赖 MySQL

## 环境与启动

使用 Python 3.12、Node.js 20+。在项目根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

可复制 `.env.example` 为 `.env` 修改课程 ZIP、原始资料目录和数据库路径。首次建立索引时会下载约 90 MB 的本地 Embedding 模型；之后可以离线运行。PPT 下载与页面图像重建依赖 `.env` 中配置的课程 ZIP。

系统仅使用通义千问 `qwen3.8-flash`，配置项为 `.env` 中的 `QWEN_API_KEY`、`QWEN_BASE_URL` 和 `QWEN_MODEL`。`.env` 已被 Git 忽略。模型调用可能发送当前问题、代码、学生上传的图片和相关课程资料，并产生 API 用量；不要提交真实密钥或在代码分析区粘贴敏感凭据。未配置模型时保留本地检索与 Python 语法检查。

教师工作台使用 `.env` 中的 `TEACHER_ACCESS_CODE`。当前本机配置已生成独立访问码；打开教师工作台时输入该值。`MEDIA_SIGNING_KEY` 用于保护学生上传图片的访问链接。学生在“我的信息”登记后，新学习记录按班级归集，最近对话、代码检查、作业提交和学习回顾按浏览器标识隔离。学生标识保存在浏览器本地，换浏览器需要重新登记。本机演示尚未提供正式账号登录与密码找回机制。

在 Windows 安装了 Microsoft PowerPoint 的电脑上，进入学生端点击“建立 PPT 页面图像索引”。系统会通过 PowerPoint 将完整幻灯片渲染成 PNG，包含图片以及 PPT 原生绘制的图形、流程图和接线图，文件保存在 `knowledge_base/processed/slide_images/`。页面预览可从资料依据中打开。用户提问涉及“图中”“接线图”“流程图”等视觉内容时，最多选取 2 张已检索页面图像和对应资料文字交给当前启用的模型；普通文字问题只发送检索文字。图像不会在导入时批量发送给模型。视觉问答会产生模型 API 用量。

将原始资料放到 `COURSE_MATERIALS_DIR` 指定的目录，再重建 PPT、DOCX 和任务资料索引：

```powershell
.\.venv\Scripts\python.exe scripts\import_course_materials.py
```

脚本会排除被 `-4改.pptx` 替代的旧 `-4.pptx`，将资料根目录的 `任务.pptx` 作为通用课程任务打包，并重新处理全部 Word 文档。逐课资料会保留模块、资料类别、课次和原始相对路径等检索元数据。完成后可在教师端使用“建立 PPT 页面图像索引”或执行 `scripts\import_visuals.py`。

启动后端：

```powershell
.\.venv\Scripts\python.exe backend\run.py
```

另开终端启动前端：

```powershell
cd frontend
npm run dev
```

访问 `http://127.0.0.1:5173`。接口文档位于 `http://127.0.0.1:8001/docs`。后端默认使用 8001 端口（可通过 `BACKEND_PORT` 修改），避开当前常见的 8000 端口冲突。

## 核心接口

| 接口 | 用途 |
| --- | --- |
| `POST /api/materials/import` | 从配置的 ZIP 导入课程 PPT |
| `POST /api/materials/upload` | 上传 PDF/DOCX 并增量建立索引，保留原始文件 |
| `DELETE /api/materials/{id}` | 删除上传的补充资料及索引 |
| `POST /api/knowledge/visuals/import` | 用本机 PowerPoint 建立各页图像索引 |
| `GET /api/materials` | 查看已导入资料 |
| `GET /api/materials/{id}/slides/{page}` | 查看原始页的文字和状态 |
| `GET /api/materials/{id}/slides/{page}/image` | 获取该页 PNG 预览 |
| `GET /api/materials/{id}/download` | 下载原始 PPT |
| `POST /api/knowledge/search` | 按问题和模块检索课件 |
| `POST /api/chat` | 多轮问答与学生图片分析；响应包含 Agent 调度过程、依据和回答方式 |
| `POST /api/code/analyze` | 自动识别语言、Python 本地语法与结构检查及 AI 静态代码分析 |
| `GET /api/code/reviews` | 查看本段会话的代码分析记录 |
| `POST /api/learning/summary` | 生成过程性学习回顾 |
| `GET /api/learning/summaries/{session_id}` | 查看学习回顾记录 |
| `GET /api/conversations` | 查看提问与调用记录 |
| `GET /api/conversations/sessions` | 查看会话列表 |
| `DELETE /api/conversations/{session_id}` | 删除会话、相关图片与学习记录 |
| `GET /api/teacher/overview` | 教师演示统计与最近回答 |
| `POST /api/teacher/reviews/{conversation_id}` | 保存教师审核状态和备注 |
| `GET /api/teacher/submissions/{id}` | 查看提交原文、附件和 AI 初评 |
| `POST /api/teacher/submissions/{id}/review` | 保存教师复核、意见与最终分数 |
| `GET /api/submission-files/{id}/{index}` | 学生本人或教师下载提交附件 |
| `GET/PUT /api/student/profile` | 读取或登记当前浏览器对应的学生信息 |
| `GET /api/student/progress` | 查看当前学生的跨对话学习与任务进度 |
| `GET /api/teacher/analytics` | 按班级、模块、日期查询学习活动与任务进度 |

`/api/chat` 的请求示例：

```json
{"question":"ADAM-4017 的 Vin0+ 连接什么？","module":"虚拟仿真"}
```

返回内容包含 `answer`、`agent`、`status`、`trace`、`mode` 和 `evidence`。每条证据包含 `filename`、`slide_number`、`excerpt`、`score` 和原始 PPT 下载地址。

## 范围说明

当前导入了所提供的 PPT 与 Word 课程资料。Word 的“片段”并非原始页码，扫描 PDF 图片页识别需教师主动勾选并调用已配置模型，低清图片仍需人工核对。代码静态分析不等同于编译或运行。学习回顾不代替教师评分。教师端访问码适用于本机演示，学生标识不是正式账号权限系统，不应直接发布到公网。课程资料、学生图片和模型输出均是数据，不作为系统指令执行；模型思考内容不会展示或保存。
