<template>
  <el-card class="llm-page">
    <template #header>
      <div class="llm-header">
        <span>本地模型</span>
        <el-tag :type="status.loaded ? 'success' : 'info'">
          {{ status.loaded ? '已加载' : '未加载' }}
        </el-tag>
      </div>
    </template>

    <el-alert
      class="llm-alert"
      type="info"
      :closable="false"
      title="模型文件单独放在磁盘任意目录，安装包不包含权重。配置保存在程序目录的 config/llm.json。"
    />

    <el-form label-width="120px" class="llm-form">
      <el-form-item label="运行库">
        <span>{{ status.runtime_message || '检测中...' }}</span>
      </el-form-item>
      <el-form-item label="配置文件">
        <el-input :model-value="status.config_path" readonly />
      </el-form-item>
      <el-form-item label="模型目录">
        <Upload
          v-model:value="form.model_dir"
          type="folder"
          label=""
          placeholder="选择存放 .gguf 的文件夹"
        />
      </el-form-item>
      <el-form-item label="当前模型">
        <Upload
          v-model:value="form.model_path"
          type="file"
          dataType="gguf"
          label=""
          placeholder="选择一个 .gguf 文件"
        />
      </el-form-item>
      <el-form-item label="上下文长度">
        <el-input-number v-model="form.n_ctx" :min="512" :max="32768" :step="512" />
        <span class="llm-hint">越小越快，改名任务 2048 通常够用。改完需重新加载模型</span>
      </el-form-item>
      <el-form-item label="CPU 线程">
        <el-input-number v-model="form.n_threads" :min="1" :max="64" />
        <span class="llm-hint">建议设为物理核心数，不是越大越好</span>
      </el-form-item>
      <el-form-item label="GPU 层数">
        <el-input-number v-model="form.n_gpu_layers" :min="0" :max="99" />
        <span class="llm-hint">无 CUDA 独显保持 0；有 NVIDIA 可逐步加大，改完需重新加载</span>
      </el-form-item>
      <el-form-item label="最大生成长度">
        <el-input-number v-model="form.max_tokens" :min="64" :max="4096" :step="64" />
        <span class="llm-hint">限制模型每次生成多少字，越小越快</span>
      </el-form-item>
      <el-form-item label="跳过语句理解">
        <el-switch v-model="form.skip_llm_for_script" />
        <span class="llm-hint">默认关闭。打开后只靠规则猜字段，说法一变就容易错</span>
      </el-form-item>
      <el-form-item>
        <el-button @click="refreshModels">扫描目录</el-button>
        <el-button type="primary" @click="saveConfig">保存配置</el-button>
        <el-button type="success" :loading="loading" @click="loadModel">加载模型</el-button>
        <el-button @click="unloadModel">卸载</el-button>
      </el-form-item>
    </el-form>

    <el-table :data="models" highlight-current-row @row-click="selectModel">
      <el-table-column prop="name" label="文件名" min-width="240" />
      <el-table-column prop="size_mb" label="大小(MB)" width="120" />
      <el-table-column prop="path" label="路径" min-width="360" show-overflow-tooltip />
      <el-table-column label="操作" width="120">
        <template #default="scope">
          <el-button link type="primary" @click.stop="selectAndLoad(scope.row.path)">加载</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="llm-test">
      <div class="llm-test-title">连通测试</div>
      <el-input
        v-model="prompt"
        type="textarea"
        :rows="3"
        placeholder="输入一段文字，确认模型能离线回答"
      />
      <el-button type="primary" :loading="chatting" @click="runChat">发送</el-button>
      <el-input v-model="answer" type="textarea" :rows="6" readonly placeholder="模型输出" />
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import Upload from '@/components/Upload/index.vue'
import { chatLlm, getLlmConfig, listLlmModels, loadLlm, saveLlmConfig, unloadLlm } from '@/api/llm'

const form = reactive({
  model_dir: '',
  model_path: '',
  n_ctx: 2048,
  n_threads: 4,
  n_gpu_layers: 0,
  skip_llm_for_script: false,
  max_tokens: 512,
})

const status = reactive<any>({
  loaded: false,
  runtime_message: '',
  config_path: '',
})

const models = ref<any[]>([])
const loading = ref(false)
const chatting = ref(false)
const prompt = ref('把下面表格的 name 改成 名称，只输出 JSON：[{"name":"道路"}]')
const answer = ref('')

function applyStatus(data: any) {
  Object.assign(status, data || {})
  form.model_dir = data?.model_dir || ''
  form.model_path = data?.model_path || ''
  form.n_ctx = data?.n_ctx ?? 2048
  form.n_threads = data?.n_threads ?? 4
  form.n_gpu_layers = data?.n_gpu_layers ?? 0
  form.skip_llm_for_script = data?.skip_llm_for_script ?? false
  form.max_tokens = data?.max_tokens ?? 512
}

async function refreshModels() {
  if (!form.model_dir) {
    models.value = []
    return
  }
  models.value = (await listLlmModels(form.model_dir)) || []
}

async function loadStatus() {
  const data = await getLlmConfig()
  applyStatus(data)
  await refreshModels()
}

async function saveConfig() {
  const data = await saveLlmConfig({ ...form })
  applyStatus(data)
  await refreshModels()
  ElMessage.success('配置已保存')
}

async function loadModel(path?: string) {
  loading.value = true
  try {
    await saveLlmConfig({ ...form, model_path: path || form.model_path })
    const data = await loadLlm(path || form.model_path)
    applyStatus(data)
    ElMessage.success('模型已加载')
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '加载失败')
  } finally {
    loading.value = false
  }
}

async function unloadModel() {
  const data = await unloadLlm()
  applyStatus(data)
  ElMessage.success('已卸载')
}

function selectModel(row: any) {
  form.model_path = row.path
}

async function selectAndLoad(path: string) {
  form.model_path = path
  await loadModel(path)
}

async function runChat() {
  chatting.value = true
  try {
    const res = await chatLlm({ prompt: prompt.value })
    answer.value = res?.text || ''
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '调用失败')
  } finally {
    chatting.value = false
  }
}

watch(() => form.model_dir, async (dir, prev) => {
  if (dir && dir !== prev) {
    await refreshModels()
  }
})

onMounted(loadStatus)
</script>

<style scoped lang="less">
.llm-page {
  max-width: 960px;
}
.llm-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.llm-alert {
  margin-bottom: 16px;
}
.llm-form {
  :deep(.upload) {
    width: 100%;
    justify-content: flex-start;
  }
}
.llm-hint {
  margin-left: 8px;
  color: #888;
  font-size: 12px;
}
.llm-test {
  margin-top: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.llm-test-title {
  font-weight: 600;
}
</style>
