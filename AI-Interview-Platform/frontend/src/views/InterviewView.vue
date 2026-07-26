<template>
  <div class="interview-page">
    <h2 class="page-title">AI 模拟面试</h2>

    <!-- 进度条 -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: (currentRound / 5) * 100 + '%' }"></div>
      <span class="progress-text">{{ currentRound }} / 5</span>
    </div>

    <!-- 聊天区域 -->
    <div class="chat-area" ref="chatArea">
      <div v-for="(msg, i) in messages" :key="i" class="msg" :class="msg.role">
        <div class="msg-bubble">{{ msg.content }}</div>
        <div class="msg-eval" v-if="msg.eval">
          <span class="eval-score">等级：{{ msg.eval.grade }}</span>
          <span class="eval-feedback">{{ msg.eval.feedback }}</span>
        </div>
        <button
          v-if="msg.role === 'user' && i === lastUserIndex && !streaming"
          class="re-edit-btn"
          @click="reEdit(i)"
        >重新编辑</button>
      </div>
      <div v-if="streaming" class="msg assistant">
        <div class="msg-bubble typing">{{ streamingText }}<span class="cursor">|</span></div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area" v-if="!finished">
      <textarea
        v-model="userInput"
        placeholder="输入你的回答..."
        rows="3"
        @keydown.ctrl.enter="sendAnswer"
        :disabled="streaming || waitingFirst"
      ></textarea>
      <button class="btn btn-primary" @click="sendAnswer" :disabled="streaming || !userInput.trim() || waitingFirst">
        发送 (Ctrl+Enter)
      </button>
    </div>

    <!-- 面试结束 -->
    <div class="card" v-if="finished">
      <p style="text-align: center; color: #00d2a0; font-size: 16px;">🎉 面试完成！</p>
      <button class="btn btn-primary" style="width: 100%; margin-top: 12px;" @click="viewReport">
        查看评分报告 →
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { startInterviewSSE, interviewChatSSE } from '../api'

const router = useRouter()
const messages = ref([])
const userInput = ref('')
const streaming = ref(false)
const streamingText = ref('')
const currentRound = ref(1)
const finished = ref(false)
const waitingFirst = ref(true)
const chatArea = ref(null)
const history = ref([])

const lastUserIndex = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') return i
  }
  return -1
})

let resumeData = null
let jdText = ''
const evaluatedRounds = []  // 收集每轮评估结果，report时直接传给后端

onMounted(async () => {
  resumeData = JSON.parse(sessionStorage.getItem('resumeData') || 'null')
  jdText = sessionStorage.getItem('jdText') || ''

  if (!resumeData) {
    router.push('/upload')
    return
  }

  // 开始面试，获取第一个问题
  streaming.value = true
  try {
    const response = await startInterviewSSE(resumeData, jdText)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let question = ''
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()  // 最后一行可能不完整，留到下次
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error) {
              messages.value.push({ role: 'assistant', content: '⚠️ ' + data.error })
              streaming.value = false
              waitingFirst.value = false
              return
            }
            if (data.token) {
              question += data.token
              streamingText.value = question
            }
          } catch (_) { /* 忽略不完整JSON */ }
        }
      }
    }

    messages.value.push({ role: 'assistant', content: question })
    history.value.push({ role: 'assistant', content: question })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '面试启动失败，请检查后端服务是否运行。' })
  } finally {
    streaming.value = false
    streamingText.value = ''
    waitingFirst.value = false
    scrollToBottom()
  }
})

