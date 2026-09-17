<template>
  <div class="style-editor">
    <div class="style-editor-bar">
      <el-button size="small" @click="goBack">返回</el-button>
      <b class="title">样式编辑器</b>
      <el-button size="small" @click="router.push('/style/sprite')">图标精灵图</el-button>
      <span class="hint">{{ store.style.name }} {{ store.dirty ? '*' : '' }}</span>
      <el-button size="small" @click="importLocal">导入样式</el-button>
      <el-button size="small" @click="importPath">打开本地文件</el-button>
      <el-button size="small" @click="store.resetEmpty">空白样式</el-button>
      <el-button size="small" @click="jsonOpen = true">JSON</el-button>
      <el-button type="primary" size="small" @click="exportOpen = true">导出 tileserver</el-button>
      <input ref="fileInput" type="file" accept=".json,application/json" hidden @change="onFile" />
    </div>
    <div class="style-editor-body">
      <aside class="pane left">
        <el-tabs v-model="store.leftTab">
          <el-tab-pane label="图层" name="layers">
            <LayerList />
          </el-tab-pane>
          <el-tab-pane label="数据源" name="sources">
            <SourcePanel />
          </el-tab-pane>
          <el-tab-pane label="资源" name="assets">
            <RootAssetsPanel />
          </el-tab-pane>
        </el-tabs>
      </aside>
      <main class="map-wrap">
        <MapPreview />
      </main>
      <aside class="pane right">
        <LayerForm />
      </aside>
    </div>
    <JsonDrawer v-model="jsonOpen" />
    <ExportDialog v-model="exportOpen" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { tryLoadOfficialSpec } from '@/views/style/lib/specFields'
import { selectFile } from '@/api/file'
import { readStyleFile } from '@/api/style'
import LayerList from './components/LayerList.vue'
import SourcePanel from './components/SourcePanel.vue'
import RootAssetsPanel from './components/RootAssetsPanel.vue'
import LayerForm from './components/LayerForm.vue'
import MapPreview from './components/MapPreview.vue'
import JsonDrawer from './components/JsonDrawer.vue'
import ExportDialog from './components/ExportDialog.vue'

const router = useRouter()
const store = useStyleEditorStore()
const jsonOpen = ref(false)
const exportOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => {
  tryLoadOfficialSpec()
})

function goBack() {
  router.push('/data/vector')
}

function importLocal() {
  fileInput.value?.click()
}

function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try {
      store.setStyle(JSON.parse(String(reader.result)))
      ElMessage.success('已导入样式')
    } catch (err: any) {
      ElMessage.error(err?.message || 'JSON 无效')
    }
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

async function importPath() {
  const path = await selectFile({ filetypes: [['JSON', '*.json']] })
  if (!path) return
  const text = await readStyleFile(path)
  store.setStyle(JSON.parse(text))
  ElMessage.success('已打开本地样式')
}
</script>

<style scoped lang="less">
.style-editor {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
}
.style-editor-bar {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
  .title {
    margin-right: 8px;
  }
  .hint {
    color: #909399;
    font-size: 12px;
    margin-right: auto;
  }
}
.style-editor-body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.pane {
  width: 320px;
  flex-shrink: 0;
  overflow: auto;
  padding: 8px 12px;
  box-sizing: border-box;
  background: #fafafa;
}
.left {
  border-right: 1px solid #ebeef5;
}
.right {
  width: 360px;
  border-left: 1px solid #ebeef5;
  background: #fff;
}
.map-wrap {
  flex: 1;
  min-width: 0;
}
</style>
