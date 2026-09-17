<template>
  <div class="sprite-editor" @dragover.prevent @drop.prevent="onDrop">
    <div class="bar">
      <el-button size="small" @click="goBack">返回</el-button>
      <b class="title">图标精灵图</b>
      <span class="hint">{{ store.icons.length }} 个图标{{ store.dirty ? ' *' : '' }}</span>
      <el-button size="small" @click="goStyle">样式编辑器</el-button>
      <el-button size="small" @click="addIcons">添加图标</el-button>
      <el-button size="small" @click="importAtlas">导入 PNG + JSON</el-button>
      <el-button size="small" @click="importLocal">打开本地文件</el-button>
      <el-button size="small" @click="store.reset()">空白</el-button>
      <el-button size="small" @click="jsonOpen = true">JSON</el-button>
      <el-button type="primary" size="small" @click="exportOpen = true">导出</el-button>
      <input ref="iconInput" type="file" accept="image/*" multiple hidden @change="onAddIcons" />
      <input ref="atlasInput" type="file" accept="image/png,.png,.json,application/json" multiple hidden @change="onAtlasFiles" />
    </div>
    <div class="body">
      <aside class="pane left">
        <div class="pack-opts">
          <div class="lab">间距 padding</div>
          <el-input-number v-model="store.padding" size="small" :min="0" :max="16" />
          <div class="lab">最大行宽</div>
          <el-select v-model="store.maxWidth" size="small">
            <el-option :value="512" label="512" />
            <el-option :value="1024" label="1024" />
            <el-option :value="2048" label="2048" />
            <el-option :value="4096" label="4096" />
          </el-select>
        </div>
        <SpriteIconList />
      </aside>
      <main class="center">
        <SpritePreview />
      </main>
      <aside class="pane right">
        <SpriteIconForm />
      </aside>
    </div>
    <el-drawer v-model="jsonOpen" title="sprite.json" size="420px">
      <el-input :model-value="jsonPreview" type="textarea" :rows="28" readonly />
    </el-drawer>
    <SpriteExportDialog v-model="exportOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import { selectFile } from '@/api/file'
import { readStyleBinary, readStyleFile } from '@/api/style'
import {
  blobToCanvas,
  fileToCanvas,
  iconNameFromFile,
  parseSpriteJson,
  toSpriteJson,
} from '@/views/style/lib/spritePack'
import SpriteIconList from './components/SpriteIconList.vue'
import SpritePreview from './components/SpritePreview.vue'
import SpriteIconForm from './components/SpriteIconForm.vue'
import SpriteExportDialog from './components/SpriteExportDialog.vue'

const router = useRouter()
const store = useSpriteEditorStore()
const jsonOpen = ref(false)
const exportOpen = ref(false)
const iconInput = ref<HTMLInputElement | null>(null)
const atlasInput = ref<HTMLInputElement | null>(null)

const jsonPreview = computed(() => JSON.stringify(toSpriteJson(store.layout, 1), null, 2))

function goBack() {
  router.push('/data/vector')
}

function goStyle() {
  router.push('/style/editor')
}

function addIcons() {
  iconInput.value?.click()
}

function importAtlas() {
  atlasInput.value?.click()
}

async function onAddIcons(e: Event) {
  const files = [...((e.target as HTMLInputElement).files || [])]
  ;(e.target as HTMLInputElement).value = ''
  if (!files.length) return
  try {
    for (const file of files) {
      const canvas = await fileToCanvas(file)
      const { name, pixelRatio } = iconNameFromFile(file.name)
      store.addFromCanvas(canvas, name, { pixelRatio })
    }
    ElMessage.success(`已添加 ${files.length} 个图标`)
  } catch (err: any) {
    ElMessage.error(err?.message || '添加失败')
  }
}

async function applyAtlas(png: Blob, jsonText: string) {
  const json = parseSpriteJson(jsonText)
  const canvas = await blobToCanvas(png)
  store.importFromAtlas(canvas, json)
  ElMessage.success(`已导入 ${store.icons.length} 个图标，可继续编辑`)
}

async function onAtlasFiles(e: Event) {
  const files = [...((e.target as HTMLInputElement).files || [])]
  ;(e.target as HTMLInputElement).value = ''
  const png = files.find((f) => /\.png$/i.test(f.name) || f.type.startsWith('image/'))
  const jsonFile = files.find((f) => /\.json$/i.test(f.name) || f.type.includes('json'))
  if (!png || !jsonFile) {
    ElMessage.warning('请同时选择 sprite.png 和 sprite.json')
    return
  }
  try {
    await applyAtlas(png, await jsonFile.text())
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  }
}

function b64ToBlob(b64: string, type: string) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type })
}

async function onDrop(e: DragEvent) {
  const files = [...(e.dataTransfer?.files || [])]
  if (!files.length) return
  const png = files.find((f) => /\.png$/i.test(f.name) || f.type.startsWith('image/'))
  const jsonFile = files.find((f) => /\.json$/i.test(f.name) || f.type.includes('json'))
  try {
    if (png && jsonFile) {
      await applyAtlas(png, await jsonFile.text())
      return
    }
    const images = files.filter((f) => f.type.startsWith('image/') || /\.(png|webp|gif|svg|jpg|jpeg)$/i.test(f.name))
    if (!images.length) {
      ElMessage.warning('请拖入图标图片，或同时拖入 sprite.png 与 sprite.json')
      return
    }
    for (const file of images) {
      const canvas = await fileToCanvas(file)
      const { name, pixelRatio } = iconNameFromFile(file.name)
      store.addFromCanvas(canvas, name, { pixelRatio })
    }
    ElMessage.success(`已添加 ${images.length} 个图标`)
  } catch (err: any) {
    ElMessage.error(err?.message || '导入失败')
  }
}

async function importLocal() {
  try {
    const pngPath = await selectFile({ filetypes: [['PNG', '*.png']] })
    if (!pngPath) return
    const jsonPath = await selectFile({ filetypes: [['JSON', '*.json']] })
    if (!jsonPath) return
    const b64 = await readStyleBinary(pngPath)
    const text = await readStyleFile(jsonPath)
    await applyAtlas(b64ToBlob(b64, 'image/png'), text)
  } catch (err: any) {
    ElMessage.error(err?.message || '打开失败')
  }
}
</script>

<style scoped lang="less">
.sprite-editor {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
}
.bar {
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
.body {
  flex: 1;
  min-height: 0;
  display: flex;
}
.pane {
  width: 300px;
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
  width: 320px;
  border-left: 1px solid #ebeef5;
  background: #fff;
}
.center {
  flex: 1;
  min-width: 0;
}
.pack-opts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 8px;
  margin-bottom: 12px;
  align-items: center;
  .lab {
    font-size: 12px;
    color: #606266;
  }
}
</style>
