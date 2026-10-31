import test from 'node:test'
import assert from 'node:assert/strict'
import { createCourseMarkdown, formatAssignmentText } from '../src/document-rendering.js'

test('assignment sections become headings without rewriting command lines', () => {
  const source = '任务要求\n步骤 1：创建目录\nmkdir demog3\ncd demog3'
  const formatted = formatAssignmentText(source)
  assert.match(formatted, /^### 任务要求/m)
  assert.match(formatted, /^### 步骤 1：创建目录/m)
  assert.match(formatted, /^mkdir demog3$/m)
  assert.match(formatted, /^cd demog3$/m)
})

test('numbered manual sections and parenthesized requirements become headings and lists', () => {
  const source = '1 任务描述\n正文\n2 基本要求\n（1）要求一\n（2）要求二\n4.1 硬件连接与配置\n步骤 2：运行程序'
  const formatted = formatAssignmentText(source)
  assert.match(formatted, /^### 任务描述$/m)
  assert.match(formatted, /^### 2 基本要求$/m)
  assert.match(formatted, /^1\. 要求一$/m)
  assert.match(formatted, /^2\. 要求二$/m)
  assert.match(formatted, /^### 4\.1 硬件连接与配置$/m)
  assert.match(formatted, /^### 步骤 2：运行程序$/m)
})

test('unfenced embedded C functions are restored as copyable code blocks', () => {
  const source = `6. 在main.c的主函数外增加一自定义显示函数：
void ShowSetMenu(void)
{
char xValue[30] = "";
char yValue[30] = "";
LCD_Clr();
LCD_WriteChinese(0,0,WEN);
sprintf(xValue, "%d",x);
LCD_WriteEnglishString(0,80,(uint8_t *)xValue);
}`
  const formatted = formatAssignmentText(source, '嵌入式开发')
  const html = createCourseMarkdown().render(formatted)
  assert.match(formatted, /```c\nvoid ShowSetMenu\(void\)/)
  assert.match(html, /class="copy-code-block"[\s\S]*<pre><code[^>]*class="hljs language-c"/)
  assert.match(html, /data-copy-code/)
})

test('unfenced embedded declarations and statements between prose are all code blocks', () => {
  const source = `extern void SMGSONGXIAN(uint8_t *buf, uint8_t i);
extern uint8_t xssj;
并定义变量：
uint16_t T_LED_MS = 0;
uint8_t buf_led[8];
其次，在void TIM2_IRQHandler(void)函数中添加如下代码：
T_LED_MS++;
if(T_LED_MS>=8)
{
T_LED_MS=0;
}
buf_led[0]= xssj /10000000+0x30;
buf_led[1]=( xssj %10000000)/1000000+0x30;
buf_led[2]=( xssj %1000000)/100000+0x30;
buf_led[3]=( xssj %100000)/10000+0x30;
buf_led[4]=( xssj %10000)/1000+0x30;
buf_led[5]=( xssj %1000)/100+0x30;
buf_led[6]=( xssj %100)/10+0x30;
buf_led[7]= xssj %10+0x30;
SMGSONGXIAN(buf_led,T_LED_MS);`
  const formatted = formatAssignmentText(source, '嵌入式开发')
  const html = createCourseMarkdown().render(formatted)
  assert.match(formatted, /```c\nextern void SMGSONGXIAN/)
  assert.match(formatted, /```c\nuint16_t T_LED_MS = 0;/)
  assert.match(formatted, /```c\nT_LED_MS\+\+;/)
  assert.match(formatted, /```c\nT_LED_MS\+\+;[\s\S]*buf_led\[0\]= xssj/)
  assert.match(formatted, /buf_led\[7\]= xssj %10\+0x30;\nSMGSONGXIAN\(buf_led,T_LED_MS\);\n```/)
  assert.match(html, /copy-code-block/g)
})

test('fenced code preserves hash comments, indentation, slash expressions, URLs and paths', () => {
  const markdown = createCourseMarkdown()
  const source = [
    '```python',
    'def main():',
    '    # do not treat this as a heading',
    '    path = "C:/work/demo"',
    '    url = "https://example.test/api"',
    '    value = 4 / 2',
    '```',
  ].join('\n')
  const html = markdown.render(source)
  assert.match(html, /class="hljs language-python"/)
  assert.match(html, /    <span class="hljs-comment"># do not treat this as a heading<\/span>/)
  assert.match(html, /C:\/work\/demo/)
  assert.match(html, /https:\/\/example\.test\/api/)
  assert.match(html, /<span class="hljs-number">4<\/span> \/ <span class="hljs-number">2<\/span>/)
  assert.match(html, /data-copy-code/)
  assert.doesNotMatch(html, /<h[1-6][^>]*># do not treat/)
})

test('supports tables, quotes, ordered lists and safe inline code', () => {
  const markdown = createCourseMarkdown()
  const html = markdown.render([
    '| 命令 | 作用 |',
    '| --- | --- |',
    '| `python -m venv .venv` | 创建虚拟环境 |',
    '',
    '1. 安装依赖',
    '2. 启动服务',
    '',
    '> 注意：不要把课程示例代码直接作为标题。',
    '',
    '![传感器接线图](https://example.test/wiring.png)',
    '',
    '<script>alert(1)</script>',
  ].join('\n'))
  assert.match(html, /<table>/)
  assert.match(html, /<ol>/)
  assert.match(html, /<blockquote>/)
  assert.match(html, /<img src="https:\/\/example\.test\/wiring\.png" alt="传感器接线图">/)
  assert.match(html, /<code>python -m venv \.venv<\/code>/)
  assert.match(html, /&lt;script&gt;/)
  assert.doesNotMatch(html, /<script>/)
})

test('formatting does not split slash paths or transform fenced hashes', () => {
  const source = '路径 C:/work/demo 和 URL https://example.test\n```c\n#include <stdio.h>\n```'
  const formatted = formatAssignmentText(source)
  assert.equal(formatted, source)
})

test('assignment view restores legacy slash-joined code from task manuals', () => {
  const source = "步骤 3：查询历史数据\n@app.route('/sensor_historical_data') / def sensor_historical_data(): / try: / conn = sqlite3.connect('sensor_data.db') / rows = conn.cursor().fetchall() / for row in rows: / records.append(row) / conn.close() / return render_template('history.html', records=records) / except Exception as e: / return f'Error: {str(e)}'"
  const formatted = formatAssignmentText(source)
  const html = createCourseMarkdown().render(formatted)

  assert.match(formatted, /```python\n@app\.route/)
  assert.match(formatted, /    try:\n        conn =/)
  assert.match(html, /<pre><code class="hljs language-python">/)
  assert.match(html, /<span class="hljs-keyword">def<\/span>/)
  assert.match(html, /sensor_historical_data/)
  assert.match(html, /data-copy-code/)
  assert.doesNotMatch(html, /@app\.route[^<]* \/ def sensor_historical_data/)
})

test('legacy slash recovery keeps prose URLs paths and division unchanged', () => {
  const source = 'See C:/work/demo and https://example.test/a/b; calculate 4 / 2.'
  assert.equal(formatAssignmentText(source), source)
})
