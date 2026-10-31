import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import c from 'highlight.js/lib/languages/c'
import cpp from 'highlight.js/lib/languages/cpp'
import css from 'highlight.js/lib/languages/css'
import dos from 'highlight.js/lib/languages/dos'
import java from 'highlight.js/lib/languages/java'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import powershell from 'highlight.js/lib/languages/powershell'
import python from 'highlight.js/lib/languages/python'
import sql from 'highlight.js/lib/languages/sql'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'

const grammars = { bash, c, cpp, css, dos, java, javascript, json, powershell, python, sql, xml, yaml }
for (const [name, grammar] of Object.entries(grammars)) hljs.registerLanguage(name, grammar)

const languageAliases = {
  bat: 'dos', bash: 'bash', c: 'c', cc: 'cpp', cmd: 'dos', cpp: 'cpp', cxx: 'cpp', css: 'css', h: 'c', hpp: 'cpp',
  html: 'xml', htm: 'xml', java: 'java', js: 'javascript', json: 'json', powershell: 'powershell', ps1: 'powershell', py: 'python',
  python: 'python', sh: 'bash', shell: 'bash', sql: 'sql', xml: 'xml', xhtml: 'xml', yaml: 'yaml', yml: 'yaml',
}

const cCodeStart = /^\s*(?:#(?:include|define|ifdef|ifndef|endif|pragma)\b|(?:extern\s+|static\s+|const\s+|volatile\s+)*(?:void|int|char|float|double|uint\w+_t)\s+[*\w]+\s*(?:\[[^\]]*\]\s*)?(?:[=;(,\[]|$)|(?:if|else|for|while|switch|case|default)\s*[:(]?|[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:\+\+|--)\s*;|[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:=|\+=|-=)\s*.+;|[A-Za-z_]\w*(?:\s*->\s*\w+|\s*\.\s*\w+)?\s*\([^;]*\)\s*;)/
const cCodeLine = /^\s*(?:#(?:include|define|ifdef|ifndef|endif|pragma)\b.*|\/\/.*|\/\*.*|\*\/|(?:extern\s+|static\s+|const\s+|volatile\s+)*(?:void|int|char|float|double|uint\w+_t)\s+[*\w]+\s*(?:\[[^\]]*\]\s*)?(?:[=;(,\[]|$).*|(?:if|else|for|while|switch|case|default|return|break|continue)\b.*|[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:=|\+=|-=)\s*.+(?:;|\/\/.*)$|[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:\+\+|--)\s*;?\s*(?:\/\/.*)?$|[A-Za-z_]\w*(?:\s*->\s*\w+|\s*\.\s*\w+)?\s*\([^;]*\)\s*;?\s*(?:\/\/.*)?$|[{}]\s*;?\s*$)/

function fenceUnmarkedCCode(source) {
  const lines = source.split('\n')
  const output = []
  let inFence = false
  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      output.push(line)
      index += 1
      continue
    }
    if (inFence || !cCodeStart.test(line)) {
      output.push(line)
      index += 1
      continue
    }

    const end = index + 1
    let cursor = end
    while (cursor < lines.length && !/^\s*```/.test(lines[cursor])) {
      if (cCodeLine.test(lines[cursor])) {
        cursor += 1
      } else if (!lines[cursor].trim() && cursor + 1 < lines.length && cCodeLine.test(lines[cursor + 1])) {
        cursor += 1
      } else {
        break
      }
    }
    const block = lines.slice(index, cursor)
    const codeLines = block.filter(value => value.trim())
    if (codeLines.length >= 1 && codeLines.every(value => cCodeLine.test(value))) {
      output.push('```c', ...block, '```')
      index = cursor
    } else {
      output.push(line)
      index += 1
    }
  }
  return output.join('\n')
}

function restoreLegacySlashCodeLines(source) {
  const pythonPatterns = [
    /^@\w[\w.]*(?:\(.*\))?\s*$/,
    /^(?:async\s+)?(?:def|class)\s+\w+/,
    /^(?:try|except|finally|else|elif|if|for|while|with)\b.*:?$/,
    /^(?:return|raise|pass|break|continue|import|from)\b/,
    /^[\w.]+(?:\[[^\]]+\])?\s*=(?!=)/,
    /^[\w.]+\s*\(/,
  ]
  const htmlPattern = /^(?:<!doctype\b|<\/?[a-z][^>]*>|\{%.*%\}|\{\{.*\}\})/i
  const indentPython = lines => {
    if (lines.some(line => /^\s+\S/.test(line))) return lines
    let indent = 0
    const suites = []
    return lines.map(raw => {
      const line = raw.trim()
      if (!line) return ''
      const clause = /^(except\b|finally\b|elif\b|else\s*:)/.exec(line)
      if (clause) {
        const kinds = /^(?:except|finally)/.test(line) ? ['try'] : ['if', 'branch']
        while (suites.length && !kinds.includes(suites.at(-1).kind)) suites.pop()
        const parent = suites.pop()
        indent = parent ? parent.indent : Math.max(0, indent - 4)
      } else if (/\b\w+\.close\s*\(/.test(line) && suites.some(suite => suite.kind === 'try')) {
        while (['for', 'while', 'if', 'with'].includes(suites.at(-1)?.kind)) suites.pop()
        const parent = [...suites].reverse().find(suite => suite.kind === 'try')
        if (parent) indent = parent.indent + 4
      }
      const rendered = `${' '.repeat(indent)}${line}`
      const header = /^(?:async\s+)?(def|class|try|for|while|if|elif|else|with)\b.*:\s*$/.exec(line)
      if (header) {
        suites.push({ kind: header[1], indent })
        indent += 4
      } else if (clause && /^(?:except|finally)/.test(clause[1])) {
        suites.push({ kind: 'try', indent })
        indent += 4
      }
      return rendered
    })
  }
  return source.split('\n').flatMap(line => {
    const parts = line.split(/\s+\/\s+/).map(part => part.trim())
    if (parts.length < 4) return [line]

    const meaningful = parts.filter(Boolean)
    const htmlCount = meaningful.filter(part => htmlPattern.test(part)).length
    const isHtml = htmlCount >= 4 && htmlCount / meaningful.length >= 0.72 &&
      meaningful.some(part => /^(?:<!doctype\b|<html\b|\{%\s*extends\b)/i.test(part))
    const pythonCount = meaningful.filter(part => pythonPatterns.some(pattern => pattern.test(part))).length
    const isPython = pythonCount >= 4 && pythonCount / meaningful.length >= 0.6

    if (isHtml || isPython) {
      const language = isHtml ? 'html' : 'python'
      const codeLines = isPython ? indentPython(parts) : parts
      return [`\`\`\`${language}`, ...codeLines, '\`\`\`']
    }
    return [line]
  }).join('\n')
}

