<template>
  <div class="report-page">
    <h2 class="page-title">面试评分报告</h2>

    <div class="loading" v-if="loading">正在生成报告</div>

    <!-- 空态：无面试记录 -->
    <div class="card" v-if="!loading && !report && rounds.length === 0" style="text-align: center; padding: 48px;">
      <p style="color: #9898b0; font-size: 15px; margin-bottom: 16px;">暂无面试记录</p>
      <button class="btn btn-primary" @click="$router.push('/interview')">去面试 →</button>
    </div>

    <template v-if="report && !loading">
      <!-- 综合评分 -->
      <div class="card score-card">
        <div class="score-circle">
          <span class="score-num" :class="gradeClass(report.total_grade)">{{ report.total_grade }}</span>
          <span class="score-max">{{ gradeLabel(report.total_grade) }}</span>
        </div>
        <p class="score-summary">{{ report.summary }}</p>
      </div>

      <!-- 五维雷达图 -->
      <div class="card" v-if="radarData.length">
        <div class="card-title">能力维度分析</div>
        <div class="radar-wrap">
          <svg viewBox="0 0 300 280" class="radar-svg">
            <!-- 背景网格（3层五边形） -->
            <polygon v-for="level in [1, 0.66, 0.33]" :key="'g'+level"
              :points="gridPoints(level)" fill="none" stroke="#2a2a3e" stroke-width="1"/>
            <!-- 轴线 -->
            <line v-for="(d, i) in radarData" :key="'ax'+i"
              x1="150" y1="140" :x2="axisEnd(i).x" :y2="axisEnd(i).y" stroke="#2a2a3e" stroke-width="1"/>
            <!-- 数据多边形 -->
            <polygon :points="dataPoints" fill="rgba(108,92,231,0.25)" stroke="#6c5ce7" stroke-width="2"/>
            <!-- 数据点 -->
            <circle v-for="(d, i) in radarData" :key="'pt'+i"
              :cx="dataPoint(i).x" :cy="dataPoint(i).y" r="4" fill="#6c5ce7"/>
            <!-- 标签 -->
            <text v-for="(d, i) in radarData" :key="'lb'+i"
              :x="labelPos(i).x" :y="labelPos(i).y"
              text-anchor="middle" font-size="12" fill="#e4e4ec">{{ d.label }}</text>
            <text v-for="(d, i) in radarData" :key="'sc'+i"
              :x="labelPos(i).x" :y="labelPos(i).y + 14"
              text-anchor="middle" font-size="10" fill="#9898b0">{{ d.score }}分</text>
          </svg>
        </div>
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
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getInterviewReport } from '../api'

const router = useRouter()
const loading = ref(true)
const report = ref(null)
const rounds = ref([])

const GRADE_SCORE = { S: 100, A: 85, B: 70, C: 55, D: 40, E: 25, F: 10 }
const DIM_LABELS = ['项目经验', '技术深度', '应变能力', '表达逻辑', '软性素质']

const radarData = computed(() => {
  if (!rounds.value.length) return []
  return rounds.value.slice(0, 5).map((r, i) => ({
    label: DIM_LABELS[i] || `第${i + 1}题`,
    score: GRADE_SCORE[r.grade] ?? 55,
  }))
})

// SVG 雷达图几何计算（中心150,140 半径100）
const CX = 150, CY = 140, R = 100

function angleFor(i) {
  return (Math.PI * 2 * i) / 5 - Math.PI / 2
}

function gridPoints(level) {
  return Array.from({ length: 5 }, (_, i) => {
    const a = angleFor(i)
    return `${CX + R * level * Math.cos(a)},${CY + R * level * Math.sin(a)}`
  }).join(' ')
}

function axisEnd(i) {
  const a = angleFor(i)
  return { x: CX + R * Math.cos(a), y: CY + R * Math.sin(a) }
}

function dataPoint(i) {
  const a = angleFor(i)
  const ratio = (radarData.value[i]?.score ?? 50) / 100
  return { x: CX + R * ratio * Math.cos(a), y: CY + R * ratio * Math.sin(a) }
}

const dataPoints = computed(() =>
  radarData.value.map((_, i) => {
    const p = dataPoint(i)
    return `${p.x},${p.y}`
  }).join(' ')
)

function labelPos(i) {
  const a = angleFor(i)
  return { x: CX + (R + 24) * Math.cos(a), y: CY + (R + 24) * Math.sin(a) }
}

onMounted(async () => {
  const history = JSON.parse(sessionStorage.getItem('interviewHistory') || '[]')
  const jdText = sessionStorage.getItem('interviewJd') || ''
  const resumeData = JSON.parse(sessionStorage.getItem('resumeData') || 'null')
  const preRounds = JSON.parse(sessionStorage.getItem('interviewRounds') || '[]')

  if (!history.length) {
    loading.value = false
    return
  }

  try {
    const res = await getInterviewReport({
      resume_data: resumeData || {},
      jd_text: jdText,
      round_num: 5,
      history: history,
      user_answer: '',
      rounds: preRounds,
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

.radar-wrap { display: flex; justify-content: center; padding: 8px 0; }
.radar-svg { width: 300px; max-width: 100%; }

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
