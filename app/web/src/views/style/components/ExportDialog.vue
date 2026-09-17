<template>
  <el-dialog v-model="visible" title="导出 tileserver-gl 样式" width="560px">
    <el-form label-position="top" size="small">
      <el-form-item label="样式 ID">
        <el-input v-model="form.styleId" />
      </el-form-item>
      <el-form-item label="sprite 相对路径">
        <el-input v-model="form.sprite" placeholder="sprite" />
      </el-form-item>
      <el-form-item label="glyphs 模板">
        <el-input v-model="form.glyphs" placeholder="{fontstack}/{range}.pbf" />
      </el-form-item>
      <el-form-item label="vector 数据源改为 mbtiles://">
        <div v-for="id in vectorIds" :key="id" class="mbtiles-row">
          <span>{{ id }}</span>
          <el-input v-model="form.mbtilesMap[id]" placeholder="data.mbtiles" />
        </div>
      </el-form-item>
      <el-checkbox v-model="form.withConfig">同时导出 tileserver config.json 片段</el-checkbox>
    </el-form>
    <template #footer>
      <el-button @click="copy">复制 style.json</el-button>
      <el-button type="primary" @click="save">保存到文件</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { buildTileserverConfig, rewriteForTileserver } from '@/views/style/lib/tileserverExport'
import { selectSavePathAndFileName } from '@/api/file'
import { writeStyleFile } from '@/api/style'

const visible = defineModel<boolean>({ default: false })
const store = useStyleEditorStore()

const form = reactive({
  styleId: 'mystyle',
  sprite: 'sprite',
  glyphs: '{fontstack}/{range}.pbf',
  mbtilesMap: {} as Record<string, string>,
  withConfig: true,
})

const vectorIds = computed(() =>
  Object.entries(store.style.sources)
    .filter(([, s]: any) => s?.type === 'vector')
    .map(([id]) => id),
)

watch(visible, (v) => {
  if (!v) return
  form.styleId = (store.style.name || 'mystyle').replace(/\s+/g, '-').toLowerCase()
  if (typeof store.style.sprite === 'string' && store.style.sprite && !/^https?:/i.test(store.style.sprite)) {
    form.sprite = store.style.sprite
  }
  if (store.style.glyphs) form.glyphs = store.style.glyphs
  vectorIds.value.forEach((id) => {
    if (!form.mbtilesMap[id]) form.mbtilesMap[id] = ''
  })
})

function exportedStyle() {
  return rewriteForTileserver(store.exportStyle(), {
    sprite: form.sprite,
    glyphs: form.glyphs,
    mbtilesMap: form.mbtilesMap,
  })
}

async function copy() {
  await navigator.clipboard.writeText(JSON.stringify(exportedStyle(), null, 2))
  ElMessage.success('已复制 style.json')
}

async function save() {
  const path = await selectSavePathAndFileName({
    filetypes: [['JSON', '*.json']],
  })
  if (!path) return
  const styleJson = JSON.stringify(exportedStyle(), null, 2)
  await writeStyleFile(path, styleJson)
  if (form.withConfig) {
    const configPath = path.replace(/[^/\\]+$/, 'config.snippet.json')
    await writeStyleFile(configPath, JSON.stringify(buildTileserverConfig(form.styleId), null, 2))
  }
  ElMessage.success('已保存')
}
</script>

<style scoped lang="less">
.mbtiles-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  span {
    width: 120px;
    font-size: 12px;
  }
}
</style>
