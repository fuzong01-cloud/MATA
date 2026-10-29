from __future__ import annotations

import ast
import re
from pathlib import Path
from dataclasses import dataclass


GUIDANCE_TERMS = ("怎么", "如何", "步骤", "实操", "配置", "接线", "报错", "失败", "无法", "排查", "不工作", "不能")
WIRING_TERMS = ("接线", "连线", "怎么接", "如何接", "接法")
SPECIFIC_EQUIPMENT_TERMS = (
    "adam", "烟雾", "火焰", "lcd", "数码管", "气象站", "风速", "二氧化碳", "co2", "co₂",
    "大气压力", "继电器", "补光灯", "报警灯", "火灾报警", "水温", "液位", "土壤",
)


@dataclass(frozen=True)
class AgentResult:
    agent: str
    answer: str
    status: str
    trace: list[str]


def choose_agent(question: str) -> str:
    return "experiment_guide" if any(term in question for term in GUIDANCE_TERMS) else "course_qa"


def plan_agents(question: str) -> list[str]:
    """Route a question to one specialist, or two for a concept plus procedure."""
    guidance = any(term in question for term in GUIDANCE_TERMS)
    concept = any(term in question for term in ("为什么", "原理", "区别", "是什么", "解释", "作用"))
    if guidance and concept:
        return ["course_qa", "experiment_guide"]
    return ["experiment_guide"] if guidance else ["course_qa"]


def respond_smalltalk(question: str) -> AgentResult | None:
    """Reply to common conversational turns without pretending they are course facts."""
    normalized = re.sub(r"[\s，。！？!?、,.~～]+", "", question.lower())
    if any(term in normalized for term in ("你是谁", "你是什么", "你是做什么的", "你叫什么")):
        answer = ("我是《物联网综合实训课程》的 AI 助教，可以陪你多轮交流、查课程 PPT、整理实验步骤，"
                  "也能检查 Python 语法。课程知识问题会尽量附上 PPT 文件和页码；资料没有说明的内容，我会直接告诉你。")
    elif any(term in normalized for term in ("你会什么", "你能做什么", "可以做什么", "有什么功能")):
        answer = ("我可以回答课程相关问题、根据 PPT 整理实验步骤和接线信息，也可以做 Python 语法检查。"
                  "你可以直接描述问题；如果我没理解，会继续问你需要补充什么。")
    elif any(term in normalized for term in ("谢谢", "多谢", "辛苦了")):
        answer = "不客气！还想继续看哪个课程问题，直接接着问我就行。"
    elif normalized in {"你好吗", "你还好吗"}:
        answer = "我在，可以继续帮你查课程资料。你最近在做哪个模块或设备实验？"
    elif (normalized.startswith(("你好", "您好")) or
          normalized in {"嗨", "哈喽", "hello", "hi", "在吗", "早上好", "下午好", "晚上好"}):
        answer = "你好！我是课程 AI 助教。你可以问我课件知识、实验步骤或设备接线；也可以直接接着前面的对话追问。"
    else:
        return None
    return AgentResult("course_qa", answer, "answered_general", ["识别为日常对话并直接回应"])


def retrieval_query(question: str, module: str | None) -> str:
    """Expand a narrow troubleshooting query using terms printed in these course slides."""
    if (module == "Android开发" or "Android" in question) and "云平台" in question and any(
        term in question for term in ("无法", "失败", "报错", "连不上", "不能访问")
    ):
        return question + " 网络权限 INTERNET usesCleartextTraffic SecurityException Unable to resolve host Token Status onFailure 排雷演练"
    normalized = question.lower()
    asks_wiring = any(term in question for term in WIRING_TERMS)
    names_equipment = any(term in normalized for term in SPECIFIC_EQUIPMENT_TERMS)
    if asks_wiring and not names_equipment:
        return question + " 传感器 接线规范 ADAM4017 ADAM4150 24V GND RS485 Vin0+ DI1 DI2"
    return question


def is_ambiguous_wiring_question(question: str) -> bool:
    normalized = question.lower()
    return (any(term in question for term in WIRING_TERMS)
            and not any(term in normalized for term in SPECIFIC_EQUIPMENT_TERMS))


def _useful_lines(excerpt: str, question: str, limit: int = 4) -> list[str]:
    normalized_question = re.sub(r"[^\w\u4e00-\u9fff]+", "", question.lower())
    query_grams = {normalized_question[i:i + 2] for i in range(max(0, len(normalized_question) - 1))}
    lines = [re.sub(r"\s+", " ", line).strip() for line in excerpt.splitlines()]
    lines = [line for line in lines if 12 <= len(line) <= 350 and "北京农学院农林物联网系统综合实训课程组" not in line]
    def priority(line: str) -> tuple[int, int]:
        normalized_line = re.sub(r"[^\w\u4e00-\u9fff]+", "", line.lower())
        grams = {normalized_line[i:i + 2] for i in range(max(0, len(normalized_line) - 1))}
        return (len(query_grams & grams), -abs(len(line) - 100))
    lines.sort(key=priority, reverse=True)
    return lines[:limit]


