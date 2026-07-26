<template>
  <div class="match-page">
    <h2 class="page-title">JD 匹配分析</h2>
    <p class="page-desc">粘贴岗位描述或选择预设模板，分析与简历的岗位匹配度（学历+技能+经验）</p>

    <div class="card" v-if="!resumeData">
      <p style="color: #f0a040;">⚠️ 请先上传简历</p>
      <button class="btn btn-secondary" @click="$router.push('/upload')">去上传简历</button>
    </div>

    <template v-else>
      <!-- JD 输入 -->
      <div class="card">
        <div class="card-title">岗位描述</div>
        <div class="template-btns">
          <button class="btn btn-secondary" @click="useTemplate('sde')">后端开发</button>
          <button class="btn btn-secondary" @click="useTemplate('pm')">产品经理</button>
          <button class="btn btn-secondary" @click="useTemplate('data')">数据分析</button>
        </div>
        <textarea v-model="jdText" placeholder="粘贴岗位描述（JD）..." rows="8"></textarea>
        <button class="btn btn-primary" style="margin-top: 12px;" @click="analyze" :disabled="analyzing || !jdText.trim()">
          {{ analyzing ? '分析中...' : '开始分析' }}
        </button>
      </div>

      <!-- 错误提示 -->
      <div class="card error-card" v-if="errorMsg">
        <p style="color: #ff5e5e; font-size: 14px;">{{ errorMsg }}</p>
      </div>

      <!-- 分析结果 -->
      <div v-if="matchResult">
        <div class="card">
          <div class="card-title">匹配度</div>
          <div class="gauge-wrap">
            <svg viewBox="0 0 200 120" class="gauge-svg">
              <!-- 背景弧段：红→橙→绿 -->
              <path d="M 20 100 A 80 80 0 0 1 73 30" fill="none" stroke="#ff5e5e" stroke-width="12" stroke-linecap="round"/>
              <path d="M 73 30 A 80 80 0 0 1 127 30" fill="none" stroke="#f0a040" stroke-width="12" stroke-linecap="round"/>
              <path d="M 127 30 A 80 80 0 0 1 180 100" fill="none" stroke="#00d2a0" stroke-width="12" stroke-linecap="round"/>
              <!-- 指针 -->
              <line
                x1="100" y1="100"
                :x2="100 + 60 * Math.cos(Math.PI - (matchResult.match_rate / 100) * Math.PI)"
                :y2="100 - 60 * Math.sin((matchResult.match_rate / 100) * Math.PI)"
                stroke="#e4e4ec" stroke-width="3" stroke-linecap="round"
              />
              <circle cx="100" cy="100" r="6" fill="#e4e4ec"/>
              <!-- 刻度标签 -->
              <text x="16" y="115" fill="#ff5e5e" font-size="9">0%</text>
              <text x="90" y="18" fill="#f0a040" font-size="9">50%</text>
              <text x="170" y="115" fill="#00d2a0" font-size="9">100%</text>
            </svg>
            <div class="gauge-value">
              <span class="score-num">{{ matchResult.match_rate }}%</span>
              <span class="score-label">岗位匹配度</span>
            </div>
          </div>
        </div>

        <!-- 三维度分解 -->
        <div class="card" v-if="matchResult.dimensions">
          <div class="card-title">匹配维度分解</div>
          <div class="dim-list">
            <div class="dim-item">
              <div class="dim-header">
                <span class="dim-name">学历匹配</span>
                <span class="dim-weight">权重 {{ (matchResult.dimension_weights?.education ?? 0.2) * 100 }}%</span>
                <span class="dim-score">{{ Math.round(matchResult.dimensions.education.score * 100) }}%</span>
              </div>
              <div class="dim-bar"><div class="dim-fill" :style="{width: matchResult.dimensions.education.score * 100 + '%'}"></div></div>
              <div class="dim-detail">{{ matchResult.dimensions.education.detail }}</div>
            </div>
            <div class="dim-item">
              <div class="dim-header">
                <span class="dim-name">技能匹配</span>
                <span class="dim-weight">权重 {{ (matchResult.dimension_weights?.skills ?? 0.5) * 100 }}%</span>
                <span class="dim-score">{{ matchResult.dimensions.skills.rate }}%</span>
              </div>
              <div class="dim-bar"><div class="dim-fill" :style="{width: matchResult.dimensions.skills.rate + '%'}"></div></div>
              <div class="dim-detail">匹配 {{ matchResult.dimensions.skills.matched.length }} / {{ matchResult.dimensions.skills.matched.length + matchResult.dimensions.skills.missing.length }} 项技术要求</div>
            </div>
            <div class="dim-item">
              <div class="dim-header">
                <span class="dim-name">经验相关性</span>
                <span class="dim-weight">权重 {{ (matchResult.dimension_weights?.experience ?? 0.3) * 100 }}%</span>
                <span class="dim-score">{{ Math.round(matchResult.dimensions.experience.score * 100) }}%</span>
              </div>
              <div class="dim-bar"><div class="dim-fill" :style="{width: matchResult.dimensions.experience.score * 100 + '%'}"></div></div>
              <div class="dim-detail">{{ matchResult.dimensions.experience.detail }}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">已匹配技能</div>
          <div class="tags-wrap" v-if="matchResult.matched.length">
            <span class="tag tag-green" v-for="s in matchResult.matched" :key="s">
              {{ s }}<sup class="weight-num" v-if="matchResult.dimensions?.skills?.weights?.[s]">×{{ matchResult.dimensions.skills.weights[s] }}</sup>
            </span>
          </div>
          <p v-else style="color: #9898b0; font-size: 13px;">暂无匹配项</p>
        </div>

        <div class="card">
          <div class="card-title">缺失技术技能（需补强）</div>
          <div class="tags-wrap" v-if="matchResult.missing.length">
            <span class="tag tag-red" v-for="s in matchResult.missing" :key="s">
              {{ s }}<sup class="weight-num" v-if="matchResult.dimensions?.skills?.weights?.[s]">×{{ matchResult.dimensions.skills.weights[s] }}</sup>
            </span>
          </div>
          <p v-else-if="matchResult.matched.length" style="color: #00d2a0; font-size: 13px;">技术技能覆盖完整！</p>
          <p v-else style="color: #9898b0; font-size: 13px;">未提取到技能要求，请检查JD内容或后端服务</p>
        </div>

        <div class="card" v-if="(matchResult.soft_requirements && matchResult.soft_requirements.length) || (matchResult.domain_requirements && matchResult.domain_requirements.length)">
          <div class="card-title">岗位软性要求（参考，非简历必写项）</div>
          <div class="tags-wrap">
            <span class="tag" v-for="s in (matchResult.soft_requirements || [])" :key="'s'+s">{{ s }}</span>
            <span class="tag" v-for="s in (matchResult.domain_requirements || [])" :key="'d'+s">{{ s }}</span>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" @click="startInterview">开始模拟面试 →</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { analyzeJD } from '../api'

