<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const modules = ['全部模块', '嵌入式开发', 'Web开发', 'Android开发', '虚拟仿真']
const selectedModule = ref('全部模块')
const activeTab = ref('ask')
const question = ref('')
const pendingQuestion = ref('')
const code = ref('')
const codeLanguage = ref('auto')
const codeModule = ref('')
const codeContext = ref('')
const codeImage = ref(null)
const assignmentData = ref({ items: [], modules: [] })
const assignmentModule = ref('全部模块')
const assignmentQuery = ref('')
const selectedAssignment = ref(null)
const assignmentWorkText = ref('')
const assignmentReportText = ref('')
const assignmentWorkFiles = ref([])
const assignmentReportFiles = ref([])
const assignmentGrade = ref(null)
const assignmentSubmissions = ref([])
const assignmentRevisionId = ref(null)
const retainedAssignmentFiles = ref([])
const selectedSubmissionId = ref(null)
const assignmentTutorTurns = ref([])
const assignmentTutorInput = ref('')
const assignmentTutorLoading = ref(false)
const assignmentSubmitting = ref(false)
const assignmentWorkInput = ref(null)
const assignmentReportInput = ref(null)
const codeLanguages = [
  { value: 'auto', label: '自动识别' },
  { value: 'python', label: 'Python' }, { value: 'c', label: 'C' },
  { value: 'cpp', label: 'C++' }, { value: 'java', label: 'Java / Android' },
  { value: 'javascript', label: 'JavaScript' }, { value: 'html', label: 'HTML' },
  { value: 'css', label: 'CSS' },
]
const sessionId = ref(localStorage.getItem('teaching-assistant-session') || crypto.randomUUID())
localStorage.setItem('teaching-assistant-session', sessionId.value)
const messages = ref([])
const codeResult = ref(null)
const codeHistory = ref([])
const codeThread = ref(null)
const codeTurns = computed(() => [...codeHistory.value].reverse())
const learningSummaries = ref([])
const studentProgress = ref(null)
const studentKey = ref(localStorage.getItem('teaching-assistant-student') || crypto.randomUUID())
localStorage.setItem('teaching-assistant-student', studentKey.value)
const studentProfile = ref({ name: '', student_number: '', class_name: '', registered: false })
const profileSaving = ref(false)
const teacherCode = ref(sessionStorage.getItem('teaching-assistant-teacher-code') || '')
const teacherCodeInput = ref('')
const teacherData = ref(null)
const teacherAnalytics = ref(null)
const teacherFilter = ref({ class_name: '', module: '', from_date: '', to_date: '' })
const teacherMaterialFile = ref(null)
const teacherMaterialInput = ref(null)
const teacherMaterialModule = ref('嵌入式开发')
const teacherMaterialOcr = ref(false)
const materialUploading = ref(false)
const teacherImportMessage = ref('')
const selectedTeacherQuestion = ref(null)
const selectedTeacherSubmission = ref(null)
const submissionReviewStatus = ref('pending')
const submissionReviewNote = ref('')
const submissionFinalScore = ref('')
const reviewStatus = ref('pending')
const reviewNote = ref('')
const status = ref(null)
const sessions = ref([])
const sourceDetail = ref(null)
const selectedImage = ref(null)
const imageInput = ref(null)
const messageList = ref(null)
const loading = ref(false)
const importing = ref(false)
const visualImporting = ref(false)
const error = ref('')
const sampleQuestions = [
  'Flask 登录表单的字段名为什么要和 request.form 一致？',
  'Android 应用无法访问云平台，应该怎样排查？',
  'SQLite 中如何查询传感器历史数据？',
  '农业气象站的 ADAM-4017 应该怎样接线？',
]
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
markdown.renderer.rules.fence = (tokens, index, options, _env, renderer) => {
  const token = tokens[index]
  const language = token.info.trim().split(/\s+/, 1)[0]
  const className = language ? ` class="language-${renderer.utils.escapeHtml(language)}"` : ''
  return `<div class="copy-code-block"><button type="button" class="copy-code-button" data-copy-code>复制代码</button><pre><code${className}>${renderer.utils.escapeHtml(token.content)}</code></pre></div>`
}

const moduleValue = computed(() => selectedModule.value === '全部模块' ? null : selectedModule.value)
const visibleAssignments = computed(() => assignmentData.value.items.filter(item => {
  const moduleMatches = assignmentModule.value === '全部模块' || item.module === assignmentModule.value
  const query = assignmentQuery.value.trim().toLowerCase()
  return moduleMatches && (!query || `${item.title} ${item.source} ${item.description} ${item.rubric}`.toLowerCase().includes(query))
}))
const selectedAssignmentSubmission = computed(() => assignmentSubmissions.value.find(
  item => item.submission_id === selectedSubmissionId.value) || null)
const isEmptyThread = computed(() => activeTab.value === 'ask' && messages.value.length === 0 && !pendingQuestion.value)

function responseLabel(mode) {
  const labels = {
    model_grounded: '根据课程 PPT 回答',
    model_multimodal: '结合 PPT 文字与图像回答',
    model_general: 'AI 补充分析',
    multi_agent: '多角色协同回答',
    offline_fallback: 'AI 暂时不可用 · 本地回复',
    clarification: '需要补充信息',
    general: '日常交流',
  }
  if (labels[mode]) return labels[mode]
  if (mode?.endsWith('_grounded')) return labels.model_grounded
  if (mode?.endsWith('_multimodal')) return labels.model_multimodal
  if (mode?.endsWith('_general')) return labels.model_general
  return '课程助教'
}

function renderMarkdown(content) {
  return DOMPurify.sanitize(markdown.render(content || ''))
}

async function handleCodeCopy(event) {
  const button = event.target.closest?.('[data-copy-code]')
  if (!button) return
  const codeElement = button.parentElement?.querySelector('pre code')
  if (!codeElement) return
  try {
    await navigator.clipboard.writeText(codeElement.textContent || '')
    button.textContent = '已复制'
    window.setTimeout(() => { button.textContent = '复制代码' }, 1400)
  } catch {
    error.value = '复制失败，请选择代码后使用 Ctrl+C。'
  }
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  headers.set('X-Student-Key', studentKey.value)
  if (teacherCode.value) headers.set('X-Teacher-Code', teacherCode.value)
  const response = await fetch(path, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || `请求失败 (${response.status})`)
  return payload
}

async function loadThread(id) {
  messages.value = await request(`/api/conversations?limit=100&session_id=${encodeURIComponent(id)}`)
  await scrollToLatest()
}

async function refresh() {
  try {
    const [system, threadList, thread, profile] = await Promise.all([
      request('/api/status'),
      request('/api/conversations/sessions'),
      request(`/api/conversations?limit=100&session_id=${encodeURIComponent(sessionId.value)}`),
      request('/api/student/profile'),
    ])
    status.value = system
    sessions.value = threadList
    messages.value = thread
    studentProfile.value = profile
    await scrollToLatest()
  } catch (cause) {
    error.value = `后端尚未启动：${cause.message}`
  }
}

async function saveStudentProfile() {
  if (profileSaving.value) return
  profileSaving.value = true
  error.value = ''
  try {
    studentProfile.value = await request('/api/student/profile', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(studentProfile.value),
    })
  } catch (cause) {
    error.value = cause.message
  } finally {
    profileSaving.value = false
  }
}

async function unlockTeacher() {
  if (!teacherCodeInput.value.trim()) return
  teacherCode.value = teacherCodeInput.value.trim()
  sessionStorage.setItem('teaching-assistant-teacher-code', teacherCode.value)
  teacherCodeInput.value = ''
  await openTeacher()
}

function lockTeacher() {
  teacherCode.value = ''
  teacherData.value = null
  teacherAnalytics.value = null
  selectedTeacherSubmission.value = null
  sessionStorage.removeItem('teaching-assistant-teacher-code')
}

async function selectTeacherSubmission(item) {
  error.value = ''
  try {
    const detail = await request(`/api/teacher/submissions/${item.id}`)
    selectedTeacherSubmission.value = detail
    submissionReviewStatus.value = detail.teacher_review_status || 'pending'
    submissionReviewNote.value = detail.teacher_review_note || ''
    submissionFinalScore.value = detail.teacher_final_score ?? ''
  } catch (cause) {
    error.value = cause.message
  }
}

