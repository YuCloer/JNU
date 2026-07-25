<template>
  <div class="report-page">
    <h2 class="page-title">面试评分报告</h2>

    <div class="loading" v-if="loading">正在生成报告</div>

    <template v-if="report && !loading">
      <!-- 综合评分 -->
      <div class="card score-card">
        <div class="score-circle">
          <span class="score-num" :class="gradeClass(report.total_grade)">{{ report.total_grade }}</span>
          <span class="score-max">{{ gradeLabel(report.total_grade) }}</span>
        </div>
        <p class="score-summary">{{ report.summary }}</p>
      </div>

      <!-- 优势 -->
      <div class="card" v-if="report.strengths && report.strengths.length">
        <div class="card-title">✅ 优势亮点</div>
        <ul class="list">
          <li v-for="(s, i) in report.strengths" :key="i">{{ s }}</li>
        </ul>
      </div>

      <!-- 改进建议 -->
      <div class="card" v-if="report.improvements && report.improvements.length">
        <div class="card-title">💡 改进建议</div>
        <ul class="list">
          <li v-for="(s, i) in report.improvements" :key="i">{{ s }}</li>
        </ul>
      </div>

      <!-- 逐题点评 -->
      <div class="card" v-if="rounds.length">
        <div class="card-title">逐题点评</div>
        <div v-for="(r, i) in rounds" :key="i" class="round-item">
          <div class="round-header" @click="r.expanded = !r.expanded">
            <span class="round-num">第 {{ i + 1 }} 题</span>
            <span class="round-score" :class="gradeClass(r.grade)">{{ r.grade }}</span>
            <span class="expand-icon">{{ r.expanded ? '▼' : '▶' }}</span>
          </div>
          <div class="round-detail" v-if="r.expanded">
            <p class="round-q"><strong>问：</strong>{{ r.question }}</p>
            <p class="round-a"><strong>答：</strong>{{ r.answer }}</p>
            <p class="round-fb"><strong>点评：</strong>{{ r.feedback }}</p>
          </div>
        </div>
      </div>

      <!-- 操作 -->
      <div class="actions">
        <button class="btn btn-primary" @click="retry">再来一次</button>
        <button class="btn btn-secondary" @click="$router.push('/upload')">返回首页</button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getInterviewReport } from '../api'

const router = useRouter()
const loading = ref(true)
const report = ref(null)
const rounds = ref([])

onMounted(async () => {
  const history = JSON.parse(sessionStorage.getItem('interviewHistory') || '[]')
  const jdText = sessionStorage.getItem('interviewJd') || ''
  const resumeData = JSON.parse(sessionStorage.getItem('resumeData') || 'null')

  if (!history.length) {
    loading.value = false
    router.push('/interview')
    return
  }

  try {
    const res = await getInterviewReport({
      resume_data: resumeData || {},
      jd_text: jdText,
      round_num: 5,
      history: history,
      user_answer: '',
    })
    report.value = res.data.report
    rounds.value = (res.data.rounds || []).map(r => ({ ...r, expanded: false }))
  } catch (e) {
    alert('报告生成失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
})

function gradeClass(grade) {
  if ('SAB'.includes(grade)) return 'high'
  if (grade === 'C') return 'mid'
  return 'low'
}

function gradeLabel(grade) {
  const labels = { S: '完美', A: '优秀', B: '良好', C: '合格', D: '偏弱', E: '较差', F: '不合格' }
  return labels[grade] || ''
}

function retry() {
  sessionStorage.removeItem('interviewHistory')
  router.push('/interview')
}
</script>

<style scoped>
.page-title { font-size: 22px; font-weight: 700; margin-bottom: 24px; }

.score-card { text-align: center; padding: 32px; }
.score-circle { margin-bottom: 12px; }
.score-num { font-size: 56px; font-weight: 700; color: #6c5ce7; }
.score-max { font-size: 20px; color: #9898b0; }
.score-summary { font-size: 14px; color: #9898b0; max-width: 500px; margin: 0 auto; }

.list { padding-left: 20px; }
.list li { font-size: 14px; color: #e4e4ec; margin-bottom: 8px; line-height: 1.5; }

.round-item { border-bottom: 1px solid #2a2a38; }
.round-item:last-child { border-bottom: none; }
.round-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  cursor: pointer;
}
.round-num { font-size: 14px; font-weight: 500; }
.round-score { font-size: 13px; font-weight: 600; }
.round-score.high { color: #00d2a0; }
.round-score.mid { color: #f0a040; }
.round-score.low { color: #ff5e5e; }
.expand-icon { margin-left: auto; font-size: 11px; color: #9898b0; }

.round-detail { padding: 0 0 12px; font-size: 13px; color: #9898b0; line-height: 1.7; }
.round-detail p { margin-bottom: 6px; }
.round-q strong, .round-a strong, .round-fb strong { color: #e4e4ec; }

.actions { display: flex; gap: 12px; margin-top: 24px; }
</style>
