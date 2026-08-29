<template>
  <div class="upload-page">
    <h2 class="page-title">简历智能解析</h2>
    <p class="page-desc">上传 PDF 或 Word 格式简历，AI 自动提取结构化信息</p>

    <!-- 上传区域 -->
    <div class="card" v-if="!resumeData">
      <div
        class="drop-zone"
        :class="{ dragging: isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave="isDragging = false"
        @drop.prevent="handleDrop"
        @click="triggerFileInput"
      >
        <input ref="fileInput" type="file" accept=".pdf,.docx" hidden @change="handleFileSelect" />
        <div class="drop-icon">📄</div>
        <p class="drop-text">拖拽文件到此处，或点击选择</p>
        <p class="drop-hint">支持 PDF、Word(.docx) 格式</p>
      </div>
    </div>

    <!-- 解析中 -->
    <div class="card" v-if="parsing">
      <div class="loading">AI 正在解析简历，请稍候</div>
    </div>

    <!-- 错误提示 -->
    <div class="card error-card" v-if="error">
      <p>⚠️ {{ error }}</p>
      <button class="btn btn-secondary" @click="reset">重新上传</button>
    </div>

    <!-- 解析结果预览 -->
    <div v-if="resumeData && !parsing">
      <div class="card">
        <div class="card-title">基本信息</div>
        <div class="info-grid">
          <div class="info-item">
            <label>姓名</label>
            <input v-model="resumeData.name" />
          </div>
          <div class="info-item">
            <label>邮箱</label>
            <input v-model="resumeData.email" />
          </div>
          <div class="info-item">
            <label>手机</label>
            <input v-model="resumeData.phone" />
          </div>
        </div>
      </div>

      <div class="card" v-if="resumeData.education && resumeData.education.length">
        <div class="card-title">教育经历</div>
        <div v-for="(edu, i) in resumeData.education" :key="i" class="edu-item">
          <div class="edu-display" v-if="editingEdu !== i">
            <strong>{{ edu.school }}</strong><template v-if="edu.major"> · {{ edu.major }}</template><template v-if="edu.degree"> · {{ edu.degree }}</template>
            <span class="edu-date" v-if="edu.start_date || edu.end_date">{{ edu.start_date }}<template v-if="edu.start_date && edu.end_date"> - </template>{{ edu.end_date }}</span>
            <button class="edit-btn" @click="editingEdu = i">编辑</button>
          </div>
          <div class="edu-form" v-else>
            <div class="edu-form-grid">
              <input v-model="edu.school" placeholder="学校" />
              <input v-model="edu.major" placeholder="专业" />
              <input v-model="edu.degree" placeholder="学历" />
              <input v-model="edu.start_date" placeholder="起始日期" />
              <input v-model="edu.end_date" placeholder="结束日期" />
            </div>
            <button class="btn btn-secondary btn-sm" @click="editingEdu = -1">完成</button>
          </div>
        </div>
      </div>

      <div class="card" v-if="resumeData.skills">
        <div class="card-title">技能标签</div>
        <div class="tags-wrap">
          <span class="tag tag-editable" v-for="(skill, i) in resumeData.skills" :key="i">
            {{ skill }}
            <span class="tag-del" @click="removeSkill(i)">&times;</span>
          </span>
        </div>
        <div class="tag-add-row">
          <input v-model="newSkill" placeholder="添加技能" @keydown.enter="addSkill" class="tag-input" />
          <button class="btn btn-secondary btn-sm" @click="addSkill">添加</button>
        </div>
      </div>

      <div class="card" v-if="resumeData.languages && resumeData.languages.length">
        <div class="card-title">语言能力</div>
        <div class="tags-wrap">
          <span class="tag tag-lang" v-for="(lang, i) in resumeData.languages" :key="i">{{ lang }}</span>
        </div>
      </div>

      <div class="card" v-if="resumeData.experiences && resumeData.experiences.length">
        <div class="card-title">工作 / 实习经历</div>
        <div v-for="(exp, i) in resumeData.experiences" :key="i" class="exp-item">
          <div class="exp-header">
            <strong>{{ exp.company }}</strong>
            <span v-if="exp.position" class="exp-pos">{{ exp.position }}</span>
            <span v-if="exp.duration" class="exp-date">{{ exp.duration }}</span>
          </div>
          <p v-if="exp.description" class="exp-desc">{{ exp.description }}</p>
        </div>
      </div>

      <div class="card" v-if="resumeData.projects && resumeData.projects.length">
        <div class="card-title">项目经历</div>
        <div v-for="(proj, i) in resumeData.projects" :key="i" class="proj-item">
          <div v-if="editingProj !== i">
            <strong>{{ proj.name }}</strong><span v-if="proj.role"> · {{ proj.role }}</span>
            <button class="edit-btn" @click="editingProj = i">编辑</button>
            <p v-if="proj.description" class="proj-desc">{{ proj.description }}</p>
            <p v-if="proj.tech_stack" class="proj-tech">技术栈：{{ proj.tech_stack }}</p>
          </div>
          <div class="proj-form" v-else>
            <input v-model="proj.name" placeholder="项目名称" />
            <input v-model="proj.role" placeholder="角色" />
            <textarea v-model="proj.description" placeholder="项目描述" rows="2"></textarea>
            <input v-model="proj.tech_stack" placeholder="技术栈" />
            <button class="btn btn-secondary btn-sm" @click="editingProj = -1">完成</button>
          </div>
        </div>
      </div>

      <div class="actions">
        <button class="btn btn-primary" @click="goToMatch">下一步：JD 匹配 →</button>
        <button class="btn btn-secondary" @click="reset">重新上传</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { uploadResume } from '../api'