async function saveSubmissionReview() {
  if (!selectedTeacherSubmission.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    await request(`/api/teacher/submissions/${selectedTeacherSubmission.value.id}/review`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: submissionReviewStatus.value,
        note: submissionReviewNote.value,
        final_score: submissionReviewStatus.value !== 'approved' || submissionFinalScore.value === '' ? null : Number(submissionFinalScore.value) }),
    })
    await selectTeacherSubmission(selectedTeacherSubmission.value)
    await loadTeacherAnalytics()
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

async function downloadSubmissionFile(submissionId, attachment) {
  error.value = ''
  try {
    const headers = new Headers({ 'X-Student-Key': studentKey.value })
    if (teacherCode.value) headers.set('X-Teacher-Code', teacherCode.value)
    const response = await fetch(`/api/submission-files/${submissionId}/${attachment.index}`, { headers })
    if (!response.ok) throw new Error(`附件下载失败 (${response.status})`)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.filename
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 30000)
  } catch (cause) {
    error.value = cause.message
  }
}

async function openProgress() {
  activeTab.value = 'progress'
  error.value = ''
  try {
    const [summaries, progress] = await Promise.all([
      request(`/api/learning/summaries/${encodeURIComponent(sessionId.value)}`),
      request('/api/student/progress'),
    ])
    learningSummaries.value = summaries
    studentProgress.value = progress
  } catch (cause) {
    error.value = cause.message
  }
}

async function openCode() {
  activeTab.value = 'code'
  error.value = ''
  try {
    codeHistory.value = await request(`/api/code/reviews?session_id=${encodeURIComponent(sessionId.value)}`)
    codeResult.value = codeHistory.value[0] || null
    code.value = codeHistory.value[0]?.code || ''
    if (codeHistory.value[0]?.language) codeLanguage.value = codeHistory.value[0].language
    codeModule.value = codeHistory.value[0]?.module || ''
  } catch (cause) {
    error.value = cause.message
  }
}

async function openAssignments() {
  activeTab.value = 'assignments'
  error.value = ''
  try {
    assignmentData.value = await request('/api/assignments')
  } catch (cause) {
    error.value = cause.message
  }
}

async function selectAssignment(item) {
  selectedAssignment.value = item
  assignmentWorkText.value = ''
  assignmentReportText.value = ''
  assignmentWorkFiles.value = []
  assignmentReportFiles.value = []
  assignmentGrade.value = null
  assignmentRevisionId.value = null
  retainedAssignmentFiles.value = []
  selectedSubmissionId.value = null
  assignmentTutorTurns.value = []
  assignmentTutorInput.value = ''
  try {
    const [detail, submissions] = await Promise.all([
      request(`/api/assignments/${encodeURIComponent(item.id)}`),
      request(`/api/assignments/${encodeURIComponent(item.id)}/submissions?session_id=${encodeURIComponent(sessionId.value)}`),
    ])
    selectedAssignment.value = detail
    assignmentSubmissions.value = submissions
    if (assignmentSubmissions.value.length) {
      assignmentGrade.value = assignmentSubmissions.value[0].evaluation
      selectedSubmissionId.value = assignmentSubmissions.value[0].submission_id
    }
  } catch (cause) {
    error.value = cause.message
  }
}

function readSubmissionFile(file) {
  return new Promise((resolve, reject) => {
    const maxBytes = file.type.startsWith('image/') ? 5_000_000 : 10_000_000
    if (file.size > maxBytes) return reject(new Error(`${file.name} 超过 ${file.type.startsWith('image/') ? '5' : '10'} MB。`))
    const reader = new FileReader()
    reader.onload = () => resolve({ filename: file.name || 'clipboard-image.png', data_url: String(reader.result) })
    reader.onerror = () => reject(new Error(`读取 ${file.name} 失败。`))
    reader.readAsDataURL(file)
  })
}

async function addSubmissionFiles(event, group) {
  const files = [...(event.target.files || [])]
  const target = group === 'work' ? assignmentWorkFiles : assignmentReportFiles
  try {
    const converted = await Promise.all(files.map(readSubmissionFile))
    const maxFiles = group === 'work' ? 8 : 4
    const retainedCount = retainedAssignmentFiles.value.filter(item => item.group === group).length
    if (target.value.length + converted.length + retainedCount > maxFiles) throw new Error('作品或报告附件数量已达上限。')
    target.value.push(...converted)
    error.value = ''
  } catch (cause) {
    error.value = cause.message
  } finally {
    event.target.value = ''
  }
}

function pasteAssignmentImage(event, group) {
  let file = [...(event.clipboardData?.items || [])]
    .find(item => ['image/png', 'image/jpeg', 'image/webp'].includes(item.type))?.getAsFile()
  if (!file) return
  event.preventDefault()
  if (assignmentSubmitting.value) return
  if (!file.name) file = new File([file], 'clipboard-image.png', { type: file.type })
  addSubmissionFiles({ target: { files: [file], value: '' } }, group)
}

function submissionPayload(files) {
  return files.map(file => ({ filename: file.filename,
    data_base64: file.data_url.split(',', 2)[1] || '' }))
}

async function submitAssignment() {
  if (!selectedAssignment.value || assignmentSubmitting.value) return
  assignmentSubmitting.value = true
  error.value = ''
  try {
    const assignmentPath = `/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}`
    const isRevision = assignmentRevisionId.value !== null
    const endpoint = isRevision ? `${assignmentPath}/submissions/${assignmentRevisionId.value}` : `${assignmentPath}/grade`
    const result = await request(endpoint, {
      method: isRevision ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value, student_key: studentKey.value,
        work_text: assignmentWorkText.value, report_text: assignmentReportText.value,
        work_files: submissionPayload(assignmentWorkFiles.value),
        report_files: submissionPayload(assignmentReportFiles.value),
        retain_attachment_indexes: retainedAssignmentFiles.value.map(file => file.index) }),
    })
    assignmentGrade.value = result
    selectedSubmissionId.value = result.submission_id
    assignmentSubmissions.value = await request(`${assignmentPath}/submissions?session_id=${encodeURIComponent(sessionId.value)}`)
    assignmentRevisionId.value = null
    retainedAssignmentFiles.value = []
    assignmentWorkFiles.value = []
    assignmentReportFiles.value = []
  } catch (cause) {
    error.value = cause.message
  } finally {
    assignmentSubmitting.value = false
  }
}

function newAssignmentSubmission() {
  assignmentRevisionId.value = null
  retainedAssignmentFiles.value = []
  assignmentWorkText.value = ''
  assignmentReportText.value = ''
  assignmentWorkFiles.value = []
  assignmentReportFiles.value = []
  error.value = ''
}

function showAssignmentSubmission(item) {
  assignmentGrade.value = item.evaluation
  selectedSubmissionId.value = item.submission_id
}

async function reviseAssignmentSubmission(item) {
  if (!selectedAssignment.value || assignmentSubmitting.value) return
  error.value = ''
  try {
    const detail = await request(`/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}/submissions/${item.submission_id}?session_id=${encodeURIComponent(sessionId.value)}`)
    assignmentRevisionId.value = item.submission_id
    assignmentWorkText.value = detail.work_text || ''
    assignmentReportText.value = detail.report_text || ''
    retainedAssignmentFiles.value = detail.attachments || []
    assignmentWorkFiles.value = []
    assignmentReportFiles.value = []
    showAssignmentSubmission(item)
  } catch (cause) {
    error.value = cause.message
  }
}

async function deleteAssignmentSubmission(item) {
  if (!selectedAssignment.value || assignmentSubmitting.value) return
  if (!window.confirm('删除这次提交及其附件？删除后无法恢复。')) return
  error.value = ''
  try {
    await request(`/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}/submissions/${item.submission_id}?session_id=${encodeURIComponent(sessionId.value)}`, { method: 'DELETE' })
    assignmentSubmissions.value = assignmentSubmissions.value.filter(record => record.submission_id !== item.submission_id)
    if (assignmentRevisionId.value === item.submission_id) newAssignmentSubmission()
    if (selectedSubmissionId.value === item.submission_id) {
      assignmentGrade.value = assignmentSubmissions.value[0]?.evaluation || null
      selectedSubmissionId.value = assignmentSubmissions.value[0]?.submission_id || null
    }
  } catch (cause) {
    error.value = cause.message
  }
}

