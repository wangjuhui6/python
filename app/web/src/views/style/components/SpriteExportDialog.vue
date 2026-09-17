<template>
  <el-dialog v-model="visible" title="导出 Mapbox / MapLibre 精灵图" width="520px">
    <el-form label-position="top" size="small">
      <el-form-item label="文件前缀">
        <el-input v-model="prefix" placeholder="sprite" />
      </el-form-item>
      <el-checkbox v-model="with2x">同时导出 @2x（sprite@2x.png / sprite@2x.json）</el-checkbox>
      <p class="hint">输出一对 PNG + JSON，可直接给 style.sprite 使用，例如 sprites/mystyle/sprite</p>
    </el-form>
    <template #footer>
      <el-button @click="download">下载到浏览器</el-button>
      <el-button type="primary" @click="saveFolder">保存到文件夹</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import { selectFolder } from '@/api/file'
import { writeStyleBinary, writeStyleFile } from '@/api/style'
import {
  blobToBase64,
  canvasToPngBlob,
  downloadBlob,
  drawPacked,
  joinPath,
  toSpriteJson,
} from '@/views/style/lib/spritePack'

const visible = defineModel<boolean>({ default: false })
const store = useSpriteEditorStore()
const prefix = ref('sprite')
const with2x = ref(true)

async function files() {
  const layout = store.layout
  if (!layout.items.length) throw new Error('没有图标')
  const name = (prefix.value || 'sprite').replace(/\.png$/i, '').replace(/\.json$/i, '')
  const png = await canvasToPngBlob(drawPacked(layout, 1))
  const json = JSON.stringify(toSpriteJson(layout, 1), null, 2)
  const out: { filename: string; blob?: Blob; text?: string }[] = [
    { filename: `${name}.png`, blob: png },
    { filename: `${name}.json`, text: json },
  ]
  const all1x = layout.items.every((item) => (item.pixelRatio || 1) === 1)
  if (with2x.value) {
    if (!all1x) throw new Error('当前图标已包含 2x，请关闭「同时导出 @2x」或把 pixelRatio 改回 1x')
    const png2 = await canvasToPngBlob(drawPacked(layout, 2))
    out.push({ filename: `${name}@2x.png`, blob: png2 })
    out.push({ filename: `${name}@2x.json`, text: JSON.stringify(toSpriteJson(layout, 2), null, 2) })
  }
  return out
}

async function download() {
  try {
    const list = await files()
    for (const item of list) {
      if (item.blob) downloadBlob(item.blob, item.filename)
      else downloadBlob(new Blob([item.text || ''], { type: 'application/json' }), item.filename)
    }
    store.markClean()
    ElMessage.success('已开始下载 PNG 和 JSON')
  } catch (err: any) {
    ElMessage.error(err?.message || '导出失败')
  }
}

async function saveFolder() {
  try {
    const dir = await selectFolder({})
    if (!dir) return
    const list = await files()
    for (const item of list) {
      const path = joinPath(dir, item.filename)
      if (item.blob) await writeStyleBinary(path, await blobToBase64(item.blob))
      else await writeStyleFile(path, item.text || '')
    }
    store.markClean()
    ElMessage.success('已保存精灵图文件')
  } catch (err: any) {
    ElMessage.error(err?.message || '保存失败')
  }
}
</script>

<style scoped>
.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
}
</style>
