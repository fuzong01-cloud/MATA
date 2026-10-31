<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { createCourseMarkdown, formatAssignmentText } from './document-rendering.js'
import { MessageCircleQuestion, ClipboardCheck, CodeXml, ChartNoAxesCombined, CircleUserRound, GraduationCap, ArrowUp, ArrowUpRight, BookOpen, Cpu, Database, Layers, Paperclip, Smartphone, Sparkles } from '@lucide/vue'
import BrandMark from './assets/brand-mark.svg'
import CustomSelect from './components/CustomSelect.vue'

const modules = ['全部模块', '嵌入式开发', 'Web开发', 'Android开发', '虚拟仿真']
const selectedModule = ref('全部模块')
const activeTab = ref('ask')
const activeNavIndex = computed(() => ({ ask: 0, assignments: 1, code: 2, progress: 3, profile: 4, teacher: 5 })[activeTab.value] ?? 0)
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const question = ref('')
const questionInput = ref(null)
const pendingQuestion = ref('')
const pendingImage = ref(null)
const waitSeconds = ref(0)
const waitingStatus = computed(() => {
  const seconds = waitSeconds.value
  if (seconds >= 45) return '请求仍在处理中，模型响应较慢…'
  if (seconds >= 22) return '正在组织回答并整理可核对的资料依据…'
  if (seconds >= 9) return '正在检索相关课程资料…'
  if (pendingImage.value) return '已收到图片，正在读取图片内容…'
  return '已收到问题，正在理解并查找相关资料…'
})
const code = ref('')
const codeLineNumbersRef = ref(null)
const codeLanguage = ref('auto')
const codeModule = ref('')
const codeContext = ref('')
const codeImage = ref(null)
const assignmentData = ref({ items: [], modules: [] })
const assignmentModule = ref('全部模块')
const assignmentQuery = ref('')
const collapsedAssignmentGroups = ref(new Set())
const assignmentWorkspaceRef = ref(null)
const assignmentListScrollTop = ref(0)
const selectedAssignment = ref(null)
const assignmentDetailOpen = ref(false)
const assignmentTutorOpen = ref(false)
const assignmentDetailsLoading = ref(false)
const loadedAssignmentId = ref('')
let assignmentLoadSequence = 0
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
const openingSessionId = ref('')
let conversationOpenSequence = 0
const codeResult = ref(null)
const codeHistory = ref([])
const codeThread = ref(null)
const codeTurns = computed(() => [...codeHistory.value].reverse())
const codeLineCount = computed(() => (code.value.match(/\n/g) || []).length + 1)
const codeLineNumbers = computed(() => Array.from({ length: codeLineCount.value }, (_, index) => index + 1).join('\n'))
const learningSummaries = ref([])
const studentProgress = ref(null)
const studentKey = ref(localStorage.getItem('teaching-assistant-student') || crypto.randomUUID())
localStorage.setItem('teaching-assistant-student', studentKey.value)
const studentProfile = ref({ name: '', student_number: '', class_name: '', registered: false })
const profileSaving = ref(false)
const profileSaveMessage = ref('')
const teacherCode = ref(sessionStorage.getItem('teaching-assistant-teacher-code') || '')
const teacherCodeInput = ref('')
const teacherWorkspaceRef = ref(null)
const teacherData = ref(null)
const teacherSection = ref('assignments')
const teacherAssignments = ref({ tasks: [], submissions: [], classes: [] })
const teacherSelectedTaskId = ref('')
const teacherTaskDetail = ref(null)
const teacherTaskEditing = ref(false)
const teacherTaskDraft = ref({ title: '', description: '', scoring_rubric: '' })
const teacherTaskLoading = ref(false)
const teacherAssignmentModule = ref('')
const teacherAssignmentQuery = ref('')
const teacherSubmissionClass = ref('')
const teacherSubmissionStudent = ref('')
const teacherSubmissionStatus = ref('')
const teacherSubmissionFrom = ref('')
const teacherSubmissionTo = ref('')
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
const assignmentImagePreview = ref(null)
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
const moduleIcons = {
  全部模块: Sparkles,
  嵌入式开发: Cpu,
  Web开发: CodeXml,
  Android开发: Smartphone,
  虚拟仿真: Layers,
}
const sampleTopics = [
  { category: 'Web 开发', tone: 'web', icon: CodeXml },
  { category: 'Android 开发', tone: 'android', icon: Smartphone },
  { category: '数据库', tone: 'database', icon: Database },
  { category: '嵌入式开发', tone: 'embedded', icon: Cpu },
]
const sampleCards = computed(() => sampleQuestions.map((question, index) => ({ ...sampleTopics[index], question })))

function resizeQuestionInput(target = questionInput.value) {
  if (!target) return
  target.style.height = 'auto'
  target.style.height = `${Math.min(target.scrollHeight, 176)}px`
  target.style.overflowY = target.scrollHeight > 176 ? 'auto' : 'hidden'
}

watch(question, async () => {
  await nextTick()
  resizeQuestionInput()
})
const markdown = createCourseMarkdown({ linkify: true })
const assignmentMarkdown = createCourseMarkdown()