async function regradeAssignment() {
  const previous = selectedAssignmentSubmission.value
  if (!selectedAssignment.value || !previous?.submission_id || assignmentSubmitting.value) return
  assignmentSubmitting.value = true
  error.value = ''
  try {
    const result = await request(`/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}/submissions/${previous.submission_id}/regrade?session_id=${encodeURIComponent(sessionId.value)}`, { method: 'POST' })
    assignmentGrade.value = result
    selectedSubmissionId.value = result.submission_id
    assignmentSubmissions.value = await request(`/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}/submissions?session_id=${encodeURIComponent(sessionId.value)}`)
  } catch (cause) {
    error.value = cause.message
  } finally {
    assignmentSubmitting.value = false
  }
}

async function askAssignment() {
  const prompt = assignmentTutorInput.value.trim()
  if (!prompt || !selectedAssignment.value || assignmentTutorLoading.value) return
  assignmentTutorLoading.value = true
  assignmentTutorTurns.value.push({ role: 'user', content: prompt })
  assignmentTutorInput.value = ''
  try {
    const result = await request(`/api/assignments/${encodeURIComponent(selectedAssignment.value.id)}/questions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: prompt,
        history: assignmentTutorTurns.value.slice(-9, -1).map(turn => ({ role: turn.role, content: turn.content })) }),
    })
    assignmentTutorTurns.value.push({ role: 'assistant', content: result.answer })
  } catch (cause) {
    assignmentTutorTurns.value.pop()
    assignmentTutorInput.value = prompt
    error.value = cause.message
  } finally {
    assignmentTutorLoading.value = false
  }
}

async function openTeacher() {
  activeTab.value = 'teacher'
  error.value = ''
  if (!teacherCode.value) return
  try {
    const [overview, analytics] = await Promise.all([
      request('/api/teacher/overview'),
      request(`/api/teacher/analytics?${new URLSearchParams(Object.entries(teacherFilter.value).filter(([, value]) => value)).toString()}`),
    ])
    teacherData.value = overview
    teacherAnalytics.value = analytics
    if (selectedTeacherQuestion.value) {
      selectedTeacherQuestion.value = teacherData.value.questions.find(
        item => item.id === selectedTeacherQuestion.value.id) || null
    }
  } catch (cause) {
    error.value = cause.message
    if (cause.message.includes('访问码')) lockTeacher()
  }
}

async function loadTeacherAnalytics() {
  if (!teacherCode.value) return
  try {
    teacherAnalytics.value = await request(`/api/teacher/analytics?${new URLSearchParams(Object.entries(teacherFilter.value).filter(([, value]) => value)).toString()}`)
  } catch (cause) {
    error.value = cause.message
  }
}

function selectTeacherQuestion(item) {
  selectedTeacherQuestion.value = item
  reviewStatus.value = item.review_status || 'pending'
  reviewNote.value = item.review_note || ''
}

async function saveTeacherReview() {
  if (!selectedTeacherQuestion.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await request(`/api/teacher/reviews/${selectedTeacherQuestion.value.id}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: reviewStatus.value, note: reviewNote.value }),
    })
    selectedTeacherQuestion.value.review_status = result.review_status
    selectedTeacherQuestion.value.review_note = result.review_note
    await openTeacher()
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

async function importTeacherSlides() {
  await importSlides()
  await openTeacher()
}

async function importTeacherVisuals() {
  await importVisuals()
  await openTeacher()
}

function selectTeacherMaterial(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!/\.(pdf|docx)$/i.test(file.name) || file.size > 20_000_000) {
    error.value = '请选取不超过 20 MB 的 PDF 或 DOCX 文件。'
    event.target.value = ''
    return
  }
  teacherMaterialFile.value = file
  error.value = ''
}

async function uploadTeacherMaterial() {
  if (!teacherMaterialFile.value || materialUploading.value) return
  materialUploading.value = true
  error.value = ''
  try {
    const file = teacherMaterialFile.value
    const result = await request(`/api/materials/upload?filename=${encodeURIComponent(file.name)}&module=${encodeURIComponent(teacherMaterialModule.value)}&ocr=${teacherMaterialOcr.value}`,
                  { method: 'POST', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file })
    teacherImportMessage.value = result.status === 'unchanged' ? `${result.filename} 内容未变化，已保留现有索引。` : `已导入 ${result.filename}：${result.units} ${result.unit_label}，${result.indexed_chunks} 个可检索片段。${result.ocr_units ? `其中 ${result.ocr_units} 页通过图片识别。` : ''}${result.error_units ? `${result.error_units} 页未能解析，请核对源文件。` : ''}${result.indexed_chunks ? '' : '该文件没有可提取文字。'}`
    teacherMaterialFile.value = null
    if (teacherMaterialInput.value) teacherMaterialInput.value.value = ''
    status.value = await request('/api/status')
    await openTeacher()
  } catch (cause) {
    error.value = cause.message
  } finally {
    materialUploading.value = false
  }
}

async function deleteTeacherMaterial(item) {
  if (!window.confirm(`删除资料“${item.filename}”及其检索索引？`)) return
  error.value = ''
  try {
    await request(`/api/materials/${item.id}`, { method: 'DELETE' })
    status.value = await request('/api/status')
    await openTeacher()
  } catch (cause) {
    error.value = cause.message
  }
}

async function summarizeLearning() {
  if (loading.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await request('/api/learning/summary', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId.value, student_key: studentKey.value }),
    })
    learningSummaries.value.unshift(result)
    studentProgress.value = await request('/api/student/progress')
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

async function ask() {
  const text = question.value.trim()
  if ((!text && !selectedImage.value) || loading.value) return
  const prompt = text || '请分析这张图片，说明看得清的内容，并结合课程资料回答。'
  const targetSessionId = sessionId.value
  const imageDataUrl = selectedImage.value?.dataUrl || null
  loading.value = true
  pendingQuestion.value = prompt
  error.value = ''
  sourceDetail.value = null
  await scrollToLatest()
  try {
    const response = await request('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: prompt, module: moduleValue.value, session_id: targetSessionId,
                             student_key: studentKey.value,
                             image_data_url: imageDataUrl }),
    })
    if (sessionId.value === targetSessionId) messages.value.push(response)
    pendingQuestion.value = ''
    question.value = ''
    selectedImage.value = null
    if (imageInput.value) imageInput.value.value = ''
    sessions.value = await request('/api/conversations/sessions')
    await scrollToLatest()
  } catch (cause) {
    pendingQuestion.value = ''
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

function selectImage(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5_000_000) {
    error.value = '请上传不超过 5 MB 的 PNG、JPEG 或 WebP 图片。'
    event.target.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    selectedImage.value = { name: file.name, dataUrl: String(reader.result) }
    error.value = ''
  }
  reader.onerror = () => { error.value = '读取图片失败，请重试。' }
  reader.readAsDataURL(file)
}

function removeImage() {
  selectedImage.value = null
  if (imageInput.value) imageInput.value.value = ''
}

async function scrollToLatest() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

async function scrollCodeToLatest() {
  await nextTick()
  if (codeThread.value) codeThread.value.scrollTop = codeThread.value.scrollHeight
}

watch(() => codeHistory.value.length, scrollCodeToLatest)

watch(() => messages.value.length, scrollToLatest)

async function openConversation(item) {
  activeTab.value = item.kind === 'code' ? 'code' : 'ask'
  sessionId.value = item.session_id
  localStorage.setItem('teaching-assistant-session', sessionId.value)
  selectedModule.value = '全部模块'
  question.value = ''
  pendingQuestion.value = ''
  sourceDetail.value = null
  removeImage()
  error.value = ''
  try {
    if (item.kind === 'code') await openCode()
    else await loadThread(sessionId.value)
  } catch (cause) {
    error.value = cause.message
  }
}

function newConversation() {
  activeTab.value = 'ask'
  sessionId.value = crypto.randomUUID()
  localStorage.setItem('teaching-assistant-session', sessionId.value)
  messages.value = []
  question.value = ''
  pendingQuestion.value = ''
  selectedModule.value = '全部模块'
  sourceDetail.value = null
  removeImage()
  code.value = ''
  codeContext.value = ''
  codeResult.value = null
  codeHistory.value = []
  learningSummaries.value = []
  error.value = ''
}

async function deleteConversation(item) {
  if (!window.confirm(`删除对话“${item.title}”？此操作会删除这段对话的全部消息。`)) return
  error.value = ''
  try {
    await request(`/api/conversations/${encodeURIComponent(item.session_id)}`, { method: 'DELETE' })
    sessions.value = sessions.value.filter(session => session.session_id !== item.session_id)
    if (sessionId.value === item.session_id) newConversation()
  } catch (cause) {
    error.value = cause.message
  }
}

