<template>
  <div class="match-page">
    <h2 class="page-title">JD 匹配分析</h2>
    <p class="page-desc">粘贴岗位描述或选择预设模板，分析与简历的技能匹配度</p>

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

      <!-- 分析结果 -->
      <div v-if="matchResult">
        <div class="card">
          <div class="card-title">匹配度</div>
          <div class="match-score">
            <span class="score-num">{{ matchResult.match_rate }}%</span>
            <span class="score-label">技能匹配率</span>
          </div>
        </div>

        <div class="card">
          <div class="card-title">已匹配技能</div>
          <div class="tags-wrap" v-if="matchResult.matched.length">
            <span class="tag tag-green" v-for="s in matchResult.matched" :key="s">{{ s }}</span>
          </div>
          <p v-else style="color: #9898b0; font-size: 13px;">暂无匹配项</p>
        </div>

        <div class="card">
          <div class="card-title">缺失技能（需补强）</div>
          <div class="tags-wrap" v-if="matchResult.missing.length">
            <span class="tag tag-red" v-for="s in matchResult.missing" :key="s">{{ s }}</span>
          </div>
          <p v-else style="color: #00d2a0; font-size: 13px;">技能覆盖完整！</p>
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
  try {
    const res = await analyzeJD(jdText.value, resumeData.value)
    matchResult.value = res.data.match
  } catch (e) {
    alert(e.response?.data?.detail || '分析失败')
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
.match-score { text-align: center; padding: 16px 0; }
.score-num { font-size: 48px; font-weight: 700; color: #6c5ce7; }
.score-label { display: block; font-size: 13px; color: #9898b0; margin-top: 4px; }
.tags-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.actions { margin-top: 20px; }
</style>
