from app.knowledge.assignments import _extract_range, _format_task_content, _merge_split_code_fences


def test_assignment_catalog_does_not_truncate_long_descriptions_or_rubrics():
    lines = ["任务一：完整任务示例", "```python"]
    lines.extend("value = 'complete instructional line'" for _ in range(350))
    lines.extend(["```", "评分标准", "评分内容 " * 1200])

    task = _extract_range(lines, 0, len(lines), "test", "Web开发", "manual.docx")[0]

    assert len(task["description"]) > 9000
    assert task["description"].startswith("任务一：完整任务示例\n```python")
    assert task["description"].rstrip().endswith("```")
    assert len(task["rubric"]) > 5000


def test_legacy_embedded_c_macros_are_fenced_and_pipe_rows_become_a_table():
    source = """设备名称 | 型号/规格 | 用途说明
计算机一台 | | 安装编译环境进行代码开发
M3核心模块 | STM32F103VET6 | 主控模块
/*******************LED数码管显示*********************/
//PA7-H
#define LED_DB7_PIN_PORTGPIOA
#define LED_DB7_PIN_PORT_CLKRCC_APB2Periph_GPIOA
#define LED_DB7_PINGPIO_Pin_7
#define LED_DB7_InitLED_DB7_PIN_PORT_CLK,\\
LED_DB7_PIN_PORT,\\
LED_DB7_PIN,GPIO_Speed_2MHz,GPIO_Mode_Out_PP
"""

    formatted = _format_task_content(source, "嵌入式开发")

    assert "| 设备名称 | 型号/规格 | 用途说明 |\n| --- | --- | --- |" in formatted
    assert "```c\n/*******************LED数码管显示" in formatted
    assert "#define LED_DB7_PIN_PORTGPIOA" in formatted
    assert formatted.count("```") == 2


def test_embedded_task_repairs_fences_split_inside_macro_and_loop():
    source = """任务三：按键控制
（1）添加宏定义
```c
#define KEY1_InitPORT_CLK,\\
```
```c
KEY1_PORT,\\
KEY1_PIN,GPIO_Speed_2MHz,GPIO_Mode_IPU
```
（2）在 main 中加入循环
while(1)
{
if(KEY1==0)
{
delay_ms(10);//延时
}
}
```c
"""

    formatted = _format_task_content(source, "嵌入式开发")

    assert formatted.count("```") == 4
    assert "```c\n#define KEY1_InitPORT_CLK,\\\nKEY1_PORT,\\\nKEY1_PIN" in formatted
    assert "while(1)\n{\nif(KEY1==0)" in formatted
    assert "delay_ms(10);//延时" in formatted


def test_embedded_switch_case_and_default_stay_in_one_code_block():
    source = """switch(count_k1)
{
case 1: P_LAMP=1;break;
default: P_FAN=1;count_k1=0;break;
}
"""
    formatted = _format_task_content(source, "嵌入式开发")
    assert "case 1: P_LAMP=1;break;\ndefault: P_FAN=1;count_k1=0;break;" in formatted
    assert formatted.count("```") == 2


def test_join_split_web_code_blocks_without_breaking_url_paths():
    source = """```javascript
fetch(
```
```javascript
'/devices/1')
.then(response => response.json());
```
```javascript
const ratio = 8 / 2;
```
"""

    formatted = _merge_split_code_fences(source)

    assert formatted.count("```") == 4
    assert "fetch(\n'/devices/1')" in formatted
    assert "const ratio = 8 / 2;" in formatted