async function inspectSource(item) {
  error.value = ''
  try {
    sourceDetail.value = await request(`/api/materials/${item.document_id}/slides/${item.slide_number}`)
  } catch (cause) {
    error.value = cause.message
  }
}

async function analyze() {
  if ((!code.value.trim() && !codeImage.value && !codeHistory.value.length) || loading.value) return
  loading.value = true
  error.value = ''
  try {
    codeResult.value = await request('/api/code/analyze', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: codeLanguage.value, module: codeModule.value || null,
                             context: codeContext.value,
                             session_id: sessionId.value, student_key: studentKey.value,
                             code: code.value, image_data_url: codeImage.value?.dataUrl || null }),
    })
    if (codeImage.value) codeResult.value.image_data_url = codeImage.value.dataUrl
    codeHistory.value.unshift(codeResult.value)
    codeContext.value = ''
    codeImage.value = null
    await scrollCodeToLatest()
    sessions.value = await request('/api/conversations/sessions')
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

function pasteImage(event, target = 'chat') {
  const file = [...(event.clipboardData?.items || [])]
    .find(item => ['image/png', 'image/jpeg', 'image/webp'].includes(item.type))?.getAsFile()
  if (!file) return
  event.preventDefault()
  if (loading.value) return
  if (file.size > 5_000_000) {
    error.value = '图片不能超过 5 MB。'
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    const image = { name: file.name || '剪贴板图片', dataUrl: String(reader.result) }
    if (target === 'code') codeImage.value = image
    else selectedImage.value = image
    error.value = ''
  }
  reader.onerror = () => { error.value = '读取图片失败，请重试。' }
  reader.readAsDataURL(file)
}

async function importSlides() {
  importing.value = true
  error.value = ''
  try {
    await request('/api/materials/import', { method: 'POST' })
    await refresh()
  } catch (cause) {
    error.value = cause.message
  } finally {
    importing.value = false
  }
}