async function sendAnswer() {
  if (!userInput.value.trim() || streaming.value) return

  const answer = userInput.value.trim()
  userInput.value = ''
  messages.value.push({ role: 'user', content: answer })
  history.value.push({ role: 'user', content: answer })
  scrollToBottom()

  streaming.value = true
  streamingText.value = ''

  try {
    const response = await interviewChatSSE({
      resume_data: resumeData,
      jd_text: jdText,
      round_num: currentRound.value,
      history: history.value,
      user_answer: answer,
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let question = ''
    let evalData = null
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'eval') {
              evalData = data.data
              const lastUserMsg = [...messages.value].reverse().find(m => m.role === 'user')
              if (lastUserMsg) lastUserMsg.eval = evalData
              // 收集该轮评估结果，report时复用
              const lastQuestion = [...history.value].reverse().find(m => m.role === 'assistant')
              evaluatedRounds.push({
                round_num: currentRound.value,
                question: lastQuestion?.content || '',
                answer: answer,
                grade: evalData.grade || 'C',
                feedback: evalData.feedback || '',
              })
            } else if (data.type === 'token') {
              question += data.token
              streamingText.value = question
            } else if (data.type === 'end') {
              finished.value = true
            } else if (data.error) {
              messages.value.push({ role: 'assistant', content: '⚠️ ' + data.error })
            }
          } catch (_) { /* 忽略不完整JSON */ }
        }
      }
    }

    if (question) {
      messages.value.push({ role: 'assistant', content: question })
      history.value.push({ role: 'assistant', content: question })
      currentRound.value++
    }
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '连接中断，请重试。' })
  } finally {
    streaming.value = false
    streamingText.value = ''
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatArea.value) chatArea.value.scrollTop = chatArea.value.scrollHeight
  })
}

function reEdit(index) {
  // 取回用户输入
  userInput.value = messages.value[index].content
  // 截断该条及之后的所有消息
  messages.value = messages.value.slice(0, index)
  // history 同步截断（history与messages一一对应）
  history.value = history.value.slice(0, index)
  // 移除对应的评估记录
  if (evaluatedRounds.length) evaluatedRounds.pop()
  // 回退轮次
  if (currentRound.value > 1) currentRound.value--
  finished.value = false
  scrollToBottom()
}

function viewReport() {
  sessionStorage.setItem('interviewHistory', JSON.stringify(history.value))
  sessionStorage.setItem('interviewJd', jdText)
  sessionStorage.setItem('interviewRounds', JSON.stringify(evaluatedRounds))
  router.push('/report')
}
</script>

<style scoped>
.page-title { font-size: 22px; font-weight: 700; margin-bottom: 16px; }

.progress-bar {
  position: relative;
  height: 6px;
  background: #2a2a38;
  border-radius: 3px;
  margin-bottom: 20px;
}
.progress-fill {
  height: 100%;
  background: #6c5ce7;
  border-radius: 3px;
  transition: width 0.3s;
}
.progress-text {
  position: absolute;
  right: 0;
  top: -22px;
  font-size: 12px;
  color: #9898b0;
}

.chat-area {
  height: 420px;
  overflow-y: auto;
  padding: 16px;
  background: #18181f;
  border: 1px solid #2a2a38;
  border-radius: 14px;
  margin-bottom: 16px;
}

.msg { margin-bottom: 16px; }
.msg.assistant .msg-bubble {
  background: rgba(108, 92, 231, 0.1);
  border: 1px solid rgba(108, 92, 231, 0.2);
  border-radius: 14px 14px 14px 4px;
  padding: 12px 16px;
  max-width: 85%;
  font-size: 14px;
  line-height: 1.6;
}
.msg.user {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}
.msg.user .msg-bubble {
  background: #6c5ce7;
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  padding: 12px 16px;
  max-width: 85%;
  font-size: 14px;
  line-height: 1.6;
}

.msg-eval {
  margin-top: 6px;
  font-size: 12px;
  color: #9898b0;
  text-align: right;
}
.eval-score { color: #f0a040; margin-right: 8px; }

.cursor { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0; } }

.input-area {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}
.input-area textarea { flex: 1; }
.input-area .btn { height: fit-content; white-space: nowrap; }

.re-edit-btn {
  margin-top: 4px;
  font-size: 11px;
  color: #9898b0;
  background: none;
  border: 1px solid #3a3a4e;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.re-edit-btn:hover { color: #6c5ce7; border-color: #6c5ce7; }
</style>