const router = useRouter()
const fileInput = ref(null)
const isDragging = ref(false)
const parsing = ref(false)
const error = ref('')
const resumeData = ref(null)
const newSkill = ref('')
const editingEdu = ref(-1)
const editingProj = ref(-1)

function removeSkill(index) {
  resumeData.value.skills.splice(index, 1)
}

function addSkill() {
  const s = newSkill.value.trim()
  if (s && !resumeData.value.skills.includes(s)) {
    resumeData.value.skills.push(s)
  }
  newSkill.value = ''
}

function triggerFileInput() {
  fileInput.value.click()
}

function handleDrop(e) {
  isDragging.value = false
  const file = e.dataTransfer.files[0]
  if (file) processFile(file)
}

function handleFileSelect(e) {
  const file = e.target.files[0]
  if (file) processFile(file)
}

async function processFile(file) {
  if (!file.name.match(/\.(pdf|docx)$/i)) {
    error.value = '仅支持 PDF 和 Word(.docx) 格式'
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    error.value = '文件过大，最大支持 10MB'
    return
  }
  error.value = ''
  parsing.value = true
  try {
    const res = await uploadResume(file)
    resumeData.value = res.data.data
  } catch (e) {
    error.value = e.response?.data?.detail || '解析失败，请重试'
  } finally {
    parsing.value = false
  }
}

function reset() {
  resumeData.value = null
  error.value = ''
}

function goToMatch() {
  // 通过 sessionStorage 传递简历数据
  sessionStorage.setItem('resumeData', JSON.stringify(resumeData.value))
  router.push('/match')
}
</script>

<style scoped>
.page-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.page-desc { color: #9898b0; font-size: 14px; margin-bottom: 24px; }

.drop-zone {
  border: 2px dashed #2a2a38;
  border-radius: 14px;
  padding: 48px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}
.drop-zone:hover, .drop-zone.dragging {
  border-color: #6c5ce7;
  background: rgba(108, 92, 231, 0.05);
}
.drop-icon { font-size: 40px; margin-bottom: 12px; }
.drop-text { font-size: 15px; color: #e4e4ec; }
.drop-hint { font-size: 12px; color: #9898b0; margin-top: 6px; }

.error-card { border-color: #ff5e5e; }
.error-card p { color: #ff5e5e; margin-bottom: 12px; }

.info-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.info-item label { display: block; font-size: 12px; color: #9898b0; margin-bottom: 4px; }
.info-item input { width: 100%; padding: 6px 10px; margin: 0; border: 1px solid #2a2a3e; border-radius: 6px; background: #1a1a2e; color: #e4e4ec; font-size: 14px; box-sizing: border-box; }

.edu-item { padding: 8px 0; border-bottom: 1px solid #2a2a38; font-size: 14px; }
.edu-item:last-child { border-bottom: none; }
.edu-date { color: #9898b0; font-size: 12px; margin-left: 8px; }

.tags-wrap { display: flex; flex-wrap: wrap; gap: 6px; }
.tag-lang { background: rgba(0, 210, 160, 0.12); color: #00d2a0; }

.proj-item { padding: 10px 0; border-bottom: 1px solid #2a2a38; }
.proj-item:last-child { border-bottom: none; }
.proj-desc { font-size: 13px; color: #9898b0; margin-top: 4px; }
.proj-tech { font-size: 12px; color: #6c5ce7; margin-top: 4px; }

.exp-item { padding: 10px 0; border-bottom: 1px solid #2a2a38; }
.exp-item:last-child { border-bottom: none; }
.exp-header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.exp-pos { font-size: 13px; color: #e4e4ec; background: #2a2a3e; padding: 2px 8px; border-radius: 4px; }
.exp-date { font-size: 12px; color: #9898b0; margin-left: auto; }
.exp-desc { font-size: 13px; color: #9898b0; margin-top: 4px; }

.actions { display: flex; gap: 12px; margin-top: 20px; }

.edit-btn {
  margin-left: 8px;
  font-size: 11px;
  color: #9898b0;
  background: none;
  border: 1px solid #3a3a4e;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.edit-btn:hover { color: #6c5ce7; border-color: #6c5ce7; }

.tag-editable { display: inline-flex; align-items: center; gap: 4px; }
.tag-del { cursor: pointer; font-size: 14px; opacity: 0.6; transition: opacity 0.2s; }
.tag-del:hover { opacity: 1; color: #ff5e5e; }

.tag-add-row { display: flex; gap: 8px; margin-top: 10px; }
.tag-input { flex: 1; padding: 6px 10px; margin: 0; border: 1px solid #2a2a3e; border-radius: 6px; background: #1a1a2e; color: #e4e4ec; font-size: 13px; }
.btn-sm { padding: 6px 14px; font-size: 12px; }

.edu-form, .proj-form { margin-top: 8px; }
.edu-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }
.edu-form-grid input, .proj-form input, .proj-form textarea {
  padding: 6px 10px; margin: 0 0 6px; border: 1px solid #2a2a3e; border-radius: 6px; background: #1a1a2e; color: #e4e4ec; font-size: 13px; width: 100%; box-sizing: border-box; min-height: auto;
}
.edu-display { display: flex; align-items: center; flex-wrap: wrap; }
</style>