async function importVisuals() {
  visualImporting.value = true
  error.value = ''
  try {
    const result = await request('/api/knowledge/visuals/import', { method: 'POST' })
    await refresh()
    if (result.file_errors?.length) error.value = `已建立 ${result.rendered_this_run} 页图像；另有 ${result.file_errors.length} 页或文件未能渲染。`
  } catch (cause) {
    error.value = cause.message
  } finally {
    visualImporting.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">IoT</div>
        <div><strong>智学工作台</strong><small>物联网综合实训</small></div>
      </div>
      <button class="new-chat-button" @click="newConversation"><span>＋</span> 新建对话</button>
      <div class="sidebar-section-label">最近对话</div>
      <div class="history-list">
        <div v-for="item in sessions" :key="item.session_id" class="history-row" :class="{ selected: sessionId === item.session_id && activeTab === 'ask' }">
          <button class="history-item" :title="item.title" @click="openConversation(item)">{{ item.title }}</button>
          <button class="delete-button" title="删除对话" aria-label="删除对话" @click.stop="deleteConversation(item)">×</button>
        </div>
        <p v-if="!sessions.length" class="sidebar-empty">还没有对话记录</p>
      </div>
      <div class="sidebar-tools">
        <div class="sidebar-section-label">学习工具</div>
        <button class="tool-button" :class="{ selected: activeTab === 'ask' }" @click="activeTab = 'ask'"><span class="nav-glyph">✦</span><span>课程问答</span></button>
        <button class="tool-button" :class="{ selected: activeTab === 'assignments' }" @click="openAssignments"><span class="nav-glyph">▣</span><span>任务验收</span></button>
        <button class="tool-button" :class="{ selected: activeTab === 'code' }" @click="openCode"><span class="nav-glyph">⌘</span><span>代码分析</span></button>
        <button class="tool-button" :class="{ selected: activeTab === 'progress' }" @click="openProgress"><span class="nav-glyph">↗</span><span>学习回顾</span></button>
        <button class="tool-button" :class="{ selected: activeTab === 'profile' }" @click="activeTab = 'profile'"><span class="nav-glyph">◎</span><span>我的信息</span></button>
        <button class="tool-button" :class="{ selected: activeTab === 'teacher' }" @click="openTeacher"><span class="nav-glyph">▤</span><span>教师工作台</span></button>
      </div>
      <div class="sidebar-foot">{{ status?.model_configured ? '课程 PPT 检索 · AI 助教' : '课程 PPT 离线问答' }}</div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <div class="topbar-heading"><small>物联网综合实训 / 学习工作区</small><strong>{{ activeTab === 'ask' ? '课程问答' : activeTab === 'assignments' ? '任务验收' : activeTab === 'code' ? '代码分析' : activeTab === 'progress' ? '学习回顾' : activeTab === 'profile' ? '我的信息' : '教师工作台' }}</strong></div>
        <div class="topbar-meta">
          <span class="knowledge-count">{{ status?.knowledge?.ppt_documents || 0 }} 份 PPT · {{ status?.knowledge?.ppt_pages || 0 }} 页<span v-if="status?.knowledge?.documents > status?.knowledge?.ppt_documents"> · {{ status.knowledge.documents - status.knowledge.ppt_documents }} 份补充资料</span></span>
          <span class="status-pill"><span class="status-dot"></span>{{ status?.model_configured ? 'AI 助教已就绪' : '本地课件模式' }}</span>
        </div>
      </header>

      <div v-if="error" class="alert" role="alert">{{ error }}</div>

      <template v-if="activeTab === 'ask'">
        <section v-if="isEmptyThread" class="welcome-panel">
          <div class="welcome-mark">✦</div>
          <span class="page-eyebrow">COURSE COMPANION · 课程学习伙伴</span>
          <h1>把问题带来，一起找到答案。</h1>
          <p>围绕课程资料提问、上传现场图片、继续追问代码和实验细节。每一步都有可回看的资料依据。</p>
          <p class="capability-line">{{ status?.message || '正在读取课程资料状态…' }}</p>
          <div class="welcome-samples">
            <button v-for="sample in sampleQuestions" :key="sample" @click="question = sample">{{ sample }}<span>↗</span></button>
          </div>
          <button v-if="!studentProfile.registered" class="profile-prompt" @click="activeTab = 'profile'">登记姓名和班级，让教师工作台正确汇总你的学习记录 →</button>
          <section v-if="status && !status.knowledge.documents" class="empty-knowledge">
            <p>课程知识库尚未导入。导入配置好的课程 PPT 后即可按课件检索。</p>
            <p>请联系教师在工作台导入课程资料。</p>
          </section>
        </section>

        <section v-else ref="messageList" class="message-list" aria-live="polite">
          <article v-for="message in messages" :key="message.id" class="message-pair">
            <div class="user-message"><div class="avatar user-avatar">我</div><div class="message-bubble user-bubble">{{ message.question }}<img v-if="message.image_url" class="chat-user-image" :src="message.image_url" alt="本轮上传的图片"></div></div>
            <div class="assistant-message">
              <div class="avatar assistant-avatar">IoT</div>
              <div class="assistant-content">
                <div class="assistant-name">课程助教 <span v-if="message.mode" class="response-label">{{ responseLabel(message.mode) }}</span></div>
                <div class="message-bubble assistant-bubble" v-html="renderMarkdown(message.answer)"></div>
                <details v-if="message.trace?.length" class="agent-trace"><summary>查看处理过程</summary><ol><li v-for="(step, index) in message.trace" :key="index">{{ step }}</li></ol></details>
                <details v-if="message.evidence?.length" class="source-details">
                  <summary>{{ message.evidence.some(item => item.candidate_only) ? '可能相关的候选课件页（非回答依据）' : '查看课件依据' }}（{{ message.evidence.length }}）</summary>
                  <article v-for="item in message.evidence" :key="item.chunk_id || `${item.document_id}-${item.slide_number}`" class="evidence-card">
                    <div v-if="item.candidate_only" class="candidate-note">此页只是检索候选，AI 的补充分析没有把它当作已确认依据。</div>
                    <div class="evidence-top"><span class="module-tag">{{ item.module }}</span><span>{{ item.material_category || '课程资料' }}</span><span v-if="item.lesson_label">{{ item.lesson_label }}</span><span>第 {{ item.slide_number }} {{ item.unit_label || '页' }}</span></div>
                    <h3>{{ item.filename }}</h3><p>{{ item.excerpt }}</p>
                    <div class="evidence-actions"><button @click="inspectSource(item)">{{ item.has_visual ? '查看页面图像' : '查看提取文字' }}</button><a :href="item.download_url">下载原文件</a></div>
                  </article>
                </details>
              </div>
            </div>
          </article>
          <article v-if="pendingQuestion" class="message-pair pending-pair">
            <div class="user-message"><div class="avatar user-avatar">我</div><div class="message-bubble user-bubble">{{ pendingQuestion }}</div></div>
            <div class="typing-indicator"><span></span><span></span><span></span><small>助教正在查资料并整理回复…</small></div>
          </article>
        </section>

        <div v-if="sourceDetail" class="modal-backdrop" role="presentation" @click.self="sourceDetail = null" @keydown.esc.window="sourceDetail = null">
          <section class="slide-modal" role="dialog" aria-modal="true" :aria-label="`${sourceDetail.filename} 第 ${sourceDetail.slide_number} ${sourceDetail.unit_label || '页'}`">
            <header class="slide-modal-header">
              <div><strong>{{ sourceDetail.filename }}</strong><span>第 {{ sourceDetail.slide_number }} {{ sourceDetail.unit_label || '页' }} · {{ sourceDetail.module }}</span></div>
              <button class="modal-close" aria-label="关闭" @click="sourceDetail = null">×</button>
            </header>
            <div class="slide-modal-body">
              <img v-if="sourceDetail.image_url" class="slide-preview" :src="sourceDetail.image_url" :alt="`${sourceDetail.filename} 第 ${sourceDetail.slide_number} ${sourceDetail.unit_label || '页'}`">
              <p v-else class="quiet">该页还没有生成页面图像。</p>
              <details v-if="sourceDetail.text" class="slide-text-details">
                <summary>查看本页提取文字</summary>
                <pre>{{ sourceDetail.text }}</pre>
              </details>
            </div>
          </section>
        </div>

        <form class="composer-dock" @submit.prevent="ask" @paste="pasteImage($event, 'chat')">
          <div class="module-row">
            <button v-for="module in modules" :key="module" type="button" class="module-chip" :class="{ active: selectedModule === module }" @click="selectedModule = module">{{ module }}</button>
          </div>
          <div class="composer">
            <div v-if="selectedImage" class="image-attachment"><img :src="selectedImage.dataUrl" alt="待发送图片预览"><span>{{ selectedImage.name }}</span><button type="button" aria-label="移除图片" @click="removeImage">×</button></div>
            <textarea v-model="question" rows="2" maxlength="2000" placeholder="给课程助教发送消息…（Enter 发送，Shift + Enter 换行）" @keydown.enter.exact.prevent="ask"></textarea>
            <div class="composer-footer"><div class="composer-tools"><input ref="imageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="selectImage"><button type="button" class="attach-button" :disabled="loading" @click="imageInput?.click()">＋ 图片</button><span>课件依据会标注来源</span></div><button class="send-button" type="submit" :disabled="loading || (!question.trim() && !selectedImage)" :aria-label="loading ? '正在回复' : '发送消息'">{{ loading ? '…' : '发送 ↑' }}</button></div>
          </div>
        </form>
      </template>

      <section v-else-if="activeTab === 'code'" class="code-workspace" @paste="pasteImage($event, 'code')">
        <div class="code-heading"><h1>代码分析</h1><p>Python 会先做本地语法检查；AI 可进一步分析代码与报错。可以围绕同一段代码连续追问，或修改代码后继续分析。检查过程不会运行代码。启用 AI 时，代码会发送至模型服务，请勿粘贴密钥。</p></div>
        <div v-if="!codeHistory.length" class="code-options"><label>代码语言 <select v-model="codeLanguage"><option v-for="item in codeLanguages" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>课程模块 <select v-model="codeModule"><option value="">未指定</option><option v-for="item in modules.slice(1)" :key="item" :value="item">{{ item }}</option></select></label></div>
        <textarea v-if="!codeHistory.length" v-model="code" class="code-box" spellcheck="false" maxlength="20000" placeholder="粘贴要分析的代码…" rows="15"></textarea>
        <template v-else>
          <div class="code-thread-toolbar"><label>代码语言 <select v-model="codeLanguage"><option v-for="item in codeLanguages" :key="item.value" :value="item.value">{{ item.label }}</option></select></label><label>课程模块 <select v-model="codeModule"><option value="">未指定</option><option v-for="item in modules.slice(1)" :key="item" :value="item">{{ item }}</option></select></label><details class="code-source-editor"><summary>查看或修改当前代码</summary><textarea v-model="code" class="code-box" spellcheck="false" maxlength="20000" rows="12"></textarea></details></div>
          <section ref="codeThread" class="code-dialog" role="log" aria-label="代码分析对话">
            <article v-for="item in codeTurns" :key="item.id" class="code-turn">
              <div class="code-user-message">{{ item.context === '请分析这段代码' ? '请分析下面的代码。' : item.context }}<img v-if="item.image_data_url" class="chat-user-image" :src="item.image_data_url" alt="本轮提交的代码或报错图片"></div>
              <div class="code-assistant-message">
                <small>{{ item.module || '未指定模块' }} · {{ item.language }} · {{ item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '刚刚' }}</small>
                <p>{{ item.summary }}</p>
                <details v-if="item.structure" class="code-turn-source"><summary>静态结构</summary><p>函数：{{ item.structure.functions?.join('、') || '无' }}</p><p>类：{{ item.structure.classes?.join('、') || '无' }}</p><p>赋值变量：{{ item.structure.assigned_variables?.join('、') || '无' }}</p><p>调用：{{ item.structure.calls?.join('、') || '无' }}</p></details>
                <div v-for="(issue, index) in item.issues || []" :key="index" class="issue">第 {{ issue.line }} 行，第 {{ issue.column }} 列：{{ issue.message }}<pre v-if="issue.source">{{ issue.source }}</pre></div>
                <div v-if="item.analysis" class="assistant-bubble code-analysis" @click="handleCodeCopy" v-html="renderMarkdown(item.analysis)"></div>
                <p v-else-if="item.mode === 'local'" class="quiet">当前仅有本地检查结果；AI 静态分析暂不可用。</p>
                <details v-if="item.code" class="code-turn-source"><summary>本轮代码版本</summary><pre>{{ item.code }}</pre></details>
              </div>
            </article>
          </section>
        </template>
        <div v-if="codeImage" class="image-attachment code-image-attachment"><img :src="codeImage.dataUrl" alt="待分析图片预览"><span>{{ codeImage.name }}</span><button type="button" aria-label="移除图片" @click="codeImage = null">×</button></div>
        <form class="code-composer" @submit.prevent="analyze">
          <textarea v-model="codeContext" rows="2" maxlength="1000" :placeholder="codeHistory.length ? '继续追问这段代码…（Enter 发送，Shift + Enter 换行）' : '可以补充运行现象或重点问题…（Enter 分析，Shift + Enter 换行）'" @keydown.enter.exact.prevent="analyze"></textarea>
          <button class="send-button" :disabled="loading || (!code.trim() && !codeHistory.length && !codeImage)">{{ loading ? '分析中…' : codeHistory.length ? '发送 ↑' : '分析代码 ↑' }}</button>
        </form>
      </section>

      <section v-else-if="activeTab === 'assignments'" class="assignment-workspace">
        <div class="assignment-hero"><div><span class="page-eyebrow">PRACTICE STUDIO · 实训中心</span><h1>提交作品，获得清晰的验收反馈</h1><p>从指导手册选择任务，提交自己的代码、功能证据与实验报告。AI 按代码和功能完整度评分，并指出需要继续核实的部分。</p></div><div class="assignment-hero-stat"><strong>{{ assignmentData.items.length }}</strong><span>项手册任务</span></div></div>
        <div class="assignment-filters"><select v-model="assignmentModule"><option>全部模块</option><option v-for="item in assignmentData.modules" :key="item">{{ item }}</option></select><input v-model="assignmentQuery" placeholder="搜索任务、课次或内容…"></div>
        <p class="quiet assignment-count">找到 {{ visibleAssignments.length }} 项任务 · 选择任务后可提交或针对性提问</p>
        <div class="assignment-layout">
          <div class="assignment-list">
            <button v-for="item in visibleAssignments" :key="item.id" class="assignment-card assignment-card-select" :class="{ active: selectedAssignment?.id === item.id }" @click="selectAssignment(item)">
              <small>{{ item.module }} · {{ item.source }}</small><strong>{{ item.title }}</strong>
              <span>{{ item.rubric_available ? '含手册评分点' : item.rubric_note }}</span>
            </button>
          </div>
          <div v-if="selectedAssignment" class="assignment-detail">
            <div class="assignment-card-meta"><span>{{ selectedAssignment.module }}</span><span>{{ selectedAssignment.source }}</span></div>
            <h2>{{ selectedAssignment.title }}</h2>
            <details open><summary>任务要求</summary><pre>{{ selectedAssignment.description }}</pre></details>
            <details><summary>代码与功能验收点</summary><pre>{{ selectedAssignment.scoring_rubric || selectedAssignment.rubric_note }}</pre></details>
            <p class="assignment-scoring-note">验收重点是代码实现与功能完整度。环境搭建不计分；仅凭代码无法确认的运行效果会单独列出，方便补充证据。</p>

            <section v-if="assignmentSubmissions.length" class="submission-history">
              <div class="submission-history-heading"><h3>提交记录</h3><button type="button" class="secondary-button" @click="newAssignmentSubmission">＋ 重新提交</button></div>
              <div v-for="item in assignmentSubmissions" :key="item.submission_id" class="submission-history-row" :class="{ selected: selectedSubmissionId === item.submission_id }">
                <button type="button" class="submission-history-main" @click="showAssignmentSubmission(item)"><strong>第 {{ item.submission_id }} 次提交 · AI {{ item.total_score }} 分<span v-if="item.teacher_final_score !== null"> · 教师 {{ item.teacher_final_score }} 分</span></strong><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }} · {{ item.teacher_review_status === 'approved' ? '教师已确认' : item.teacher_review_status === 'needs_revision' ? '教师建议修订' : '待教师复核' }}</small></button>
                <button type="button" class="record-action" @click="reviseAssignmentSubmission(item)">修订</button>
                <button type="button" class="record-action danger" @click="deleteAssignmentSubmission(item)">删除</button>
              </div>
            </section>

            <form class="assignment-submit" @submit.prevent="submitAssignment">
              <h3>{{ assignmentRevisionId ? `修订提交 #${assignmentRevisionId}` : '提交作品进行 AI 验收' }}</h3>
              <label>作品 / 代码 / 运行证据<textarea v-model="assignmentWorkText" rows="5" placeholder="描述完成的功能、关键实现，或粘贴代码和验收说明。也可以上传源码、项目 ZIP、截图。" @paste="pasteAssignmentImage($event, 'work')"></textarea></label>
              <div class="assignment-upload-row"><input ref="assignmentWorkInput" type="file" multiple accept=".zip,.py,.c,.h,.cpp,.hpp,.java,.js,.html,.css,.json,.xml,.md,.ino,.sql,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp" hidden @change="addSubmissionFiles($event, 'work')"><button type="button" class="attach-button" @click="assignmentWorkInput?.click()">＋ 上传作品附件</button><span v-for="file in retainedAssignmentFiles.filter(item => item.group === 'work')" :key="`old-work-${file.index}`" class="submission-file">{{ file.filename }}<button type="button" aria-label="移除保留附件" @click="retainedAssignmentFiles = retainedAssignmentFiles.filter(item => item.index !== file.index)">×</button></span><span v-for="(file, index) in assignmentWorkFiles" :key="file.filename + index" class="submission-file">{{ file.filename }}<button type="button" @click="assignmentWorkFiles.splice(index, 1)">×</button></span></div>
              <label>实验报告<textarea v-model="assignmentReportText" rows="4" placeholder="粘贴报告内容，或上传 DOCX / PDF 报告。报告按课程标准占总评 30%。" @paste="pasteAssignmentImage($event, 'report')"></textarea></label>
              <div class="assignment-upload-row"><input ref="assignmentReportInput" type="file" multiple accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" hidden @change="addSubmissionFiles($event, 'report')"><button type="button" class="attach-button" @click="assignmentReportInput?.click()">＋ 上传报告附件</button><span v-for="file in retainedAssignmentFiles.filter(item => item.group === 'report')" :key="`old-report-${file.index}`" class="submission-file">{{ file.filename }}<button type="button" aria-label="移除保留附件" @click="retainedAssignmentFiles = retainedAssignmentFiles.filter(item => item.index !== file.index)">×</button></span><span v-for="(file, index) in assignmentReportFiles" :key="file.filename + index" class="submission-file">{{ file.filename }}<button type="button" @click="assignmentReportFiles.splice(index, 1)">×</button></span></div>
              <button class="send-button" :disabled="assignmentSubmitting">{{ assignmentSubmitting ? '正在验收评分…' : assignmentRevisionId ? '保存修订并重新评分' : assignmentSubmissions.length ? '重新提交并评分' : '提交并评分' }}</button>
              <button v-if="assignmentRevisionId" type="button" class="text-button" @click="newAssignmentSubmission">取消修订</button>
              <p class="quiet">支持 DOCX、PDF、ZIP、代码文件和 PNG/JPEG/WebP 图片，单个附件最大 10 MB。截图无法证明未展示的实际运行效果。</p>
            </form>

            <section v-if="assignmentGrade" class="assignment-grade">
              <h3>AI 验收反馈 <small>{{ selectedAssignmentSubmission?.created_at ? new Date(selectedAssignmentSubmission.created_at).toLocaleString('zh-CN') : '' }}</small></h3>
              <div class="grade-score-row"><div><strong>{{ assignmentGrade.acceptance_score }}</strong><span>现场验收 / 100 · 权重 70%</span></div><div><strong>{{ assignmentGrade.report_score }}</strong><span>实验报告 / 100 · 权重 30%</span></div><div class="grade-total"><strong>{{ assignmentGrade.total_score }}</strong><span>加权总分 / 100</span></div></div>
              <div v-if="selectedAssignmentSubmission" class="teacher-feedback"><strong>教师复核：{{ selectedAssignmentSubmission.teacher_review_status === 'approved' ? '已确认' : selectedAssignmentSubmission.teacher_review_status === 'needs_revision' ? '建议修订' : '待复核' }}</strong><span v-if="selectedAssignmentSubmission.teacher_final_score !== null">最终分数：{{ selectedAssignmentSubmission.teacher_final_score }}</span><p v-if="selectedAssignmentSubmission.teacher_review_note">{{ selectedAssignmentSubmission.teacher_review_note }}</p></div>
              <div v-if="selectedAssignmentSubmission?.attachments?.length" class="teacher-submission-files"><button v-for="attachment in selectedAssignmentSubmission.attachments" :key="attachment.index" class="attach-button" @click="downloadSubmissionFile(selectedAssignmentSubmission.submission_id, attachment)">下载{{ attachment.group === 'work' ? '作品' : '报告' }}：{{ attachment.filename }}</button></div>
              <div v-if="assignmentGrade.policy_version !== 'code_function_focus_v2'" class="grade-old-policy"><p>这条历史评分使用旧评分规则，曾把环境搭建纳入评分。可以直接使用本次已保存的提交材料重新评分。</p><button class="secondary-button" :disabled="assignmentSubmitting" @click="regradeAssignment">{{ assignmentSubmitting ? '重新评分中…' : '按代码与功能规则重新评分' }}</button></div>
              <p class="grade-status">{{ assignmentGrade.status }}</p>
              <h4>作品验收评分</h4><div v-for="(item, index) in assignmentGrade.acceptance_items || []" :key="'a' + index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.evidence }}</p><p>{{ item.feedback }}</p></div>
              <h4>报告评分</h4><div v-for="(item, index) in assignmentGrade.report_items || []" :key="'r' + index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.evidence }}</p><p>{{ item.feedback }}</p></div>
              <div v-if="assignmentGrade.issues?.length" class="grade-feedback"><strong>需要改进</strong><ul><li v-for="(item, index) in assignmentGrade.issues" :key="index">{{ item }}</li></ul></div>
              <div v-if="assignmentGrade.next_steps?.length" class="grade-feedback"><strong>下一步建议</strong><ul><li v-for="(item, index) in assignmentGrade.next_steps" :key="index">{{ item }}</li></ul></div>
              <div v-if="assignmentGrade.verification_limits?.length" class="grade-feedback"><strong>当前材料无法验证</strong><ul><li v-for="(item, index) in assignmentGrade.verification_limits" :key="index">{{ item }}</li></ul></div>
              <p class="quiet">这是 AI 初评，用于学习反馈；现场表现和正式成绩仍由教师确认。</p>
            </section>

            <section class="assignment-tutor">
              <h3>针对本任务答疑</h3><p class="quiet">可以询问概念、错误或评分点。助教会给提示和排查方向，不会代写整份作业或报告。</p>
              <div class="assignment-tutor-thread" role="log"><div v-for="(turn, index) in assignmentTutorTurns" :key="index" :class="turn.role === 'user' ? 'tutor-user-turn' : 'tutor-assistant-turn'"><strong>{{ turn.role === 'user' ? '我' : '助教' }}</strong><div class="assistant-bubble" v-html="renderMarkdown(turn.content)"></div></div></div>
              <form class="assignment-tutor-composer" @submit.prevent="askAssignment"><textarea v-model="assignmentTutorInput" rows="2" maxlength="1500" placeholder="描述你卡住的步骤或报错…（Enter 发送，Shift + Enter 换行）" @keydown.enter.exact.prevent="askAssignment"></textarea><button class="send-button" :disabled="assignmentTutorLoading || !assignmentTutorInput.trim()">{{ assignmentTutorLoading ? '思考中…' : '提问' }}</button></form>
            </section>
          </div>
          <div v-else class="assignment-empty">从左侧选择一项指导手册任务，查看要求、评分点并提交自己的作品和报告。</div>
        </div>
        <p v-if="!visibleAssignments.length" class="quiet">没有找到匹配的指导手册任务；请确认两份指导手册已加入知识库。</p>
      </section>

      <section v-else-if="activeTab === 'progress'" class="progress-workspace">
        <div class="code-heading"><h1>学习回顾</h1><p>根据当前对话与代码检查记录整理学习线索。没有评分标准时不生成成绩。</p></div>
        <div v-if="studentProgress" class="teacher-stats student-progress-stats"><div><strong>{{ studentProgress.totals.questions }}</strong><span>累计提问</span></div><div><strong>{{ studentProgress.totals.code_reviews }}</strong><span>代码分析</span></div><div><strong>{{ studentProgress.totals.submitted_tasks }}</strong><span>已提交任务</span></div><div><strong>{{ studentProgress.totals.learning_summaries }}</strong><span>学习回顾</span></div></div>
        <div v-if="studentProgress?.modules?.length" class="analytics-card student-progress-card"><h3>模块学习活动</h3><div v-for="row in studentProgress.modules" :key="row.name" class="analytics-row"><strong>{{ row.name }}</strong><span>{{ row.questions }} 次提问 · {{ row.code_reviews }} 次代码分析 · {{ row.submitted_tasks }} 项任务</span></div></div>
        <div v-if="studentProgress?.tasks?.length" class="analytics-card student-progress-card"><h3>最近提交的任务</h3><div v-for="row in studentProgress.tasks" :key="row.assignment_id" class="analytics-row"><strong>{{ row.title }}</strong><span>{{ row.module }} · 最新评分 {{ row.score }} · {{ new Date(row.submitted_at).toLocaleDateString('zh-CN') }}</span></div></div>
        <button class="send-button" :disabled="loading" @click="summarizeLearning">{{ loading ? '正在整理…' : '生成本段对话的学习回顾' }}</button>
        <p v-if="!learningSummaries.length" class="quiet progress-empty">还没有学习回顾。先在当前对话提问或检查代码，再点击上方按钮。</p>
        <article v-for="item in learningSummaries" :key="item.id" class="progress-card"><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small><div class="assistant-bubble" v-html="renderMarkdown(item.content)"></div></article>
      </section>

      <section v-else-if="activeTab === 'profile'" class="profile-workspace">
        <div class="code-heading"><h1>我的信息</h1><p>登记后，新产生的提问、代码分析、作业提交和学习回顾会按班级汇总到教师工作台。已有匿名记录仍单独保留。</p></div>
        <form class="profile-form" @submit.prevent="saveStudentProfile">
          <label>姓名 <input v-model="studentProfile.name" maxlength="80" required placeholder="请输入姓名"></label>
          <label>学号 <input v-model="studentProfile.student_number" maxlength="40" placeholder="选填"></label>
          <label>班级 <input v-model="studentProfile.class_name" maxlength="80" required placeholder="例如：物联网 2023 级 1 班"></label>
          <button class="send-button" :disabled="profileSaving">{{ profileSaving ? '保存中…' : studentProfile.registered ? '更新信息' : '保存信息' }}</button>
          <p v-if="studentProfile.registered" class="profile-saved">已登记：{{ studentProfile.name }} · {{ studentProfile.class_name }}</p>
        </form>
      </section>

      <section v-else class="teacher-workspace">
        <div class="code-heading"><h1>教师工作台</h1><p>按班级、模块和日期查看学习过程与任务提交，管理资料并审核助教回答。</p></div>
        <form v-if="!teacherCode" class="teacher-access" @submit.prevent="unlockTeacher"><h2>教师身份验证</h2><p>请输入本机 .env 中的 TEACHER_ACCESS_CODE 访问码。</p><input v-model="teacherCodeInput" type="password" autocomplete="off" placeholder="教师访问码" required><button class="send-button">进入工作台</button></form>
        <template v-else>
        <div class="teacher-section-heading"><h2>学习过程分析</h2><button class="text-button" @click="lockTeacher">退出教师视图</button></div>
        <div class="analytics-filters">
          <label>班级<select v-model="teacherFilter.class_name" @change="loadTeacherAnalytics"><option value="">全部班级</option><option v-for="name in teacherAnalytics?.filters?.classes || []" :key="name" :value="name">{{ name }}</option><option value="未登记">未登记</option></select></label>
          <label>模块<select v-model="teacherFilter.module" @change="loadTeacherAnalytics"><option value="">全部模块</option><option v-for="name in teacherAnalytics?.filters?.modules || []" :key="name" :value="name">{{ name }}</option></select></label>
          <label>开始日期<input v-model="teacherFilter.from_date" type="date" @change="loadTeacherAnalytics"></label>
          <label>结束日期<input v-model="teacherFilter.to_date" type="date" @change="loadTeacherAnalytics"></label>
        </div>
        <div v-if="teacherAnalytics" class="teacher-stats analytics-stats">
          <div><strong>{{ teacherAnalytics.summary.registered_students }}</strong><span>已登记学生</span></div>
          <div><strong>{{ teacherAnalytics.summary.active_participants }}</strong><span>活跃学习者</span></div>
          <div><strong>{{ teacherAnalytics.summary.questions }}</strong><span>提问</span></div>
          <div><strong>{{ teacherAnalytics.summary.code_reviews }}</strong><span>代码分析</span></div>
          <div><strong>{{ teacherAnalytics.summary.submissions }}</strong><span>任务提交</span></div>
          <div><strong>{{ teacherAnalytics.summary.average_score ?? '—' }}</strong><span>平均提交分</span></div>
        </div>
        <div class="analytics-grids" v-if="teacherAnalytics">
          <div class="analytics-card"><h3>班级概览</h3><div v-for="row in teacherAnalytics.classes" :key="row.name" class="analytics-row"><strong>{{ row.name }}</strong><span>{{ row.participants }} 人 · {{ row.questions }} 次提问 · {{ row.submissions }} 次提交</span></div><p v-if="!teacherAnalytics.classes.length" class="quiet">当前筛选范围没有学习记录。</p></div>
          <div class="analytics-card"><h3>模块活动</h3><div v-for="row in teacherAnalytics.modules" :key="row.name" class="analytics-row"><strong>{{ row.name }}</strong><span>{{ row.questions }} 次提问 · {{ row.submissions }} 次提交</span></div><p v-if="!teacherAnalytics.modules.length" class="quiet">当前筛选范围没有模块活动。</p></div>
          <div class="analytics-card"><h3>每日趋势</h3><div v-for="row in teacherAnalytics.timeline" :key="row.date" class="analytics-row"><strong>{{ row.date }}</strong><span>{{ row.questions }} 次提问 · {{ row.code_reviews }} 次代码分析 · {{ row.submissions }} 次提交</span></div><p v-if="!teacherAnalytics.timeline.length" class="quiet">当前筛选范围没有日期记录。</p></div>
          <div class="analytics-card"><h3>学生任务进度</h3><div v-for="(row, index) in teacherAnalytics.students" :key="index" class="analytics-row"><strong>{{ row.name }} · {{ row.class_name }}</strong><span>{{ row.assignment_count }} 项任务 · 均分 {{ row.average_score ?? '—' }} · {{ row.questions }} 次提问</span></div><p v-if="!teacherAnalytics.students.length" class="quiet">登记学生开始使用后，这里会显示进度。</p></div>
          <div class="analytics-card"><h3>常见问题</h3><div v-for="(row, index) in teacherAnalytics.common_issues" :key="index" class="analytics-row"><strong>{{ row.issue }}</strong><span>{{ row.count }} 次</span></div><p v-if="!teacherAnalytics.common_issues.length" class="quiet">尚无可汇总的错误或验收问题。</p></div>
        </div>
        <div v-if="teacherAnalytics?.recent_submissions?.length" class="analytics-card teacher-recent-submissions"><h3>最近任务提交 · 点击查看与复核</h3><button v-for="row in teacherAnalytics.recent_submissions" :key="row.id" class="analytics-row teacher-submission-select" :class="{ active: selectedTeacherSubmission?.id === row.id }" @click="selectTeacherSubmission(row)"><strong>{{ row.student_name }} · {{ row.class_name }} · {{ row.assignment_title }}</strong><span>{{ row.module }} · AI {{ row.total_score }} 分<span v-if="row.teacher_final_score !== null"> · 最终 {{ row.teacher_final_score }} 分</span> · {{ row.teacher_review_status === 'approved' ? '已确认' : row.teacher_review_status === 'needs_revision' ? '需修订' : '待复核' }}</span></button></div>
        <section v-if="selectedTeacherSubmission" class="teacher-submission-review"><div class="teacher-section-heading"><h2>复核：{{ selectedTeacherSubmission.assignment_title }}</h2><button class="text-button" @click="selectedTeacherSubmission = null">关闭</button></div><p>AI 初评分：{{ selectedTeacherSubmission.evaluation.total_score }}。请结合原始代码、报告和附件确认。</p><details><summary>作品文字</summary><pre>{{ selectedTeacherSubmission.work_text || '作品文字为空，请查看附件。' }}</pre></details><details><summary>实验报告文字</summary><pre>{{ selectedTeacherSubmission.report_text || '报告文字为空，请查看附件。' }}</pre></details><div class="teacher-submission-files"><button v-for="attachment in selectedTeacherSubmission.attachments" :key="attachment.index" class="attach-button" @click="downloadSubmissionFile(selectedTeacherSubmission.id, attachment)">下载{{ attachment.group === 'work' ? '作品' : '报告' }}：{{ attachment.filename }}</button></div><details><summary>AI 评分明细</summary><div v-for="(item, index) in selectedTeacherSubmission.evaluation.acceptance_items || []" :key="index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.feedback }}</p></div><div v-for="(item, index) in selectedTeacherSubmission.evaluation.report_items || []" :key="`report-${index}`" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.feedback }}</p></div></details><form class="teacher-review-form" @submit.prevent="saveSubmissionReview"><label>复核状态<select v-model="submissionReviewStatus"><option value="pending">待复核</option><option value="approved">确认</option><option value="needs_revision">建议修订</option></select></label><label>最终分数（选填）<input v-model="submissionFinalScore" type="number" min="0" max="100" step="0.1" :disabled="submissionReviewStatus !== 'approved'" placeholder="留空则显示 AI 初评分"></label><label>教师意见<textarea v-model="submissionReviewNote" rows="3" maxlength="2000" placeholder="写明确认依据或需要补充的材料"></textarea></label><button class="send-button" :disabled="loading">{{ loading ? '保存中…' : '保存复核' }}</button></form></section>
        <div class="teacher-section-heading"><h2>全库概况</h2><span>不受上方筛选影响</span></div>
        <div v-if="teacherData" class="teacher-stats">
          <div><strong>{{ teacherData.totals.documents }}</strong><span>课程资料</span></div>
          <div><strong>{{ teacherData.totals.slides }}</strong><span>内容单元</span></div>
          <div><strong>{{ teacherData.totals.questions }}</strong><span>学生提问</span></div>
          <div><strong>{{ teacherData.totals.code_reviews }}</strong><span>代码分析</span></div>
          <div><strong>{{ teacherData.totals.learning_summaries }}</strong><span>学习回顾</span></div>
          <div><strong>{{ teacherData.totals.pending_reviews }}</strong><span>待审核回答</span></div>
        </div>
        <div class="teacher-section-heading"><h2>课程资料</h2><div><button class="secondary-button" :disabled="importing" @click="importTeacherSlides">{{ importing ? '导入中…' : '导入配置的课件 ZIP' }}</button><button class="secondary-button" :disabled="visualImporting" @click="importTeacherVisuals">{{ visualImporting ? '处理中…' : '建立页面图像' }}</button></div></div>
        <div class="teacher-upload"><input ref="teacherMaterialInput" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden @change="selectTeacherMaterial"><button class="attach-button" @click="teacherMaterialInput?.click()">＋ 选择 PDF / Word</button><span>{{ teacherMaterialFile?.name || '尚未选择文件' }}</span><select v-model="teacherMaterialModule"><option v-for="item in modules.slice(1)" :key="item" :value="item">{{ item }}</option></select><label class="teacher-ocr-option"><input v-model="teacherMaterialOcr" type="checkbox" :disabled="!teacherMaterialFile || !/\.pdf$/i.test(teacherMaterialFile.name)">识别扫描 PDF 图片页</label><button class="secondary-button" :disabled="!teacherMaterialFile || materialUploading" @click="uploadTeacherMaterial">{{ materialUploading ? '建立索引中…' : '上传并建立索引' }}</button></div><p v-if="teacherImportMessage" class="teacher-import-message">{{ teacherImportMessage }}</p>
        <div class="teacher-modules"><span v-for="(item, name) in teacherData?.modules || {}" :key="name">{{ name }}：{{ item.documents }} 份 · {{ item.slides }} 个内容单元</span></div>
        <details class="teacher-materials"><summary>查看全部课件（{{ teacherData?.materials?.length || 0 }}）</summary><div v-for="item in teacherData?.materials || []" :key="item.id"><span>{{ item.filename }}</span><small>{{ item.module }} · {{ item.slide_count }} {{ item.unit_label || '页' }} · 版本 {{ item.version }} · {{ new Date(item.created_at).toLocaleDateString('zh-CN') }}</small><a :href="`/api/materials/${item.id}/download`">下载</a><button v-if="item.source_type !== 'pptx'" @click="deleteTeacherMaterial(item)">删除</button></div></details>
        <details v-if="teacherData?.material_revisions?.length" class="teacher-materials"><summary>资料更新记录（{{ teacherData.material_revisions.length }}）</summary><div v-for="item in teacherData.material_revisions" :key="item.id"><span>{{ item.filename }}</span><small>{{ item.module }} · {{ item.old_version }} → {{ item.new_version }} · {{ new Date(item.replaced_at).toLocaleString('zh-CN') }}</small></div></details>
        <div class="teacher-section-heading"><h2>回答审核</h2><span>全局最近 40 条</span></div>
        <div class="teacher-review-grid"><div class="teacher-question-list"><button v-for="item in teacherData?.questions || []" :key="item.id" :class="{ selected: selectedTeacherQuestion?.id === item.id }" @click="selectTeacherQuestion(item)"><span>{{ item.question }}</span><small>{{ item.module || '未指定模块' }} · {{ item.review_status === 'approved' ? '已确认' : item.review_status === 'needs_revision' ? '需修改' : '待审核' }}</small></button><p v-if="!teacherData?.questions?.length" class="quiet">还没有问答记录。</p></div><article v-if="selectedTeacherQuestion" class="teacher-answer"><h3>{{ selectedTeacherQuestion.question }}</h3><div class="assistant-bubble" v-html="renderMarkdown(selectedTeacherQuestion.answer)"></div><details v-if="selectedTeacherQuestion.evidence?.length"><summary>课件来源（{{ selectedTeacherQuestion.evidence.length }}）</summary><p v-for="item in selectedTeacherQuestion.evidence" :key="item.chunk_id">{{ item.filename }} · 第 {{ item.slide_number }} {{ item.unit_label || '页' }}</p></details><label>审核状态 <select v-model="reviewStatus"><option value="pending">待审核</option><option value="approved">已确认</option><option value="needs_revision">需修改</option></select></label><label>审核备注 <textarea v-model="reviewNote" rows="3" maxlength="2000" placeholder="记录需要核对或修改的地方…"></textarea></label><button class="send-button" :disabled="loading" @click="saveTeacherReview">{{ loading ? '保存中…' : '保存审核' }}</button></article><p v-else class="quiet">选择一条回答查看并审核。</p></div>
        </template>
      </section>
    </main>
  </div>
</template>