export function formatAssignmentText(content, module = '') {
  const normalized = restoreLegacySlashCodeLines(String(content || '').replace(/\r\n?/g, '\n'))
  const source = module === '嵌入式开发' ? fenceUnmarkedCCode(normalized) : normalized
  let inFence = false
  return source.split('\n').map(line => {
    if (/^\s*```/.test(line)) {
      inFence = !inFence
      return line
    }
    if (inFence) return line

    const value = line.trim()
    if (!value) return line
    const numberedList = value.match(/^[（(](\d+)[）)]\s*(.+)$/)
    if (numberedList) return `${numberedList[1]}. ${numberedList[2]}`
    const legacyHeading = value.match(/^【([^】]+)】$/)
    if (legacyHeading) return `### ${legacyHeading[1]}`

    const section = value.match(/^(?:\d+(?:\.\d+)*[.、]?\s*)?(任务(?:目标|目的|描述|准备|步骤|过程|要求|考核点|内容|背景(?:\/原理)?)|实现步骤|功能要求|验收标准|评分标准|常见(?:问题|错误)(?:与排错)?|注意事项)\s*[：:]?\s*(.*)$/)
    if (section) return `### ${section[1]}${section[2] ? `\n\n${section[2]}` : ''}`
    if (/^步骤\s*\d+\s*[：:]/.test(value)) return `### ${value}`
    const numberedHeading = value.match(/^(\d+(?:\.\d+)+|\d+)\s+([^。；;]{2,34})$/)
    if (numberedHeading && !/^[（(]\d+[）)]/.test(value)) return `### ${numberedHeading[1]} ${numberedHeading[2]}`
    return line
  }).join('\n')
}

export function createCourseMarkdown({ linkify = false } = {}) {
  const markdown = new MarkdownIt({ html: false, linkify, breaks: true })
  markdown.renderer.rules.fence = (tokens, index) => {
    const token = tokens[index]
    const requestedLanguage = token.info.trim().split(/\s+/, 1)[0].toLowerCase()
    const language = languageAliases[requestedLanguage]
    let highlighted = ''
    let detectedLanguage = language
    if (language) {
      highlighted = hljs.highlight(token.content, { language, ignoreIllegals: true }).value
    } else if (!requestedLanguage) {
      const detected = hljs.highlightAuto(token.content)
      highlighted = detected.value
      detectedLanguage = detected.language
    }
    const className = detectedLanguage ? ` class="hljs language-${detectedLanguage}"` : ' class="hljs"'
    const code = highlighted || markdown.utils.escapeHtml(token.content)
    return `<div class="copy-code-block"><button type="button" class="copy-code-button" data-copy-code>复制代码</button><pre><code${className}>${code}</code></pre></div>\n`
  }
  return markdown
}
