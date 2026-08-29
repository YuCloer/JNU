import axios from 'axios'

const api = axios.create({
  baseURL: '',
  timeout: 60000,
})

async function fetchSSE(url, payload) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (response.ok) return response

  let detail = `请求失败（${response.status}）`
  try {
    detail = (await response.json()).detail || detail
  } catch (_) { /* 使用默认错误信息 */ }
  throw new Error(detail)
}

// 全局响应拦截：Ollama 不可达友好提示
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const detail = err.response?.data?.detail || ''
    if (err.response?.status === 500 && /ollama|模型/i.test(detail)) {
      alert('模型服务不可达，请确认 Ollama 已启动')
    }
    return Promise.reject(err)
  }
)

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
  return fetchSSE('/interview/start', { resume_data: resumeData, jd_text: jdText, round_num: 1, history: [] })
}

// 面试对话（SSE流式）
export function interviewChatSSE(payload) {
  return fetchSSE('/interview/chat', payload)
}

// 获取面试报告
export function getInterviewReport(payload) {
  return api.post('/interview/report', payload)
}

export default api
