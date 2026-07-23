import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

// 简历解析
export function uploadResume(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/resume/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// JD 分析
export function analyzeJD(jdText, resumeData) {
  return api.post('/jd/analyze', { jd_text: jdText, resume_data: resumeData })
}

// 获取JD模板
export function getJDTemplates() {
  return api.get('/jd/templates')
}

// 开始面试（SSE流式）
export function startInterviewSSE(resumeData, jdText) {
  return fetch('/interview/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_data: resumeData, jd_text: jdText, round_num: 1, history: [] }),
  })
}

// 面试对话（SSE流式）
export function interviewChatSSE(payload) {
  return fetch('/interview/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// 获取面试报告
export function getInterviewReport(payload) {
  return api.post('/interview/report', payload)
}

export default api
