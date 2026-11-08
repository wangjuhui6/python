<template>
  <el-card class="page">
    <template #header>
      <span>PBF 转 MBTiles</span>
    </template>

    <el-alert
      v-if="env && !env.ready"
      class="hint"
      type="warning"
      :closable="false"
      :title="missingText"
    />
    <el-alert
      v-else
      class="hint"
      type="info"
      :closable="false"
      title="按 OpenMapTiles 规则切瓦片。低级别只保留高速、大河、大城市，建筑和小区路要到 13、14 级才写入。一个省默认切到 14 级，会占用数 GB 内存，并持续一段时间。"
    />

    <div class="form">
      <Upload
        v-model:value="form.inputFile"
        type="file"
        dataType="osmPbf"
        label="PBF 文件"
        placeholder="请选择 .osm.pbf"
      />
      <Upload
        v-model:value="form.outputPath"
        type="savePathAndFileName"
        dataType="mbtiles"
        label="保存为"
        placeholder="请选择 .mbtiles 保存位置"
      />
      <div class="row">
        <span>最大级别</span>
        <el-input-number v-model="form.maxzoom" :min="0" :max="15" />
        <span>内存 GB</span>
        <el-input-number v-model="form.memoryGb" :min="1" :max="64" />
      </div>
      <div class="actions">
        <el-button type="primary" :loading="running" :disabled="running" @click="startConvert">
          开始转换
        </el-button>
        <el-button :disabled="!running" @click="stopConvert">停止</el-button>
        <el-tag v-if="jobStatus === 'running'" type="warning">进行中</el-tag>
        <el-tag v-else-if="jobStatus === 'done'" type="success">已完成</el-tag>
        <el-tag v-else-if="jobStatus === 'error'" type="danger">失败</el-tag>
      </div>
    </div>

    <pre ref="logBox" class="log">{{ logText }}</pre>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import Upload from '@/components/Upload/index.vue'
import {
  osmPbfToMbtiles,
  osmPbfToMbtilesEnv,
  osmPbfToMbtilesStatus,
  osmPbfToMbtilesStop,
} from '@/api/gdal'

const form = ref({
  inputFile: '',
  outputPath: '',
  maxzoom: 14,
  memoryGb: 6,
})

const env = ref<any>(null)
const jobStatus = ref('idle')
const lines = ref<string[]>([])
const logBox = ref<HTMLElement | null>(null)
let timer = 0

const running = computed(() => jobStatus.value === 'running')
const logText = computed(() => lines.value.join('\n'))
const missingText = computed(() => {
  const dir = env.value?.toolDir || 'tools/planetiler'
  return `还没放好转换程序。请把 planetiler.jar 放到 ${dir}，并把 Java 21 绿色版解压到 ${dir}\\jdk，保证存在 jdk\\bin\\java.exe。这台电脑不用单独安装 Java。`
})

watch(logText, async () => {
  await nextTick()
  if (logBox.value) {
    logBox.value.scrollTop = logBox.value.scrollHeight
  }
})

function applyStatus(data: any) {
  if (!data) return
  const previous = jobStatus.value
  jobStatus.value = data.status || 'idle'
  lines.value = data.log || []
  if (previous === 'running' && data.status === 'done') {
    ElMessage.success(data.message || '转换完成')
    stopPoll()
  } else if (previous === 'running' && data.status === 'error') {
    if (data.message !== '已停止') {
      ElMessage.error(data.message || '转换失败')
    }
    stopPoll()
  } else if (data.status !== 'running') {
    stopPoll()
  }
}

async function loadStatus(notify = false) {
  const data: any = await osmPbfToMbtilesStatus()
  if (!notify) {
    jobStatus.value = data?.status || 'idle'
    lines.value = data?.log || []
    if (data?.status === 'running') startPoll()
    return
  }
  applyStatus(data)
}

function startPoll() {
  stopPoll()
  timer = window.setInterval(() => {
    loadStatus(true)
  }, 2000)
}

function stopPoll() {
  if (timer) {
    window.clearInterval(timer)
    timer = 0
  }
}

async function startConvert() {
  if (!form.value.inputFile || !form.value.outputPath) {
    ElMessage.error('请选择 PBF 文件和保存位置')
    return
  }
  try {
    const data: any = await osmPbfToMbtiles({
      inputFile: form.value.inputFile,
      outputPath: form.value.outputPath,
      maxzoom: form.value.maxzoom,
      memoryGb: form.value.memoryGb,
    })
    if (!data?.started) {
      ElMessage.warning(data?.message || '未能开始')
      return
    }
    jobStatus.value = 'running'
    lines.value = []
    ElMessage.success('已开始转换')
    startPoll()
  } catch (error) {
    ElMessage.error(typeof error === 'string' ? error : '转换失败')
  }
}

async function stopConvert() {
  const data: any = await osmPbfToMbtilesStop()
  if (data?.stopped) {
    jobStatus.value = 'error'
    ElMessage.warning('已停止')
    stopPoll()
  }
}

onMounted(async () => {
  env.value = await osmPbfToMbtilesEnv()
  await loadStatus(false)
})

onUnmounted(stopPoll)
</script>

<style scoped lang="less">
.page {
  max-width: 760px;
}
.hint {
  margin-bottom: 16px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.log {
  margin-top: 16px;
  height: 280px;
  overflow: auto;
  padding: 12px;
  background: #111;
  color: #d6d6d6;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.5;
}
</style>
