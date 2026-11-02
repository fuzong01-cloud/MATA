# 毕业设计实验复现说明

本目录实现开题报告中的检索、单/多 Agent、RAG 消融以及多模态和代码分析案例验证。**公开仓库不包含课程原文、题目正文、标注答案、图片或模型逐条输出。**本机 `private/` 保存案例与资料快照，`results/raw/` 保存逐次请求账本，均被 Git 忽略。

## 实验设置

- 同一个 `.env` 中的 `QWEN_MODEL` 用于所有模型组。文本 30 题：知识 8、操作 12、复合 10；图片 6 题；代码 6 题。
- 文本每题运行单 Agent＋RAG、单 Agent 无 RAG；10 道复合题额外运行课程问答、实验指导、整合三次调用。图片与代码案例各运行一次，共预定 **102 次模型请求**。
- 运行前从本机资料库冻结每题的标注课件页、当前 Top 5 检索结果、资料哈希和图像哈希。快照哈希写入每次请求登记。
- `runner.py` 在每次 API 调用**之前**将 `start` 事件落盘；中断后的未完成请求也占用额度，避免重复调用。上限为 120 次，SDK 自动重试已关闭。
- 同一账本只允许一个运行器进程。异常退出留下 `.lock` 时，先确认原进程已停止，再手动移除锁文件；未完成的 `start` 仍计入调用额度。
- 账本记录每次请求的状态、耗时、返回用量和原始回答。失败只记录异常类别，不自动重试。

## 运行

准备私有 `evaluation/private/cases.json`（格式见 `runner.py` 的 `freeze_cases`），确认课程资料和索引已导入，然后：

```powershell
.\.venv\Scripts\python.exe evaluation\runner.py freeze
.\.venv\Scripts\python.exe evaluation\runner.py run --max-new-calls 2
.\.venv\Scripts\python.exe evaluation\runner.py status
.\.venv\Scripts\python.exe evaluation\runner.py run
.\.venv\Scripts\python.exe evaluation\metrics.py --export-review
```

`freeze` 只允许首次创建快照。重做实验应在新的隔离副本中进行，不得覆盖已记录的快照或账本。`metrics.py` 生成公开的案例索引与汇总，人工复核表位于私有目录。

## 指标与复核

检索 `Recall@5` 要求 Top 5 至少包含人工指定的**同一文件、同一页**；来源文件命中率只要求同一文件。自动引用率仅检查回答中的 `[编号]` 是否指向本轮提供的候选，**不证明该页支持结论**。

对每条成功回答人工填写 `private/review.csv`：命中的关键点数（0 至该题总数）；有任一明确错误或无依据的课程专属断言时 `factual_error=1`，否则为 0；所有被引用的关键结论确由对应候选片段支持时 `source_support=1`，否则为 0；没有声称无法从材料确认的运行效果或设备细节时 `uncertainty_correct=1`，否则为 0。无 RAG 和代码组的 `source_support=NA`，不计入来源支持率。图片案例另检查图中可辨认信息，代码案例另检查错误定位；每行写简短理由。报告只在复核完成后把这些值作为质量结论；未复核项目保持空值。

公开 `results/summary.json` 含案例 ID、汇总值和快照哈希；原始材料与逐条输出不得提交。实验没有跨模型实测，也不代表真实硬件运行验证。