def _guide_lines(excerpt: str, question: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in excerpt.splitlines()]
    actions = [line for line in lines if 8 <= len(line) <= 350 and any(term in line for term in (
        "请检查", "请重点排查", "必须", "配置：", "设置：", "操作：", "解决方案", "DNS 解析失败"
    ))]
    return actions[:3] if actions else _useful_lines(excerpt, question, 2)


def respond_offline(question: str, evidence: list[dict]) -> AgentResult:
    agent = choose_agent(question)
    trace = ["识别问题类型", "从课程 PPT 检索证据"]
    if is_ambiguous_wiring_question(question):
        candidates = "\n".join(
            f"- {item['filename']} · 第 {item['slide_number']} {item.get('unit_label', '页')}"
            for item in evidence[:3]
        )
        candidate_text = (f"\n\n我找到的候选课件页：\n{candidates}" if candidates else "")
        answer = (
            "我还不知道你指的是哪台设备或哪个实验，所以暂时不能确定接线方案。"
            f"{candidate_text}"
            "\n\n你问的是哪台设备或哪个实验？可以回复设备型号（例如 ADAM-4017 或 ADAM-4150），"
            "也可以告诉我模块名称，我接着帮你查。"
        )
        trace.append("接线问题缺少设备信息，列出候选课件页面请求澄清")
        return AgentResult(agent, answer, "needs_clarification", trace)
    if not evidence or evidence[0]["score"] < 0.50:
        answer = ("我暂时没在已导入的课程 PPT 中找到足够依据来确定答案。"
                  "你可以告诉我课程模块、设备型号或具体报错，我会接着帮你查；"
                  "也可以在新对话中换个说法再问。")
        return AgentResult(agent, answer, "insufficient_evidence", trace)
    top = evidence[:3]
    lines = []
    for item in top:
        selected = _guide_lines(item["excerpt"], question) if agent == "experiment_guide" else _useful_lines(item["excerpt"], question, 2)
        for line in selected:
            if line not in lines:
                lines.append(line)
    if not lines:
        return AgentResult(agent, "检索到了相关课件页，但该页没有足够可整理的文字，请打开来源 PPT 查看。", "insufficient_evidence", trace)
    lines = lines[:6 if agent == "experiment_guide" else 5]
    if agent == "experiment_guide":
        answer = "依据课件，可逐项核对：\n" + "\n".join(f"{index}. {line}" for index, line in enumerate(lines, 1))
    else:
        answer = "课件中相关内容：\n" + "\n".join(f"- {line}" for line in lines)
    answer += "\n\n以上是离线课程资料摘录与整理，具体操作请以所引原始资料为准。"
    trace.append(f"由{agent}整理课件内容")
    return AgentResult(agent, answer, "answered_from_slides", trace)


def analyze_python(code: str) -> dict:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        issue = {
            "line": exc.lineno or 1,
            "column": exc.offset or 1,
            "message": exc.msg,
            "source": (exc.text or "").strip(),
        }
        return {"language": "python", "status": "syntax_error", "summary": "发现 Python 语法错误。此检查不会运行代码。", "issues": [issue], "agent": "code_analysis"}
    functions = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assignments = sorted({target.id for node in ast.walk(tree)
                          if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                          for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                          if isinstance(target, ast.Name)})
    calls = sorted({ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)})
    structure = {"functions": functions[:30], "classes": classes[:20],
                 "assigned_variables": assignments[:40], "calls": calls[:40]}
    return {"language": "python", "status": "syntax_ok", "summary": "Python 语法检查通过；这不代表运行逻辑或实验结果正确。", "issues": [], "structure": structure, "agent": "code_analysis"}


def detect_code_language(code: str, filename: str | None = None) -> str:
    extension = Path(filename or "").suffix.lower()
    by_extension = {".py": "python", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp",
                    ".hpp": "cpp", ".java": "java", ".js": "javascript", ".jsx": "javascript",
                    ".html": "html", ".htm": "html", ".css": "css"}
    if extension in by_extension:
        return by_extension[extension]
    value = code.lstrip()
    if re.search(r"<!doctype html|<html\b|<head\b|<body\b", value, re.I):
        return "html"
    if re.search(r"\b(?:package|public\s+class|private\s+class|import\s+android\.)\b", value):
        return "java"
    if re.search(r"#include\s*<|\bint\s+main\s*\(", value):
        return "cpp" if re.search(r"std::|cout\s*<<|#include\s*<iostream>|\bclass\s+\w+", value) else "c"
    if re.search(r"\b(?:function\s+\w+|const\s+\w+\s*=|let\s+\w+\s*=|document\.|console\.)", value):
        return "javascript"
    if re.search(r"^\s*[@.#\w][^\n{}]*\{[^{}]*:[^{}]*;", value, re.M):
        return "css"
    return "python"


def analyze_code_locally(language: str, code: str) -> dict:
    if language == "python":
        return analyze_python(code)
    return {"language": language, "status": "not_checked",
            "summary": "本地未配置该语言的编译器或语法检查器；可由 AI 静态阅读并提出建议。代码不会被运行。",
            "issues": [], "agent": "code_analysis"}