const router = useRouter()
const resumeData = ref(null)
const jdText = ref('')
const analyzing = ref(false)
const matchResult = ref(null)
const errorMsg = ref('')

onMounted(() => {
  const stored = sessionStorage.getItem('resumeData')
  if (stored) resumeData.value = JSON.parse(stored)
})

function useTemplate(key) {
  const templates = {
    sde: '岗位职责：\n1. 负责后端服务的设计与开发\n2. 参与系统架构设计与技术选型\n3. 编写高质量、可维护的代码\n\n任职要求：\n- 熟悉 Python/Java/Go 至少一种语言\n- 了解常用数据结构与算法\n- 熟悉 Linux 基本操作\n- 了解数据库（MySQL/Redis）\n- 有团队协作经验，良好的沟通能力\n- 加分项：了解 Docker/K8s、微服务架构',
    pm: '岗位职责：\n1. 负责产品需求分析与PRD撰写\n2. 推动跨部门协作，跟进项目进度\n3. 分析用户反馈，持续优化产品体验\n\n任职要求：\n- 较强的逻辑思维与表达能力\n- 熟练使用 Axure/Figma 等原型工具\n- 了解基本的技术概念（API、数据库）\n- 有数据分析意识\n- 自驱力强，能适应快节奏\n- 加分项：有实习/项目经验',
    data: '岗位职责：\n1. 负责数据清洗、分析与可视化\n2. 建立数据指标体系，输出分析报告\n3. 支持业务决策，挖掘数据价值\n\n任职要求：\n- 熟悉 Python（pandas/numpy）\n- 掌握 SQL\n- 了解机器学习基础\n- 熟悉至少一种可视化工具（Tableau/PowerBI）\n- 良好的业务理解能力\n- 加分项：了解大数据生态（Spark/Hive）',
  }
  jdText.value = templates[key] || ''
}

async function analyze() {
  analyzing.value = true
  matchResult.value = null
  errorMsg.value = ''
  try {
    const res = await analyzeJD(jdText.value, resumeData.value)
    matchResult.value = res.data.match
  } catch (e) {
    if (!e.response) {
      errorMsg.value = '无法连接后端服务，请确认已运行 uvicorn main:app --port 8000'
    } else {
      errorMsg.value = e.response.data?.detail || '分析失败，请重试'
    }
  } finally {
    analyzing.value = false
  }
}

function startInterview() {
  sessionStorage.setItem('jdText', jdText.value)
  router.push('/interview')
}
</script>

<style scoped>
.page-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.page-desc { color: #9898b0; font-size: 14px; margin-bottom: 24px; }
.template-btns { display: flex; gap: 8px; margin-bottom: 12px; }
.gauge-wrap { text-align: center; padding: 8px 0; }
.gauge-svg { width: 220px; max-width: 100%; }
.gauge-value { margin-top: -8px; }
.score-num { font-size: 36px; font-weight: 700; color: #6c5ce7; }
.score-label { display: block; font-size: 13px; color: #9898b0; margin-top: 2px; }
.tags-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.actions { margin-top: 20px; }
.dim-list { display: flex; flex-direction: column; gap: 16px; }
.dim-item { }
.dim-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.dim-name { font-size: 14px; font-weight: 600; color: #e4e4ec; }
.dim-weight { font-size: 12px; color: #9898b0; }
.dim-score { margin-left: auto; font-size: 14px; font-weight: 700; color: #6c5ce7; }
.dim-bar { height: 6px; background: #2a2a3e; border-radius: 3px; overflow: hidden; }
.dim-fill { height: 100%; background: linear-gradient(90deg, #6c5ce7, #00d2a0); border-radius: 3px; transition: width 0.6s ease; }
.dim-detail { font-size: 12px; color: #9898b0; margin-top: 4px; }
.weight-num { font-size: 10px; color: #f0a040; margin-left: 2px; opacity: 0.85; }
</style>