const moduleValue = computed(() => selectedModule.value === '全部模块' ? null : selectedModule.value)
const visibleAssignments = computed(() => assignmentData.value.items.filter(item => {
  const moduleMatches = assignmentModule.value === '全部模块' || item.module === assignmentModule.value
  const query = assignmentQuery.value.trim().toLowerCase()
  return moduleMatches && (!query || `${item.title} ${item.source} ${item.description} ${item.rubric}`.toLowerCase().includes(query))
}))
const assignmentGroups = computed(() => {
  const groups = new Map()
  for (const item of visibleAssignments.value) {
    const key = `${item.module}\u0000${item.source}`
    if (!groups.has(key)) groups.set(key, { module: item.module, source: item.source, items: [] })
    groups.get(key).items.push(item)
  }
  return [...groups.values()]
})
function toggleAssignmentGroup(key) {
  const next = new Set(collapsedAssignmentGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedAssignmentGroups.value = next
}
const selectedAssignmentSubmission = computed(() => assignmentSubmissions.value.find(
  item => item.submission_id === selectedSubmissionId.value) || null)
const assignmentStatusLabel = computed(() => {
  if (assignmentDetailsLoading.value) return '正在载入任务'
  if (assignmentSubmitting.value) return '正在验收'
  if (assignmentRevisionId.value !== null) return `修订第 ${assignmentRevisionId.value} 次提交`
  const review = selectedAssignmentSubmission.value?.teacher_review_status
  if (review === 'approved') return '教师已确认'
  if (review === 'needs_revision') return '建议修订'
  return selectedAssignmentSubmission.value ? '已提交 · 待教师复核' : '待提交'
})
const visibleTeacherTasks = computed(() => teacherAssignments.value.tasks.filter(task =>
  (!teacherAssignmentModule.value || task.module === teacherAssignmentModule.value)
  && (!teacherAssignmentQuery.value.trim() || `${task.title} ${task.id}`.toLowerCase().includes(teacherAssignmentQuery.value.trim().toLowerCase()))
))
const visibleTeacherSubmissions = computed(() => teacherAssignments.value.submissions.filter(item =>
  (!teacherSelectedTaskId.value || item.assignment_id === teacherSelectedTaskId.value)
  && (!teacherSubmissionClass.value || item.class_name === teacherSubmissionClass.value)
  && (!teacherSubmissionStudent.value.trim() || `${item.student_name} ${item.student_number}`.toLowerCase().includes(teacherSubmissionStudent.value.trim().toLowerCase()))
  && (!teacherSubmissionStatus.value || item.teacher_review_status === teacherSubmissionStatus.value)
  && (!teacherSubmissionFrom.value || item.created_at.slice(0, 10) >= teacherSubmissionFrom.value)
  && (!teacherSubmissionTo.value || item.created_at.slice(0, 10) <= teacherSubmissionTo.value)
))
const isEmptyThread = computed(() => activeTab.value === 'ask' && messages.value.length === 0 && !pendingQuestion.value)

async function chooseSample(sample) {
  question.value = sample
  await nextTick()
  questionInput.value?.focus()
}

function responseLabel(mode) {
  const labels = {
    model_grounded: '根据课程 PPT 回答',
    model_multimodal: '结合 PPT 文字与图像回答',
    model_general: 'AI 补充分析',
    multi_agent: '多角色协同回答',
    offline_fallback: 'AI 暂时不可用 · 本地回复',
    clarification: '需要补充信息',
    general: '日常交流',
    general_knowledge: '通用知识',
    out_of_scope: '课程范围之外',
  }
  if (labels[mode]) return labels[mode]
  if (mode?.endsWith('_grounded')) return labels.model_grounded
  if (mode?.endsWith('_multimodal')) return labels.model_multimodal
  if (mode?.endsWith('_general')) return labels.model_general
  return '课程助教'
}

function renderMarkdown(content) {
  try {
    return DOMPurify.sanitize(markdown.render(content || ''))
  } catch {
    return `<p>${markdown.utils.escapeHtml(content || '')}</p>`
  }
}

function conversationTitle(questionText) {
  const title = (questionText || '')
    .replace(/\s+/g, ' ')
    .replace(/^(请问|麻烦问一下|麻烦问下|帮我|请帮我|能不能|可以帮我|告诉我|给我)[，,：:\s]*/u, '')
    .replace(/[？?。！!]+$/u, '')
    .trim()
  if (!title) return '图片问题'
  return title.length > 24 ? `${title.slice(0, 23).trim()}…` : title
}

function formatSessions(items) {
  return items.map(item => ({ ...item, title: conversationTitle(item.title || item.last_question) }))
}

function renderAssignmentText(content, module = '') {
  return DOMPurify.sanitize(assignmentMarkdown.render(formatAssignmentText(content, module)))
}

function openAssignmentImage(image) {
  assignmentImagePreview.value = image
}

async function handleCodeCopy(event) {
  const button = event.target.closest?.('[data-copy-code]')
  if (!button) return
  event.preventDefault()
  event.stopPropagation()
  const codeElement = button.parentElement?.querySelector('pre code')
  if (!codeElement) return
  const text = codeElement.textContent || ''
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.setAttribute('readonly', '')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.append(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      textarea.remove()
      if (!copied) throw new Error('Clipboard copy was rejected')
    }
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

async function loadThread(id, sequence = conversationOpenSequence) {
  const thread = await request(`/api/conversations?limit=100&session_id=${encodeURIComponent(id)}`)
  if (!thread.length) throw new Error('没有找到这段对话的历史消息，记录可能已被删除或迁移')
  if (sequence === conversationOpenSequence && sessionId.value === id) {
    messages.value = thread
    await scrollToLatest()
  }
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
    sessions.value = formatSessions(threadList)
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
  profileSaveMessage.value = ''
  error.value = ''
  try {
    studentProfile.value = await request('/api/student/profile', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(studentProfile.value),
    })
    profileSaveMessage.value = '信息已保存，之后的学习记录会归到你的班级。'
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
  teacherAssignments.value = { tasks: [], submissions: [], classes: [] }
  teacherTaskDetail.value = null
  teacherSelectedTaskId.value = ''
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
    await loadTeacherAssignments()
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

async function loadTeacherAssignments() {
  if (!teacherCode.value) return
  try {
    teacherAssignments.value = await request('/api/teacher/assignments')
  } catch (cause) {
    error.value = cause.message
  }
}

async function openTeacherAssignments() {
  teacherSection.value = 'assignments'
  await loadTeacherAssignments()
  if (teacherWorkspaceRef.value) teacherWorkspaceRef.value.scrollTop = 0
}

async function selectTeacherTask(task) {
  teacherSelectedTaskId.value = task.id
  teacherTaskEditing.value = false
  teacherTaskLoading.value = true
  selectedTeacherSubmission.value = null
  error.value = ''
  try {
    teacherTaskDetail.value = await request(`/api/teacher/assignments/${encodeURIComponent(task.id)}`)
    const current = teacherTaskDetail.value.task
    teacherTaskDraft.value = { title: current.title, description: current.description,
      scoring_rubric: current.scoring_rubric || '' }
  } catch (cause) {
    error.value = cause.message
  } finally {
    teacherTaskLoading.value = false
  }
}

async function saveTeacherTask() {
  if (!teacherTaskDetail.value || teacherTaskLoading.value) return
  teacherTaskLoading.value = true
  error.value = ''
  try {
    teacherTaskDetail.value = await request(`/api/teacher/assignments/${encodeURIComponent(teacherSelectedTaskId.value)}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...teacherTaskDraft.value,
        expected_version: teacherTaskDetail.value.task.version }),
    })
    teacherTaskEditing.value = false
    await loadTeacherAssignments()
  } catch (cause) {
    error.value = cause.message
  } finally {
    teacherTaskLoading.value = false
  }
}

async function downloadTeacherSubmissionBundle(submissionId, group = 'all') {
  error.value = ''
  try {
    const response = await fetch(`/api/teacher/submissions/${submissionId}/download?group=${group}`, {
      headers: { 'X-Teacher-Code': teacherCode.value },
    })
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || '下载失败')
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = `提交${submissionId}_${group === 'work' ? '作品' : group === 'report' ? '报告' : '完整材料'}.zip`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 30000)
  } catch (cause) {
    error.value = cause.message
  }
}

async function deleteTeacherSubmission() {
  const item = selectedTeacherSubmission.value
  if (!item || !window.confirm(`确定删除 ${item.student_name} 的这次提交吗？删除后学生和教师都无法在页面查看。`)) return
  error.value = ''
  try {
    await request(`/api/teacher/submissions/${item.id}`, { method: 'DELETE' })
    selectedTeacherSubmission.value = null
    await Promise.all([loadTeacherAssignments(), loadTeacherAnalytics()])
  } catch (cause) {
    error.value = cause.message
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
  const sequence = ++assignmentLoadSequence
  activeTab.value = 'assignments'
  assignmentDetailOpen.value = false
  assignmentDetailsLoading.value = false
  error.value = ''
  try {
    const result = await request('/api/assignments')
    if (sequence === assignmentLoadSequence) assignmentData.value = result
  } catch (cause) {
    if (sequence === assignmentLoadSequence) error.value = cause.message
  }
}

async function loadAssignmentDetails(item) {
  const sequence = ++assignmentLoadSequence
  assignmentDetailsLoading.value = true
  error.value = ''
  try {
    const [detail, submissions] = await Promise.all([
      request(`/api/assignments/${encodeURIComponent(item.id)}`),
      request(`/api/assignments/${encodeURIComponent(item.id)}/submissions?session_id=${encodeURIComponent(sessionId.value)}`),
    ])
    if (sequence !== assignmentLoadSequence || selectedAssignment.value?.id !== item.id) return
    selectedAssignment.value = detail
    assignmentSubmissions.value = submissions
    loadedAssignmentId.value = item.id
    if (submissions.length) {
      assignmentGrade.value = submissions[0].evaluation
      selectedSubmissionId.value = submissions[0].submission_id
    }
  } catch (cause) {
    if (sequence === assignmentLoadSequence) error.value = cause.message
  } finally {
    if (sequence === assignmentLoadSequence) assignmentDetailsLoading.value = false
  }
}

async function selectAssignment(item) {
  if (!assignmentDetailOpen.value && assignmentWorkspaceRef.value) {
    assignmentListScrollTop.value = assignmentWorkspaceRef.value.scrollTop
  }
  if (selectedAssignment.value?.id === item.id) {
    if (loadedAssignmentId.value !== item.id) {
      if (assignmentDetailsLoading.value) return
      await loadAssignmentDetails(item)
    }
    if (loadedAssignmentId.value !== item.id) return
    assignmentDetailOpen.value = true
    await nextTick()
    if (assignmentWorkspaceRef.value) assignmentWorkspaceRef.value.scrollTop = 0
    return
  }
  const hasDraft = assignmentWorkText.value.trim() || assignmentReportText.value.trim()
    || assignmentWorkFiles.value.length || assignmentReportFiles.value.length
    || assignmentTutorTurns.value.length || assignmentRevisionId.value !== null
  if (hasDraft && !window.confirm('切换任务会清空当前未提交内容，是否继续？')) return
  selectedAssignment.value = item
  assignmentTutorOpen.value = false
  assignmentDetailsLoading.value = false
  loadedAssignmentId.value = ''
  assignmentWorkText.value = ''
  assignmentReportText.value = ''
  assignmentWorkFiles.value = []
  assignmentReportFiles.value = []
  assignmentGrade.value = null
  assignmentSubmissions.value = []
  assignmentRevisionId.value = null
  retainedAssignmentFiles.value = []
  selectedSubmissionId.value = null
  assignmentTutorTurns.value = []
  assignmentTutorInput.value = ''
  await loadAssignmentDetails(item)
  if (selectedAssignment.value?.id !== item.id || loadedAssignmentId.value !== item.id) return
  assignmentDetailOpen.value = true
  await nextTick()
  if (assignmentWorkspaceRef.value) assignmentWorkspaceRef.value.scrollTop = 0
}

async function backToAssignmentList() {
  assignmentDetailOpen.value = false
  await nextTick()
  if (!assignmentWorkspaceRef.value) return
  assignmentWorkspaceRef.value.scrollTop = assignmentListScrollTop.value
  assignmentWorkspaceRef.value.querySelector('.assignment-card-select.active')?.focus({ preventScroll: true })
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
    await nextTick()
    if (assignmentWorkspaceRef.value) assignmentWorkspaceRef.value.scrollTop = 0
  } catch (cause) {
    error.value = cause.message
  } finally {
    assignmentSubmitting.value = false
  }
}

function newAssignmentSubmission() {
  const hasDraft = assignmentWorkText.value.trim() || assignmentReportText.value.trim()
    || assignmentWorkFiles.value.length || assignmentReportFiles.value.length
    || retainedAssignmentFiles.value.length || assignmentRevisionId.value !== null
  if (hasDraft && !window.confirm('开始一份新提交会清空当前未提交的作品与报告内容，是否继续？')) return
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
  nextTick(() => { if (assignmentWorkspaceRef.value) assignmentWorkspaceRef.value.scrollTop = 0 })
}

function showAssignmentGradeDetail() {
  document.getElementById('assignment-grade-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
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
  await nextTick()
  await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  if (teacherWorkspaceRef.value) teacherWorkspaceRef.value.scrollTop = 0
  if (!teacherCode.value) return
  try {
    const [overview, analytics, assignments] = await Promise.all([
      request('/api/teacher/overview'),
      request(`/api/teacher/analytics?${new URLSearchParams(Object.entries(teacherFilter.value).filter(([, value]) => value)).toString()}`),
      request('/api/teacher/assignments'),
    ])
    teacherData.value = overview
    teacherAnalytics.value = analytics
    teacherAssignments.value = assignments
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
  const isNewSession = !sessions.value.some(item => item.session_id === targetSessionId)
  if (isNewSession) {
    sessions.value.unshift({
      session_id: targetSessionId,
      title: conversationTitle(prompt),
      last_question: prompt,
      updated_at: new Date().toISOString(),
      count: 0,
      kind: 'chat',
      pending: true,
    })
  }
  const submittedImage = selectedImage.value
  const imageDataUrl = submittedImage?.dataUrl || null
  loading.value = true
  pendingQuestion.value = prompt
  pendingImage.value = submittedImage
  question.value = ''
  selectedImage.value = null
  if (imageInput.value) imageInput.value.value = ''
  waitSeconds.value = 0
  const waitTimer = window.setInterval(() => { waitSeconds.value += 1 }, 1000)
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
    pendingImage.value = null
    sessions.value = formatSessions(await request('/api/conversations/sessions'))
    await scrollToLatest()
  } catch (cause) {
    if (isNewSession) sessions.value = sessions.value.filter(item => item.session_id !== targetSessionId)
    pendingQuestion.value = ''
    pendingImage.value = null
    if (sessionId.value === targetSessionId && !question.value.trim() && !selectedImage.value) {
      question.value = text
      selectedImage.value = submittedImage
    }
    error.value = cause.message
  } finally {
    window.clearInterval(waitTimer)
    waitSeconds.value = 0
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
  const sequence = ++conversationOpenSequence
  activeTab.value = item.kind === 'code' ? 'code' : 'ask'
  sessionId.value = item.session_id
  localStorage.setItem('teaching-assistant-session', sessionId.value)
  selectedModule.value = '全部模块'
  question.value = ''
  pendingQuestion.value = ''
  sourceDetail.value = null
  messages.value = []
  openingSessionId.value = item.session_id
  removeImage()
  error.value = ''
  try {
    if (item.kind === 'code') await openCode()
    else await loadThread(sessionId.value, sequence)
  } catch (cause) {
    if (sequence === conversationOpenSequence) error.value = `这段对话暂时无法打开：${cause.message}`
  } finally {
    if (sequence === conversationOpenSequence) openingSessionId.value = ''
  }
}

function newConversation() {
  sidebarOpen.value = false
  conversationOpenSequence += 1
  openingSessionId.value = ''
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
    sessions.value = formatSessions(await request('/api/conversations/sessions'))
  } catch (cause) {
    error.value = cause.message
  } finally {
    loading.value = false
  }
}

function syncCodeLineNumbers(event) {
  if (codeLineNumbersRef.value) codeLineNumbersRef.value.scrollTop = event.target.scrollTop
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
  <div class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <button v-if="sidebarOpen" class="sidebar-scrim" type="button" aria-label="关闭导航" @click="sidebarOpen = false"></button>
    <aside class="sidebar" :class="{ 'sidebar-open': sidebarOpen }">
      <div class="brand">
        <div class="brand-mark"><img :src="BrandMark" alt="" /></div>
        <div class="brand-copy"><strong>物联智学</strong><small>物联网综合实训</small></div>
        <button class="sidebar-collapse" type="button" :aria-label="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'" :title="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'" @click="sidebarCollapsed = !sidebarCollapsed"><span aria-hidden="true">{{ sidebarCollapsed ? '›' : '‹' }}</span></button>
        <button class="sidebar-close" type="button" aria-label="关闭导航" @click="sidebarOpen = false">×</button>
      </div>
      <div class="sidebar-tools">
        <div class="sidebar-section-label">学习空间</div>
        <div class="sidebar-nav-list" :style="{ '--nav-index': activeNavIndex }">
          <span class="nav-selection-indicator" aria-hidden="true"></span>
          <button class="tool-button" aria-label="课程问答" title="课程问答" :class="{ selected: activeTab === 'ask' }" @click="activeTab = 'ask'; sidebarOpen = false"><span class="nav-glyph"><MessageCircleQuestion :size="20" :stroke-width="1.8" /></span><span>课程问答</span></button>
          <button class="tool-button" aria-label="任务验收" title="任务验收" :class="{ selected: activeTab === 'assignments' }" @click="openAssignments(); sidebarOpen = false"><span class="nav-glyph"><ClipboardCheck :size="20" :stroke-width="1.8" /></span><span>任务验收</span></button>
          <button class="tool-button" aria-label="代码分析" title="代码分析" :class="{ selected: activeTab === 'code' }" @click="openCode(); sidebarOpen = false"><span class="nav-glyph"><CodeXml :size="20" :stroke-width="1.8" /></span><span>代码分析</span></button>
          <button class="tool-button" aria-label="学习回顾" title="学习回顾" :class="{ selected: activeTab === 'progress' }" @click="openProgress(); sidebarOpen = false"><span class="nav-glyph"><ChartNoAxesCombined :size="20" :stroke-width="1.8" /></span><span>学习回顾</span></button>
          <button class="tool-button" aria-label="我的信息" title="我的信息" :class="{ selected: activeTab === 'profile' }" @click="activeTab = 'profile'; sidebarOpen = false"><span class="nav-glyph"><CircleUserRound :size="20" :stroke-width="1.8" /></span><span>我的信息</span></button>
          <button class="tool-button" aria-label="教师工作台" title="教师工作台" :class="{ selected: activeTab === 'teacher' }" @click="openTeacher(); sidebarOpen = false"><span class="nav-glyph"><GraduationCap :size="20" :stroke-width="1.8" /></span><span>教师工作台</span></button>
        </div>
      </div>
      <div class="conversation-heading"><span>最近对话</span><button class="new-chat-button" aria-label="新建对话" title="新建对话" @click="newConversation"><span>＋</span><span class="new-chat-label">新建对话</span></button></div>
      <div class="history-list">
        <div v-for="item in sessions" :key="item.session_id" class="history-row" :class="{ selected: sessionId === item.session_id && activeTab === 'ask' }">
          <button class="history-item" :title="item.title" :disabled="item.pending" @click="openConversation(item); sidebarOpen = false">{{ item.title }}</button>
          <button class="delete-button" title="删除对话" aria-label="删除对话" @click.stop="deleteConversation(item)">×</button>
        </div>
        <p v-if="!sessions.length" class="sidebar-empty">发送第一条课程问题后，对话会出现在这里。</p>
      </div>
      <div class="sidebar-foot">{{ status?.model_configured ? '课程资料库已连接' : '本地课件可用' }}</div>
    </aside>

    <main class="main-content">
      <header class="topbar">
        <button class="nav-toggle" type="button" aria-label="打开导航" @click="sidebarOpen = true"><span></span><span></span><span></span></button>
        <div class="topbar-heading"><small>物联网综合实训 / 学习工作区</small><strong>{{ activeTab === 'ask' ? '课程问答' : activeTab === 'assignments' ? '任务验收' : activeTab === 'code' ? '代码分析' : activeTab === 'progress' ? '学习回顾' : activeTab === 'profile' ? '我的信息' : '教师工作台' }}</strong></div>
        <div class="topbar-meta">
          <span class="knowledge-count">资料库 {{ status?.knowledge?.ppt_documents || 0 }} 份 PPT / {{ status?.knowledge?.ppt_pages || 0 }} 页<span v-if="status?.knowledge?.documents > status?.knowledge?.ppt_documents"> / {{ status.knowledge.documents - status.knowledge.ppt_documents }} 份补充资料</span></span>
          <span class="status-pill"><span class="status-dot"></span>{{ status?.model_configured ? 'AI 助教已就绪' : '本地课件模式' }}</span>
        </div>
      </header>

      <div v-if="error" class="alert" role="alert">{{ error }}</div>

      <Transition name="page">
      <section v-if="activeTab === 'ask'" class="ask-view" key="ask">
        <section v-if="openingSessionId && isEmptyThread" class="thread-opening" role="status" aria-live="polite">
          <span class="opening-spinner" aria-hidden="true"></span>
          <strong>正在打开这段对话…</strong>
          <small>正在载入历史消息和图片</small>
        </section>
        <section v-else-if="isEmptyThread" class="welcome-panel">
          <div class="welcome-copy">
            <h1>今天想解决什么问题？</h1>
            <p>课程知识、实验步骤、代码问题，随时向 AI 助教提问。</p>
          </div>
          <div class="welcome-content">
          <form class="composer-dock welcome-composer" @submit.prevent="ask" @paste="pasteImage($event, 'chat')">
            <div class="composer">
              <div v-if="selectedImage" class="image-attachment"><img :src="selectedImage.dataUrl" alt="待发送图片预览"><span>{{ selectedImage.name }}</span><button type="button" aria-label="移除图片" @click="removeImage">×</button></div>
              <textarea ref="questionInput" v-model="question" rows="2" maxlength="2000" :disabled="loading" placeholder="向物联智学提问..." @input="resizeQuestionInput($event.target)" @keydown.enter.exact.prevent="ask"></textarea>
              <div class="composer-footer"><div class="composer-tools"><input ref="imageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="selectImage"><button type="button" class="attach-button" :disabled="loading" @click="imageInput?.click()"><Paperclip :size="16" :stroke-width="1.9" aria-hidden="true" /><span>添加图片</span></button><span class="composer-source-note"><BookOpen :size="14" :stroke-width="1.8" aria-hidden="true" />AI 回答优先引用课程资料</span></div><button class="send-button" type="submit" :disabled="loading || (!question.trim() && !selectedImage)" aria-label="发送消息" title="发送消息"><ArrowUp v-if="!loading" :size="20" :stroke-width="2.2" aria-hidden="true" /><span v-else class="send-spinner" aria-hidden="true"></span></button></div>
            </div>
          </form>
          <div class="welcome-flow" aria-label="选择课程模块">
            <div class="flow-heading"><strong>课程模块</strong><span>可按模块缩小检索范围</span></div>
            <button v-for="module in modules" :key="module" type="button" class="flow-node" :class="{ active: selectedModule === module }" @click="selectedModule = module"><component :is="moduleIcons[module]" :size="15" :stroke-width="1.8" aria-hidden="true" /><span>{{ module }}</span></button>
          </div>
          <div class="welcome-start"><strong>快捷提问</strong><span>点击后可编辑，再发送。</span></div>
          <div class="welcome-samples">
            <button v-for="sample in sampleCards" :key="sample.question" type="button" class="sample-card" :class="`tone-${sample.tone}`" @click="chooseSample(sample.question)">
              <span class="sample-card-category"><component :is="sample.icon" :size="15" :stroke-width="1.9" aria-hidden="true" />{{ sample.category }}</span>
              <span class="sample-card-question">{{ sample.question }}</span>
              <ArrowUpRight class="sample-card-arrow" :size="17" :stroke-width="1.8" aria-hidden="true" />
            </button>
          </div>
          <button v-if="!studentProfile.registered" type="button" class="profile-prompt" @click="activeTab = 'profile'"><CircleUserRound :size="15" :stroke-width="1.8" aria-hidden="true" /><span>完善学习档案</span></button>
          <section v-if="status && !status.knowledge.documents" class="empty-knowledge">
            <p>课程知识库尚未导入。导入配置好的课程 PPT 后即可按课件检索。</p>
            <p>请联系教师在工作台导入课程资料。</p>
          </section>
          </div>
        </section>

        <section v-else ref="messageList" class="message-list" aria-live="polite">
          <article v-for="message in messages" :key="message.id" class="message-pair">
            <div class="user-message"><div class="avatar user-avatar">我</div><div class="message-bubble user-bubble">{{ message.question }}<img v-if="message.image_url" class="chat-user-image" :src="message.image_url" alt="本轮上传的图片"></div></div>
            <div class="assistant-message">
              <div class="avatar assistant-avatar">IoT</div>
              <div class="assistant-content">
                <div class="assistant-name">课程助教 <span v-if="message.mode" class="response-label">{{ responseLabel(message.mode) }}</span></div>
                <div class="message-bubble assistant-bubble" @click="handleCodeCopy" v-html="renderMarkdown(message.answer)"></div>
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
            <div class="user-message"><div class="avatar user-avatar">我</div><div class="message-bubble user-bubble"><img v-if="pendingImage" class="chat-user-image" :src="pendingImage.dataUrl" :alt="pendingImage.name || '本轮上传的图片'"><span>{{ pendingQuestion }}</span></div></div>
            <div class="typing-indicator" role="status" aria-live="polite"><span></span><span></span><span></span><small>{{ waitingStatus }}<template v-if="waitSeconds >= 10"> · 已等待 {{ waitSeconds }} 秒</template></small></div>
          </article>
        </section>

        <Transition name="modal">
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
        </Transition>

        <form v-if="!isEmptyThread" class="composer-dock" @submit.prevent="ask" @paste="pasteImage($event, 'chat')">
          <div class="module-row">
            <button v-for="module in modules" :key="module" type="button" class="module-chip" :class="{ active: selectedModule === module }" @click="selectedModule = module"><component :is="moduleIcons[module]" :size="15" :stroke-width="1.8" aria-hidden="true" /><span>{{ module }}</span></button>
          </div>
          <div class="composer">
            <div v-if="selectedImage" class="image-attachment"><img :src="selectedImage.dataUrl" alt="待发送图片预览"><span>{{ selectedImage.name }}</span><button type="button" aria-label="移除图片" @click="removeImage">×</button></div>
            <textarea ref="questionInput" v-model="question" rows="2" maxlength="2000" :disabled="loading" :placeholder="loading ? '本轮已发送，等待助教回复…' : '向物联智学提问...'" @input="resizeQuestionInput($event.target)" @keydown.enter.exact.prevent="ask"></textarea>
            <div class="composer-footer"><div class="composer-tools"><input ref="imageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="selectImage"><button type="button" class="attach-button" :disabled="loading" @click="imageInput?.click()"><Paperclip :size="16" :stroke-width="1.9" aria-hidden="true" /><span>添加图片</span></button><span class="composer-source-note"><BookOpen :size="14" :stroke-width="1.8" aria-hidden="true" />AI 回答优先引用课程资料</span></div><button class="send-button" type="submit" :disabled="loading || (!question.trim() && !selectedImage)" :aria-label="loading ? '正在回复' : '发送消息'" :title="loading ? '正在回复' : '发送消息'"><ArrowUp v-if="!loading" :size="20" :stroke-width="2.2" aria-hidden="true" /><span v-else class="send-spinner" aria-hidden="true"></span></button></div>
          </div>
        </form>
      </section>

      <section v-else-if="activeTab === 'code'" class="code-workspace" @paste="pasteImage($event, 'code')">
        <div class="code-heading"><h1>粘贴代码，定位问题。</h1><p>查看带行号的静态检查结果，也可以附上报错截图继续追问。这里不会运行代码；启用 AI 时，请勿粘贴密钥。</p></div>
        <div v-if="!codeHistory.length" class="code-options"><label>代码语言<CustomSelect v-model="codeLanguage" :options="codeLanguages" aria-label="代码语言" /></label><label>课程模块<CustomSelect v-model="codeModule" :options="[{ value: '', label: '未指定' }, ...modules.slice(1)]" aria-label="课程模块" /></label></div>
        <Transition name="result" mode="out-in">
        <div v-if="!codeHistory.length" class="code-editor" key="code-editor">
          <pre ref="codeLineNumbersRef" class="code-line-numbers" aria-hidden="true">{{ codeLineNumbers }}</pre>
          <textarea v-model="code" class="code-box" spellcheck="false" wrap="off" maxlength="20000" rows="15" aria-label="待分析代码" @scroll="syncCodeLineNumbers"></textarea>
          <div v-if="!code.trim()" class="code-editor-guide"><strong>粘贴代码开始分析</strong><span>支持 Python、C/C++、Java、JavaScript、HTML 和 CSS</span></div>
        </div>
        <div v-else class="code-review-layout" key="code-results">
          <div class="code-thread-toolbar"><label>代码语言<CustomSelect v-model="codeLanguage" :options="codeLanguages" aria-label="代码语言" /></label><label>课程模块<CustomSelect v-model="codeModule" :options="[{ value: '', label: '未指定' }, ...modules.slice(1)]" aria-label="课程模块" /></label><details class="code-source-editor"><summary>查看或修改当前代码</summary><div class="code-editor compact"><pre ref="codeLineNumbersRef" class="code-line-numbers" aria-hidden="true">{{ codeLineNumbers }}</pre><textarea v-model="code" class="code-box" spellcheck="false" wrap="off" maxlength="20000" rows="12" aria-label="当前代码" @scroll="syncCodeLineNumbers"></textarea></div></details></div>
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
        </div>
        </Transition>
        <div v-if="codeImage" class="image-attachment code-image-attachment"><img :src="codeImage.dataUrl" alt="待分析图片预览"><span>{{ codeImage.name }}</span><button type="button" aria-label="移除图片" @click="codeImage = null">×</button></div>
        <form v-if="!codeHistory.length" class="code-initial-form" @submit.prevent="analyze">
          <label class="code-context-label">补充报错或运行现象 <span>选填</span><textarea v-model="codeContext" rows="2" maxlength="1000" placeholder="例如：运行到第 18 行时报错，预期结果是……（Enter 分析，Shift + Enter 换行）" @keydown.enter.exact.prevent="analyze"></textarea></label>
          <div class="code-initial-footer"><span>{{ code.trim() ? `${codeLineCount} 行代码` : codeImage ? '已添加图片，可直接分析' : '先粘贴代码或添加截图，再开始分析' }}</span><button class="send-button" :disabled="loading || (!code.trim() && !codeImage)">{{ loading ? '分析中…' : '分析代码 ↑' }}</button></div>
        </form>
        <form v-else class="code-composer" @submit.prevent="analyze">
          <textarea v-model="codeContext" rows="2" maxlength="1000" placeholder="继续追问这段代码…（Enter 发送，Shift + Enter 换行）" @keydown.enter.exact.prevent="analyze"></textarea>
          <button class="send-button" :disabled="loading || (!code.trim() && !codeImage)">{{ loading ? '分析中…' : '发送 ↑' }}</button>
        </form>
      </section>

      <section v-else-if="activeTab === 'assignments'" ref="assignmentWorkspaceRef" class="assignment-workspace">
        <template v-if="!assignmentDetailOpen">
          <div class="assignment-hero"><div><h1>选择任务，提交你的实现。</h1><p>按指导手册提交代码、功能证据和实验报告。验收反馈会列出已确认的部分与待核实的部分。</p></div><div class="assignment-hero-stat"><strong>{{ assignmentData.items.length }}</strong><span>项可选任务</span></div></div>
          <div class="assignment-filters"><CustomSelect v-model="assignmentModule" :options="['全部模块', ...assignmentData.modules]" aria-label="筛选课程模块" /><input v-model="assignmentQuery" type="search" aria-label="搜索任务" placeholder="搜索任务名称、课次或内容…"><button v-if="assignmentQuery || assignmentModule !== '全部模块'" type="button" class="filter-clear" @click="assignmentQuery = ''; assignmentModule = '全部模块'">清除筛选</button></div>
          <p class="quiet assignment-count">找到 {{ visibleAssignments.length }} 项任务 · 选择任务后可提交或针对性提问</p>
          <div class="assignment-layout">
            <div class="assignment-list">
              <section v-for="group in assignmentGroups" :key="`${group.module}-${group.source}`" class="assignment-group">
                <button type="button" class="assignment-group-heading" :aria-expanded="!collapsedAssignmentGroups.has(`${group.module}-${group.source}`)" @click="toggleAssignmentGroup(`${group.module}-${group.source}`)"><span class="group-chevron">{{ collapsedAssignmentGroups.has(`${group.module}-${group.source}`) ? '▸' : '▾' }}</span><strong>{{ group.module }}</strong><span class="group-source" :title="group.source">{{ group.source }}</span><small>{{ group.items.length }} 项</small></button>
                <div class="assignment-group-body" :class="{ collapsed: collapsedAssignmentGroups.has(`${group.module}-${group.source}`) }">
                  <TransitionGroup name="task-row" tag="div" class="assignment-group-items">
                    <button v-for="item in collapsedAssignmentGroups.has(`${group.module}-${group.source}`) ? [] : group.items" :key="item.id" class="assignment-card assignment-card-select" :class="{ active: selectedAssignment?.id === item.id }" :disabled="assignmentDetailsLoading && selectedAssignment?.id === item.id" @click="selectAssignment(item)">
                      <strong>{{ item.title }}</strong>
                      <span :title="item.rubric_available ? '含手册评分点' : item.rubric_note">{{ assignmentDetailsLoading && selectedAssignment?.id === item.id ? '正在打开任务…' : item.rubric_available ? '含手册评分点' : '评分待教师确认' }}</span>
                    </button>
                  </TransitionGroup>
                </div>
              </section>
            </div>
          </div>
          <p v-if="!visibleAssignments.length" class="quiet">没有找到匹配的指导手册任务；请确认两份指导手册已加入知识库。</p>
        </template>

        <section v-else-if="selectedAssignment" class="assignment-detail-page" aria-labelledby="assignment-page-title">
          <header class="assignment-detail-heading">
            <button type="button" class="assignment-back-button" @click="backToAssignmentList">← 返回任务列表</button>
            <div class="assignment-detail-titlebar">
              <div class="assignment-detail-title">
                <div class="assignment-card-meta"><span>{{ selectedAssignment.module }}</span><span>{{ selectedAssignment.source }}</span></div>
                <h1 id="assignment-page-title">{{ selectedAssignment.title }}</h1>
              </div>
              <span class="assignment-status-pill" :class="{ busy: assignmentSubmitting || assignmentDetailsLoading, submitted: selectedAssignmentSubmission }" role="status">{{ assignmentStatusLabel }}</span>
            </div>
          </header>

          <section v-if="assignmentGrade" class="assignment-result-banner" aria-live="polite">
            <div><span>AI 验收结果 · 第 {{ selectedSubmissionId }} 次提交</span><strong>{{ assignmentGrade.total_score }} 分</strong><small>作品 {{ assignmentGrade.acceptance_score }} 分 × 70% ＋ 报告 {{ assignmentGrade.report_score }} 分 × 30%</small></div>
            <button type="button" class="secondary-button" @click="showAssignmentGradeDetail">查看评分明细 ↓</button>
          </section>
          <div class="assignment-detail-layout">
            <main class="assignment-guide-column">
              <section class="assignment-guide-section">
                <header class="assignment-section-heading"><div><h2>任务要求</h2><p>课程目标、实现内容与手册原文</p></div><BookOpen :size="19" :stroke-width="1.8" aria-hidden="true" /></header>
                <p v-if="assignmentDetailsLoading" class="assignment-content-loading" role="status">正在读取完整手册要求与提交记录…</p>
                <div v-else class="assignment-manual-text" @click="handleCodeCopy" v-html="renderAssignmentText(selectedAssignment.description, selectedAssignment.module)"></div>
                <div v-if="!assignmentDetailsLoading && selectedAssignment.images?.length" class="assignment-manual-images">
                  <figure v-for="image in selectedAssignment.images" :key="image.url">
                    <button type="button" class="assignment-image-trigger" :aria-label="`放大查看${image.alt}`" @click="openAssignmentImage(image)"><img :src="image.url" :alt="image.alt" :width="image.width" :height="image.height" loading="lazy"></button>
                    <figcaption>{{ image.alt }}</figcaption>
                  </figure>
                </div>
              </section>

              <details class="assignment-rubric-section" :open="!selectedAssignment.rubric_available">
                <summary><span><strong>代码与功能验收标准</strong><small>作品验收 70% · 实验报告 30%</small></span><span class="rubric-summary-note">{{ selectedAssignment.rubric_available ? '查看评分点' : '当前手册未提供分项评分点' }}</span></summary>
                <div class="assignment-manual-text" @click="handleCodeCopy" v-html="renderAssignmentText(selectedAssignment.scoring_rubric || selectedAssignment.rubric_note, selectedAssignment.module)"></div>
              </details>
              <p class="assignment-scoring-note">验收重点是代码实现与功能完整度。环境搭建不计分；仅凭代码无法确认的运行效果会单独列出，方便补充证据。</p>

              <section v-if="assignmentSubmissions.length" class="submission-history">
                <div class="submission-history-heading"><h2>提交记录</h2><button type="button" class="secondary-button" @click="newAssignmentSubmission">＋ 重新提交</button></div>
                <div v-for="item in assignmentSubmissions" :key="item.submission_id" class="submission-history-row" :class="{ selected: selectedSubmissionId === item.submission_id }">
                  <button type="button" class="submission-history-main" @click="showAssignmentSubmission(item)"><strong>第 {{ item.submission_id }} 次提交 · AI {{ item.total_score }} 分<span v-if="item.teacher_final_score !== null"> · 教师 {{ item.teacher_final_score }} 分</span></strong><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }} · {{ item.teacher_review_status === 'approved' ? '教师已确认' : item.teacher_review_status === 'needs_revision' ? '教师建议修订' : '待教师复核' }}</small></button>
                  <button type="button" class="record-action" @click="reviseAssignmentSubmission(item)">修订</button>
                  <button type="button" class="record-action danger" @click="deleteAssignmentSubmission(item)">删除</button>
                </div>
              </section>

              <section v-if="assignmentGrade" id="assignment-grade-detail" class="assignment-grade">
                <h2>AI 验收反馈 <small>{{ selectedAssignmentSubmission?.created_at ? new Date(selectedAssignmentSubmission.created_at).toLocaleString('zh-CN') : '' }}</small></h2>
                <div class="grade-score-row"><div><strong>{{ assignmentGrade.acceptance_score }}</strong><span>现场验收 / 100 · 权重 70%</span></div><div><strong>{{ assignmentGrade.report_score }}</strong><span>实验报告 / 100 · 权重 30%</span></div><div class="grade-total"><strong>{{ assignmentGrade.total_score }}</strong><span>加权总分 / 100</span></div></div>
                <div v-if="selectedAssignmentSubmission" class="teacher-feedback"><strong>教师复核：{{ selectedAssignmentSubmission.teacher_review_status === 'approved' ? '已确认' : selectedAssignmentSubmission.teacher_review_status === 'needs_revision' ? '建议修订' : '待复核' }}</strong><span v-if="selectedAssignmentSubmission.teacher_final_score !== null">最终分数：{{ selectedAssignmentSubmission.teacher_final_score }}</span><p v-if="selectedAssignmentSubmission.teacher_review_note">{{ selectedAssignmentSubmission.teacher_review_note }}</p></div>
                <div v-if="selectedAssignmentSubmission?.attachments?.length" class="teacher-submission-files"><button v-for="attachment in selectedAssignmentSubmission.attachments" :key="attachment.index" class="attach-button" @click="downloadSubmissionFile(selectedAssignmentSubmission.submission_id, attachment)">下载{{ attachment.group === 'work' ? '作品' : '报告' }}：{{ attachment.filename }}</button></div>
                <div v-if="assignmentGrade.policy_version !== 'code_function_focus_v2'" class="grade-old-policy"><p>这条历史评分使用旧评分规则，曾把环境搭建纳入评分。可以直接使用本次已保存的提交材料重新评分。</p><button class="secondary-button" :disabled="assignmentSubmitting" @click="regradeAssignment">{{ assignmentSubmitting ? '重新评分中…' : '按代码与功能规则重新评分' }}</button></div>
                <p class="grade-status">{{ assignmentGrade.status }}</p>
                <h3>作品验收评分</h3><div v-for="(item, index) in assignmentGrade.acceptance_items || []" :key="'a' + index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.evidence }}</p><p>{{ item.feedback }}</p></div>
                <h3>报告评分</h3><div v-for="(item, index) in assignmentGrade.report_items || []" :key="'r' + index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.evidence }}</p><p>{{ item.feedback }}</p></div>
                <div v-if="assignmentGrade.issues?.length" class="grade-feedback"><strong>需要改进</strong><ul><li v-for="(item, index) in assignmentGrade.issues" :key="index">{{ item }}</li></ul></div>
                <div v-if="assignmentGrade.next_steps?.length" class="grade-feedback"><strong>下一步建议</strong><ul><li v-for="(item, index) in assignmentGrade.next_steps" :key="index">{{ item }}</li></ul></div>
                <div v-if="assignmentGrade.verification_limits?.length" class="grade-feedback"><strong>当前材料无法验证</strong><ul><li v-for="(item, index) in assignmentGrade.verification_limits" :key="index">{{ item }}</li></ul></div>
                <p class="quiet">这是 AI 初评，用于学习反馈；现场表现和正式成绩仍由教师确认。</p>
              </section>
            </main>

            <aside class="assignment-action-column" aria-label="任务操作">
              <Transition name="panel" mode="out-in">
                <section v-if="!assignmentTutorOpen" class="assignment-submit-panel" aria-labelledby="assignment-submit-title">
                  <header class="assignment-submit-heading"><div><span>任务操作</span><h2 id="assignment-submit-title">{{ assignmentRevisionId ? '修订本次提交' : '提交作品' }}</h2></div><span class="assignment-status-pill" :class="{ busy: assignmentSubmitting || assignmentDetailsLoading }">{{ assignmentDetailsLoading ? '载入中' : assignmentSubmitting ? '验收中' : assignmentRevisionId ? '修订中' : 'AI 验收' }}</span></header>
                  <form class="assignment-submit" @submit.prevent="submitAssignment">
                    <section class="assignment-form-block"><h3>作品与代码</h3><label>功能说明、代码或运行证据<textarea v-model="assignmentWorkText" rows="5" placeholder="描述完成的功能、关键实现，或粘贴代码和验收说明。也可以上传源码、项目 ZIP、截图。" @paste="pasteAssignmentImage($event, 'work')"></textarea></label>
                      <div class="assignment-upload-row"><input ref="assignmentWorkInput" type="file" multiple accept=".zip,.py,.c,.h,.cpp,.hpp,.java,.js,.html,.css,.json,.xml,.md,.ino,.sql,.txt,.pdf,.docx,.png,.jpg,.jpeg,.webp" hidden @change="addSubmissionFiles($event, 'work')"><button type="button" class="attach-button" :disabled="assignmentSubmitting" @click="assignmentWorkInput?.click()">＋ 添加作品附件</button><span v-for="file in retainedAssignmentFiles.filter(item => item.group === 'work')" :key="`old-work-${file.index}`" class="submission-file"><span><strong>{{ file.filename }}</strong><small>已提交附件 · {{ file.filename.split('.').pop()?.toUpperCase() || 'FILE' }}</small></span><button type="button" aria-label="移除保留附件" @click="retainedAssignmentFiles = retainedAssignmentFiles.filter(item => item.index !== file.index)">×</button></span><span v-for="(file, index) in assignmentWorkFiles" :key="file.filename + index" class="submission-file"><span><strong>{{ file.filename }}</strong><small>待提交 · {{ file.filename.split('.').pop()?.toUpperCase() || 'FILE' }}</small></span><button type="button" :aria-label="`移除 ${file.filename}`" @click="assignmentWorkFiles.splice(index, 1)">×</button></span></div>
                    </section>
                    <section class="assignment-form-block"><h3>实验报告</h3><a v-if="selectedAssignment.report_template" class="assignment-template-link" :href="selectedAssignment.report_template.url" :download="selectedAssignment.report_template.name"><span>↓ 下载报告模板</span><small>{{ selectedAssignment.report_template.name }}</small></a><label>报告内容<textarea v-model="assignmentReportText" rows="4" placeholder="粘贴报告内容，或上传 DOCX / PDF 报告。报告按课程标准占总评 30%。" @paste="pasteAssignmentImage($event, 'report')"></textarea></label>
                      <div class="assignment-upload-row"><input ref="assignmentReportInput" type="file" multiple accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp" hidden @change="addSubmissionFiles($event, 'report')"><button type="button" class="attach-button" :disabled="assignmentSubmitting" @click="assignmentReportInput?.click()">＋ 添加报告附件</button><span v-for="file in retainedAssignmentFiles.filter(item => item.group === 'report')" :key="`old-report-${file.index}`" class="submission-file"><span><strong>{{ file.filename }}</strong><small>已提交附件 · {{ file.filename.split('.').pop()?.toUpperCase() || 'FILE' }}</small></span><button type="button" aria-label="移除保留附件" @click="retainedAssignmentFiles = retainedAssignmentFiles.filter(item => item.index !== file.index)">×</button></span><span v-for="(file, index) in assignmentReportFiles" :key="file.filename + index" class="submission-file"><span><strong>{{ file.filename }}</strong><small>待提交 · {{ file.filename.split('.').pop()?.toUpperCase() || 'FILE' }}</small></span><button type="button" :aria-label="`移除 ${file.filename}`" @click="assignmentReportFiles.splice(index, 1)">×</button></span></div>
                    </section>
                    <button class="send-button assignment-submit-button" :disabled="assignmentSubmitting || assignmentDetailsLoading">{{ assignmentDetailsLoading ? '正在载入任务…' : assignmentSubmitting ? '正在验收评分…' : assignmentRevisionId ? '保存修订并重新评分' : assignmentSubmissions.length ? '重新提交并评分' : '提交并评分' }}</button>
                    <button v-if="assignmentRevisionId" type="button" class="text-button" @click="newAssignmentSubmission">取消修订</button>
                    <p class="quiet">支持 DOCX、PDF、ZIP、代码文件和 PNG/JPEG/WebP 图片；普通附件最大 10 MB，图片最大 5 MB。截图无法证明未展示的实际运行效果。</p>
                  </form>
                </section>
                <section v-else class="assignment-tutor-panel" aria-labelledby="assignment-tutor-title">
                  <header class="assignment-tutor-heading"><button type="button" class="text-button" @click="assignmentTutorOpen = false">← 返回提交</button><span>当前任务</span><h2 id="assignment-tutor-title">任务助教</h2><p>可以询问任务概念、报错原因、实现思路或评分点。</p></header>
                <div class="assignment-tutor-thread" role="log" aria-live="polite"><p v-if="!assignmentTutorTurns.length" class="assignment-tutor-empty">围绕「{{ selectedAssignment.title }}」提问，助教会结合任务要求回答。</p><div v-for="(turn, index) in assignmentTutorTurns" :key="index" :class="turn.role === 'user' ? 'tutor-user-turn' : 'tutor-assistant-turn'"><strong>{{ turn.role === 'user' ? '我' : '助教' }}</strong><div class="assistant-bubble" @click="handleCodeCopy" v-html="renderMarkdown(turn.content)"></div></div><p v-if="assignmentTutorLoading" class="quiet" role="status">助教正在整理回复…</p></div>
                  <form class="assignment-tutor-composer" @submit.prevent="askAssignment"><textarea v-model="assignmentTutorInput" rows="2" maxlength="1500" aria-label="向任务助教提问" placeholder="描述你卡住的步骤或报错…（Enter 发送，Shift + Enter 换行）" @keydown.enter.exact.prevent="askAssignment"></textarea><button class="send-button" :disabled="assignmentTutorLoading || !assignmentTutorInput.trim()">{{ assignmentTutorLoading ? '思考中…' : '提问' }}</button></form>
                </section>
              </Transition>
              <button v-if="!assignmentTutorOpen" type="button" class="assignment-tutor-entry" @click="assignmentTutorOpen = true"><MessageCircleQuestion :size="19" :stroke-width="1.8" aria-hidden="true" /><span><strong>卡在某一步？</strong><small>向 AI 助教询问当前任务</small></span><span aria-hidden="true">›</span></button>
            </aside>
          </div>
        </section>
        <Transition name="modal">
          <div v-if="assignmentImagePreview" class="modal-backdrop assignment-image-backdrop" role="presentation" @click.self="assignmentImagePreview = null" @keydown.esc.window="assignmentImagePreview = null">
            <section class="slide-modal assignment-image-modal" role="dialog" aria-modal="true" :aria-label="assignmentImagePreview.alt">
              <header class="slide-modal-header"><strong>{{ assignmentImagePreview.alt }}</strong><button type="button" class="modal-close" aria-label="关闭图片预览" @click="assignmentImagePreview = null">×</button></header>
              <div class="slide-modal-body"><img class="slide-preview" :src="assignmentImagePreview.url" :alt="assignmentImagePreview.alt"></div>
            </section>
          </div>
        </Transition>
      </section>

      <section v-else-if="activeTab === 'progress'" class="progress-workspace">
        <div class="code-heading"><h1>回看每一步学习。</h1><p>根据对话与代码检查记录整理学习线索。没有评分标准时不生成成绩。</p></div>
        <div v-if="studentProgress" class="teacher-stats student-progress-stats"><div><strong>{{ studentProgress.totals.questions }}</strong><span>累计提问</span></div><div><strong>{{ studentProgress.totals.code_reviews }}</strong><span>代码分析</span></div><div><strong>{{ studentProgress.totals.submitted_tasks }}</strong><span>已提交任务</span></div><div><strong>{{ studentProgress.totals.learning_summaries }}</strong><span>学习回顾</span></div></div>
        <div v-if="studentProgress?.modules?.length" class="analytics-card student-progress-card"><h3>模块学习活动</h3><div v-for="row in studentProgress.modules" :key="row.name" class="analytics-row"><strong>{{ row.name }}</strong><span>{{ row.questions }} 次提问 · {{ row.code_reviews }} 次代码分析 · {{ row.submitted_tasks }} 项任务</span></div></div>
        <div v-if="studentProgress?.tasks?.length" class="analytics-card student-progress-card"><h3>最近提交的任务</h3><div v-for="row in studentProgress.tasks" :key="row.assignment_id" class="analytics-row"><strong>{{ row.title }}</strong><span>{{ row.module }} · 最新评分 {{ row.score }} · {{ new Date(row.submitted_at).toLocaleDateString('zh-CN') }}</span></div></div>
        <div v-if="studentProgress && !studentProgress.totals.questions && !studentProgress.totals.code_reviews && !studentProgress.totals.submitted_tasks" class="progress-empty" role="status"><strong>还没有学习记录</strong><p>从课程问答开始提一个问题，或提交一项实训任务，学习活动就会显示在这里。</p><button class="send-button" @click="newConversation">开始课程问答</button><button class="secondary-button" @click="openAssignments">查看实训任务</button></div>
        <button v-else class="send-button progress-action" :disabled="loading" @click="summarizeLearning">{{ loading ? '正在整理…' : '生成本段对话的学习回顾' }}</button>
        <p v-if="!learningSummaries.length && studentProgress && (studentProgress.totals.questions || studentProgress.totals.code_reviews || studentProgress.totals.submitted_tasks)" class="quiet progress-hint">还没有生成学习回顾。点击上方按钮，整理当前对话中的学习线索。</p>
        <article v-for="item in learningSummaries" :key="item.id" class="progress-card"><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small><div class="assistant-bubble" v-html="renderMarkdown(item.content)"></div></article>
      </section>

      <section v-else-if="activeTab === 'profile'" class="profile-workspace">
        <div class="code-heading"><h1>让学习记录归到你名下。</h1><p>登记后，新产生的提问、代码分析、任务提交和学习回顾会按班级汇总到教师工作台。已有匿名记录仍单独保留。</p></div>
        <form class="profile-form" @submit.prevent="saveStudentProfile" @input="profileSaveMessage = ''">
          <label>姓名 <input v-model="studentProfile.name" maxlength="80" required placeholder="请输入姓名"></label>
          <label>学号 <input v-model="studentProfile.student_number" maxlength="40" placeholder="选填"></label>
          <label>班级 <input v-model="studentProfile.class_name" maxlength="80" required placeholder="例如：物联网 2023 级 1 班"></label>
          <button class="send-button" :disabled="profileSaving">{{ profileSaving ? '保存中…' : studentProfile.registered ? '更新信息' : '保存信息' }}</button>
          <p v-if="profileSaveMessage" class="profile-save-feedback" role="status" aria-live="polite">{{ profileSaveMessage }}</p>
          <p v-if="studentProfile.registered" class="profile-saved">已登记：{{ studentProfile.name }} · {{ studentProfile.class_name }}</p>
        </form>
      </section>

      <section v-else ref="teacherWorkspaceRef" class="teacher-workspace">
        <div class="code-heading"><h1>看清每一次学习与提交。</h1><p>按班级、模块和日期查看学习过程与任务提交，管理资料并审核助教回答。</p></div>
        <form v-if="!teacherCode" class="teacher-access" @submit.prevent="unlockTeacher"><h2>教师身份验证</h2><p>请输入本机 .env 中的 TEACHER_ACCESS_CODE 访问码。</p><input v-model="teacherCodeInput" type="password" autocomplete="off" placeholder="教师访问码" required><button class="send-button">进入工作台</button></form>
        <template v-else>
        <nav class="teacher-subnav" aria-label="教师工作台页面">
          <button type="button" :class="{ active: teacherSection === 'assignments' }" :aria-current="teacherSection === 'assignments' ? 'page' : undefined" @click="openTeacherAssignments">作业管理 <span v-if="teacherAssignments.tasks.some(task => task.pending)">{{ teacherAssignments.tasks.reduce((count, task) => count + task.pending, 0) }}</span></button>
          <button type="button" :class="{ active: teacherSection === 'analytics' }" :aria-current="teacherSection === 'analytics' ? 'page' : undefined" @click="teacherSection = 'analytics'">学情分析</button>
          <button type="button" :class="{ active: teacherSection === 'materials' }" :aria-current="teacherSection === 'materials' ? 'page' : undefined" @click="teacherSection = 'materials'">课程资料</button>
          <button type="button" :class="{ active: teacherSection === 'reviews' }" :aria-current="teacherSection === 'reviews' ? 'page' : undefined" @click="teacherSection = 'reviews'">回答审核 <span v-if="teacherData?.totals?.pending_reviews">{{ teacherData.totals.pending_reviews }}</span></button>
          <button type="button" class="teacher-logout" @click="lockTeacher">退出教师视图</button>
        </nav>
        <div class="teacher-panels">
        <div v-show="teacherSection === 'assignments'" class="teacher-panel teacher-assignment-panel">
          <div class="teacher-section-heading"><h2>作业管理</h2><span>全部 {{ teacherAssignments.tasks.length }} 项任务 · {{ teacherAssignments.submissions.length }} 次提交</span></div>
          <div class="teacher-assignment-filters"><label>模块<CustomSelect v-model="teacherAssignmentModule" :options="[{ value: '', label: '全部模块' }, ...modules.slice(1).map(name => ({ value: name, label: name }))]" aria-label="任务模块" /></label><label>查找任务<input v-model="teacherAssignmentQuery" type="search" placeholder="任务名称或编号"></label></div>
          <div class="teacher-assignment-grid">
            <div class="teacher-task-list" aria-label="任务列表">
              <button v-for="task in visibleTeacherTasks" :key="task.id" type="button" :class="{ active: teacherSelectedTaskId === task.id }" @click="selectTeacherTask(task)"><strong>{{ task.title }}</strong><small>{{ task.module }} · v{{ task.version }} · {{ task.students }} 人 · {{ task.submissions }} 次提交 · 待复核 {{ task.pending }}</small></button>
              <p v-if="!visibleTeacherTasks.length" class="teacher-assignment-empty">没有匹配的任务。</p>
            </div>
            <section class="teacher-task-detail">
              <p v-if="teacherTaskLoading && !teacherTaskDetail" class="teacher-assignment-empty">正在读取任务要求…</p>
              <template v-else-if="teacherTaskDetail?.task?.id === teacherSelectedTaskId">
                <div class="teacher-task-detail-heading"><div><small>{{ teacherTaskDetail.task.module }} · 当前版本 v{{ teacherTaskDetail.task.version }}</small><h3>{{ teacherTaskDetail.task.title }}</h3></div><button type="button" class="secondary-button" @click="teacherTaskEditing = !teacherTaskEditing">{{ teacherTaskEditing ? '取消编辑' : '编辑任务' }}</button></div>
                <form v-if="teacherTaskEditing" class="teacher-task-edit" @submit.prevent="saveTeacherTask"><label>任务名称<input v-model="teacherTaskDraft.title" maxlength="255" required></label><label>任务要求<textarea v-model="teacherTaskDraft.description" rows="11" maxlength="100000" required></textarea></label><label>评分标准<textarea v-model="teacherTaskDraft.scoring_rubric" rows="7" maxlength="30000" required></textarea></label><button class="send-button" :disabled="teacherTaskLoading">{{ teacherTaskLoading ? '保存中…' : '保存为新版本' }}</button></form>
                <template v-else><h4>任务要求</h4><div class="assignment-manual-text" v-html="renderAssignmentText(teacherTaskDetail.task.description, teacherTaskDetail.task.module)"></div><h4>评分标准</h4><div class="assignment-manual-text" v-html="renderAssignmentText(teacherTaskDetail.task.scoring_rubric, teacherTaskDetail.task.module)"></div></template>
                <details v-if="teacherTaskDetail.versions.length" class="teacher-task-versions"><summary>版本记录（{{ teacherTaskDetail.versions.length }}）</summary><div v-for="version in teacherTaskDetail.versions" :key="version.version"><strong>v{{ version.version }} · {{ version.title }}</strong><small>{{ new Date(version.created_at).toLocaleString('zh-CN') }}</small><details><summary>查看该版本要求与评分标准</summary><pre>{{ version.description }}</pre><pre>{{ version.scoring_rubric }}</pre></details></div></details>
              </template>
              <p v-else class="teacher-assignment-empty">选择左侧任务，查看要求、评分标准和版本记录。</p>
            </section>
          </div>
          <div class="teacher-section-heading teacher-submission-heading"><h2>学生提交</h2><div class="teacher-submission-actions"><button v-if="selectedTeacherSubmission" type="button" class="record-action danger" @click="deleteTeacherSubmission">删除所选提交</button><button v-if="teacherSelectedTaskId" type="button" class="text-button" @click="teacherSelectedTaskId = ''; teacherTaskDetail = null; selectedTeacherSubmission = null">查看全部任务提交</button></div></div>
          <div class="teacher-submission-filters"><label>班级<CustomSelect v-model="teacherSubmissionClass" :options="[{ value: '', label: '全部班级' }, ...teacherAssignments.classes.map(name => ({ value: name, label: name }))]" aria-label="提交班级" /></label><label>学生<input v-model="teacherSubmissionStudent" type="search" placeholder="姓名或学号"></label><label>复核状态<CustomSelect v-model="teacherSubmissionStatus" :options="[{ value: '', label: '全部状态' }, { value: 'pending', label: '待复核' }, { value: 'approved', label: '已确认' }, { value: 'needs_revision', label: '需修订' }]" aria-label="提交复核状态" /></label><label>开始日期<input v-model="teacherSubmissionFrom" type="date"></label><label>结束日期<input v-model="teacherSubmissionTo" type="date"></label></div>
          <div v-if="visibleTeacherSubmissions.length" class="teacher-submission-list"><button v-for="item in visibleTeacherSubmissions" :key="item.id" type="button" :class="{ active: selectedTeacherSubmission?.id === item.id }" @click="selectTeacherSubmission(item)"><span><strong>{{ item.student_name }} · {{ item.class_name }}</strong><small>{{ item.assignment_title }} · {{ new Date(item.created_at).toLocaleString('zh-CN') }}</small></span><span><strong>AI {{ item.total_score }}<template v-if="item.teacher_final_score !== null"> · 最终 {{ item.teacher_final_score }}</template></strong><small>v{{ item.assignment_version }} · {{ item.is_latest ? '最新提交' : '历史提交' }} · {{ item.teacher_review_status === 'approved' ? '已确认' : item.teacher_review_status === 'needs_revision' ? '需修订' : '待复核' }}</small></span></button></div>
          <p v-else class="teacher-assignment-empty">暂无学生提交。任务列表和筛选仍可使用；学生提交后会显示在这里。</p>
          <section v-if="selectedTeacherSubmission" class="teacher-submission-review"><div class="teacher-section-heading"><h2>提交详情 · {{ selectedTeacherSubmission.student_name }} · {{ selectedTeacherSubmission.assignment_title }}</h2><button class="text-button" @click="selectedTeacherSubmission = null">关闭</button></div><p>提交时间：{{ new Date(selectedTeacherSubmission.created_at).toLocaleString('zh-CN') }} · 任务版本 v{{ selectedTeacherSubmission.assignment_version }}<span v-if="selectedTeacherSubmission.revised_from_id"> · 修订自第 {{ selectedTeacherSubmission.revised_from_id }} 次提交</span></p><div class="teacher-submission-downloads"><button type="button" class="secondary-button" @click="downloadTeacherSubmissionBundle(selectedTeacherSubmission.id, 'work')">下载作品</button><button type="button" class="secondary-button" @click="downloadTeacherSubmissionBundle(selectedTeacherSubmission.id, 'report')">下载报告</button><button type="button" class="secondary-button" @click="downloadTeacherSubmissionBundle(selectedTeacherSubmission.id)">打包下载本次提交</button></div><details open><summary>作品文字与代码</summary><pre>{{ selectedTeacherSubmission.work_text || '作品文字为空，请下载附件。' }}</pre></details><details open><summary>实验报告文字</summary><pre>{{ selectedTeacherSubmission.report_text || '报告文字为空，请下载附件。' }}</pre></details><div v-if="selectedTeacherSubmission.attachments.length" class="teacher-submission-files"><button v-for="attachment in selectedTeacherSubmission.attachments" :key="attachment.index" class="attach-button" @click="downloadSubmissionFile(selectedTeacherSubmission.id, attachment)">下载{{ attachment.group === 'work' ? '作品' : '报告' }}：{{ attachment.filename }}</button></div><details open><summary>AI 评分明细 · {{ selectedTeacherSubmission.evaluation.total_score }} 分</summary><div v-for="(item, index) in selectedTeacherSubmission.evaluation.acceptance_items || []" :key="index" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.feedback }}</p></div><div v-for="(item, index) in selectedTeacherSubmission.evaluation.report_items || []" :key="`report-${index}`" class="grade-item"><strong>{{ item.criterion }} · {{ item.score }}/{{ item.max_score }}</strong><p>{{ item.feedback }}</p></div></details><form class="teacher-review-form" @submit.prevent="saveSubmissionReview"><label>复核状态<CustomSelect v-model="submissionReviewStatus" :options="[{ value: 'pending', label: '待复核' }, { value: 'approved', label: '确认' }, { value: 'needs_revision', label: '建议修订' }]" aria-label="复核状态" /></label><label>最终分数（选填）<input v-model="submissionFinalScore" type="number" min="0" max="100" step="0.1" :disabled="submissionReviewStatus !== 'approved'" placeholder="留空则显示 AI 初评分"></label><label>教师意见<textarea v-model="submissionReviewNote" rows="3" maxlength="2000" placeholder="写明确认依据或需要补充的材料"></textarea></label><button class="send-button" :disabled="loading">{{ loading ? '保存中…' : '保存复核' }}</button></form><details v-if="selectedTeacherSubmission.review_history?.length"><summary>复核历史（{{ selectedTeacherSubmission.review_history.length }}）</summary><p v-for="(event, index) in selectedTeacherSubmission.review_history" :key="index">{{ new Date(event.created_at).toLocaleString('zh-CN') }} · {{ event.status }} · {{ event.final_score ?? '未设最终分数' }} · {{ event.note || '无意见' }}</p></details></section>
          <details v-if="selectedTeacherSubmission?.assignment_snapshot?.description" class="teacher-submission-review teacher-submission-snapshot"><summary>本次提交所用任务要求与评分标准（v{{ selectedTeacherSubmission.assignment_version }}）</summary><h4>任务要求</h4><pre>{{ selectedTeacherSubmission.assignment_snapshot.description }}</pre><h4>评分标准</h4><pre>{{ selectedTeacherSubmission.assignment_snapshot.scoring_rubric }}</pre></details>
        </div>
        <Transition name="panel">
        <div v-show="teacherSection === 'analytics'" class="teacher-panel">
        <div class="teacher-section-heading"><h2>学习过程分析</h2></div>
        <div class="analytics-filters">
          <label>班级<CustomSelect v-model="teacherFilter.class_name" :options="[{ value: '', label: '全部班级' }, ...(teacherAnalytics?.filters?.classes || []).map(name => ({ value: name, label: name })), { value: '未登记', label: '未登记' }]" aria-label="班级" @change="loadTeacherAnalytics" /></label>
          <label>模块<CustomSelect v-model="teacherFilter.module" :options="[{ value: '', label: '全部模块' }, ...(teacherAnalytics?.filters?.modules || []).map(name => ({ value: name, label: name }))]" aria-label="模块" @change="loadTeacherAnalytics" /></label>
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
          <div class="analytics-card teacher-recent-submissions"><h3>最近任务提交</h3><p>{{ teacherAnalytics?.recent_submissions?.length ? `最近有 ${teacherAnalytics.recent_submissions.length} 条提交记录。` : '目前暂无学生提交。' }}</p><button type="button" class="secondary-button" @click="openTeacherAssignments">进入作业管理</button></div>
        </div>
        </Transition>
        <Transition name="panel">
        <div v-show="teacherSection === 'materials'" class="teacher-panel">
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
        <div class="teacher-upload"><input ref="teacherMaterialInput" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" hidden @change="selectTeacherMaterial"><button class="attach-button" @click="teacherMaterialInput?.click()">＋ 选择 PDF / Word</button><span>{{ teacherMaterialFile?.name || '尚未选择文件' }}</span><CustomSelect v-model="teacherMaterialModule" :options="modules.slice(1)" aria-label="课程模块" /><label class="teacher-ocr-option"><input v-model="teacherMaterialOcr" type="checkbox" :disabled="!teacherMaterialFile || !/\.pdf$/i.test(teacherMaterialFile.name)">识别扫描 PDF 图片页</label><button class="secondary-button" :disabled="!teacherMaterialFile || materialUploading" @click="uploadTeacherMaterial">{{ materialUploading ? '建立索引中…' : '上传并建立索引' }}</button></div><p v-if="teacherImportMessage" class="teacher-import-message">{{ teacherImportMessage }}</p>
        <div class="teacher-modules"><span v-for="(item, name) in teacherData?.modules || {}" :key="name">{{ name }}：{{ item.documents }} 份 · {{ item.slides }} 个内容单元</span></div>
        <details class="teacher-materials"><summary>查看全部课件（{{ teacherData?.materials?.length || 0 }}）</summary><div v-for="item in teacherData?.materials || []" :key="item.id"><span>{{ item.filename }}</span><small>{{ item.module }} · {{ item.slide_count }} {{ item.unit_label || '页' }} · 版本 {{ item.version }} · {{ new Date(item.created_at).toLocaleDateString('zh-CN') }}</small><a :href="`/api/materials/${item.id}/download`">下载</a><button v-if="item.source_type !== 'pptx'" @click="deleteTeacherMaterial(item)">删除</button></div></details>
        <details v-if="teacherData?.material_revisions?.length" class="teacher-materials"><summary>资料更新记录（{{ teacherData.material_revisions.length }}）</summary><div v-for="item in teacherData.material_revisions" :key="item.id"><span>{{ item.filename }}</span><small>{{ item.module }} · {{ item.old_version }} → {{ item.new_version }} · {{ new Date(item.replaced_at).toLocaleString('zh-CN') }}</small></div></details>
        </div>
        </Transition>
        <Transition name="panel">
        <div v-show="teacherSection === 'reviews'" class="teacher-panel">
        <div class="teacher-section-heading"><h2>回答审核</h2><span>全局最近 40 条</span></div>
        <div class="teacher-review-grid"><div class="teacher-question-list"><button v-for="item in teacherData?.questions || []" :key="item.id" :class="{ selected: selectedTeacherQuestion?.id === item.id }" @click="selectTeacherQuestion(item)"><span>{{ item.question }}</span><small>{{ item.module || '未指定模块' }} · {{ item.review_status === 'approved' ? '已确认' : item.review_status === 'needs_revision' ? '需修改' : '待审核' }}</small></button><p v-if="!teacherData?.questions?.length" class="quiet">还没有问答记录。</p></div><article v-if="selectedTeacherQuestion" class="teacher-answer"><h3>{{ selectedTeacherQuestion.question }}</h3><div class="assistant-bubble" v-html="renderMarkdown(selectedTeacherQuestion.answer)"></div><details v-if="selectedTeacherQuestion.evidence?.length"><summary>课件来源（{{ selectedTeacherQuestion.evidence.length }}）</summary><p v-for="item in selectedTeacherQuestion.evidence" :key="item.chunk_id">{{ item.filename }} · 第 {{ item.slide_number }} {{ item.unit_label || '页' }}</p></details><label>审核状态<CustomSelect v-model="reviewStatus" :options="[{ value: 'pending', label: '待审核' }, { value: 'approved', label: '已确认' }, { value: 'needs_revision', label: '需修改' }]" aria-label="审核状态" /></label><label>审核备注<textarea v-model="reviewNote" rows="3" maxlength="2000" placeholder="记录需要核对或修改的地方…"></textarea></label><button class="send-button" :disabled="loading" @click="saveTeacherReview">{{ loading ? '保存中…' : '保存审核' }}</button></article><p v-else class="quiet">选择一条回答查看并审核。</p></div>
        </div>
        </Transition>
        </div>
        </template>
      </section>
      </Transition>
    </main>
  </div>
</template>
