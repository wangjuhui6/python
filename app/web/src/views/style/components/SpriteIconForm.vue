<template>
  <div v-if="icon" class="form">
    <el-form label-position="top" size="small">
      <el-form-item label="图标预览">
        <div class="big-thumb">
          <SpriteThumb :uid="icon.uid" :size="64" />
        </div>
      </el-form-item>
      <el-form-item label="名称（style 里 icon-image）">
        <el-input :model-value="icon.name" @change="(v: string) => store.updateIcon(icon.uid, { name: v })" />
      </el-form-item>
      <el-form-item label="pixelRatio">
        <el-radio-group :model-value="icon.pixelRatio" @change="(v: number) => store.updateIcon(icon.uid, { pixelRatio: Number(v) })">
          <el-radio-button :value="1">1x</el-radio-button>
          <el-radio-button :value="2">2x</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="SDF">
        <el-switch :model-value="icon.sdf" @change="(v: boolean) => store.updateIcon(icon.uid, { sdf: v })" />
      </el-form-item>
      <el-form-item label="尺寸">
        <span class="muted">{{ icon.width }} × {{ icon.height }}</span>
      </el-form-item>
      <el-form-item label="替换图片">
        <el-button size="small" @click="pickReplace">选择图片</el-button>
      </el-form-item>
      <el-form-item label="content（可选 JSON）">
        <el-input :model-value="jsonText(icon.content)" type="textarea" :rows="2" @change="(v: string) => onJson('content', v)" />
      </el-form-item>
      <el-form-item label="stretchX（可选 JSON）">
        <el-input :model-value="jsonText(icon.stretchX)" type="textarea" :rows="2" @change="(v: string) => onJson('stretchX', v)" />
      </el-form-item>
      <el-form-item label="stretchY（可选 JSON）">
        <el-input :model-value="jsonText(icon.stretchY)" type="textarea" :rows="2" @change="(v: string) => onJson('stretchY', v)" />
      </el-form-item>
    </el-form>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="onReplace" />
  </div>
  <div v-else class="empty">选择左侧图标查看属性</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import { fileToCanvas } from '@/views/style/lib/spritePack'
import SpriteThumb from './SpriteThumb.vue'

const store = useSpriteEditorStore()
const icon = computed(() => store.selected)
const fileInput = ref<HTMLInputElement | null>(null)

function jsonText(v: unknown) {
  return v == null ? '' : JSON.stringify(v)
}

function onJson(key: 'content' | 'stretchX' | 'stretchY', text: string) {
  const cur = icon.value
  if (!cur) return
  const t = text.trim()
  if (!t) {
    store.updateIcon(cur.uid, { [key]: undefined })
    return
  }
  try {
    store.updateIcon(cur.uid, { [key]: JSON.parse(t) })
  } catch {
    ElMessage.error('JSON 无效')
  }
}

function pickReplace() {
  fileInput.value?.click()
}

async function onReplace(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  const cur = icon.value
  ;(e.target as HTMLInputElement).value = ''
  if (!file || !cur) return
  const canvas = await fileToCanvas(file)
  store.replaceImage(cur.uid, canvas)
  ElMessage.success('已替换图片')
}
</script>

<style scoped lang="less">
.form {
  padding-bottom: 16px;
}
.empty {
  color: #909399;
  font-size: 13px;
  padding: 12px 0;
}
.muted {
  font-size: 13px;
  color: #606266;
}
.big-thumb {
  display: inline-block;
}
</style>
