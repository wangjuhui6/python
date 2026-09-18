<template>
  <el-card class="transform-page">
    <template #header>
      <div class="transform-header">
        <span>按描述执行</span>
        <el-tag :type="loaded ? 'success' : 'warning'">
          {{ loaded ? '模型已加载' : '请先到「本地模型」加载，预览会先让模型理解描述' }}
        </el-tag>
      </div>
    </template>

    <el-input
      v-model="instruction"
      type="textarea"
      :rows="8"
      placeholder="直接写要做什么。改文件名、对照表映射、生成浏览器调用代码都可以。
例如：根据 iso.md 的 ISO 和中文，把 flags 文件夹里的图片改成中文名。
例如：把表格 A B C 列分别做成 name/age/time，每 1 秒按模板 fetch 调用一次接口。"
    />

    <div class="path-row">
      <el-button @click="addFolder">添加文件夹</el-button>
      <el-button @click="addFile">添加文件</el-button>
      <el-button type="primary" :loading="running" @click="previewRun">按描述预览</el-button>
      <el-button type="success" :loading="applying" :disabled="!plan" @click="confirmRun">确认执行</el-button>
    </div>

    <div v-if="paths.length" class="chips">
      <el-tag
        v-for="(item, index) in paths"
        :key="item"
        closable
        class="chip"
        @close="paths.splice(index, 1)"
      >
        {{ item }}
      </el-tag>
    </div>

    <div v-if="plan?.notes" class="preview-block">
      <div class="block-title">理解</div>
      <div>{{ plan.notes }}</div>
      <div class="meta">类型：{{ actionLabel[plan.action] || plan.action || '-' }}</div>
      <div class="meta">来源：{{ plan.source_path || '-' }}</div>
      <div class="meta">对照：{{ plan.mapping_path || '无' }}</div>
      <div class="meta">输出：{{ plan.save_path || '-' }}</div>
      <div class="meta">推理：{{ usedLlm ? '模型理解语句，程序按方案执行' : '未调用模型（规则兜底）' }}</div>
      <div v-if="plan.execute || plan.need_more_ai" class="meta">
        执行：{{ plan.execute === 'llm' || plan.need_more_ai ? '仍需模型继续判断' : '程序执行，不再二次调用模型' }}
      </div>
    </div>

    <div v-if="outputRows.length" class="preview-block">
      <div class="block-title">{{ dryRun ? '将要处理' : '已处理' }} · {{ outputRows.length }} 个</div>
      <el-table :data="outputRows" size="small" max-height="360">
        <el-table-column prop="from_rel" label="原路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="to_rel" label="新路径" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="120" />
      </el-table>
    </div>

    <div v-if="codeText" class="preview-block">
      <div class="block-title">浏览器代码</div>
      <el-input :model-value="codeText" type="textarea" :rows="16" readonly />
      <el-button class="copy-btn" @click="copyCode">复制代码</el-button>
    </div>

    <el-collapse v-if="plan" class="advanced">
      <el-collapse-item title="方案 JSON（可改）" name="plan">
        <el-input v-model="planText" type="textarea" :rows="14" />
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { selectFile, selectFolder } from '@/utils/base'
import { getLlmConfig, runLlmTransform } from '@/api/llm'

const loaded = ref(false)
const instruction = ref('')
const paths = ref<string[]>([])
const plan = ref<any>(null)
const planText = ref('')
const running = ref(false)
const applying = ref(false)
const outputRows = ref<any[]>([])
const dryRun = ref(true)
const codeText = ref('')
const usedLlm = ref(false)
const actionLabel: Record<string, string> = {
  copy: '复制整理',
  move: '移动',
  rename: '改名',
  generate_script: '生成调用代码',
  convert: '转换表格',
}

onMounted(async () => {
  const data = await getLlmConfig()
  loaded.value = !!data?.loaded
})

async function addFolder() {
  const res = await selectFolder()
  if (res && !paths.value.includes(res as string)) {
    paths.value.push(res as string)
  }
}

async function addFile() {
  const res = await selectFile()
  if (res && !paths.value.includes(res as string)) {
    paths.value.push(res as string)
  }
}

function currentPlan() {
  if (planText.value.trim()) {
    return JSON.parse(planText.value)
  }
  return plan.value
}

function applyResult(res: any, isDry: boolean) {
  plan.value = res.plan
  planText.value = JSON.stringify(res.plan || {}, null, 2)
  outputRows.value = res.result?.files || res.files || []
  codeText.value = res.result?.code || ''
  usedLlm.value = !!res.used_llm
  dryRun.value = isDry
}

async function copyCode() {
  if (!codeText.value) {
    return
  }
  await navigator.clipboard.writeText(codeText.value)
  ElMessage.success('已复制，可粘贴到浏览器控制台执行')
}

async function previewRun() {
  if (!instruction.value.trim()) {
    ElMessage.error('请填写描述')
    return
  }
  running.value = true
  try {
    const res = await runLlmTransform({
      instruction: instruction.value,
      paths: paths.value,
      dry_run: true,
    })
    applyResult(res, true)
    ElMessage.success(res.plan?.notes || `将处理 ${outputRows.value.length} 个文件`)
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '预览失败')
  } finally {
    running.value = false
  }
}

async function confirmRun() {
  let current: any
  try {
    current = currentPlan()
  } catch {
    ElMessage.error('方案 JSON 不合法')
    return
  }
  applying.value = true
  try {
    const res = await runLlmTransform({
      instruction: instruction.value,
      paths: paths.value,
      dry_run: false,
      plan: current,
    })
    applyResult(res, false)
    ElMessage.success(res.result?.output ? `已输出到：${res.result.output}` : '执行完成')
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '执行失败')
  } finally {
    applying.value = false
  }
}
</script>

<style scoped lang="less">
.transform-page {
  max-width: 960px;
}
.transform-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.path-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 16px 0 8px;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  max-width: 100%;
}
.preview-block {
  margin-top: 20px;
}
.block-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.meta {
  color: #666;
  font-size: 13px;
  margin-top: 4px;
  word-break: break-all;
}
.copy-btn {
  margin-top: 8px;
}
.advanced {
  margin-top: 16px;
}
</style>
