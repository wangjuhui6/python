<template>
  <div class="preview">
    <div class="toolbar">
      <span>精灵图预览 {{ layout.width }}×{{ layout.height }}</span>
      <el-radio-group v-model="bg" size="small">
        <el-radio-button value="black">黑底</el-radio-button>
        <el-radio-button value="check">透明</el-radio-button>
      </el-radio-group>
    </div>
    <div :class="['stage', bg]" @click="onClick">
      <canvas ref="view" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import { drawPacked } from '@/views/style/lib/spritePack'

const store = useSpriteEditorStore()
const layout = computed(() => store.layout)
const bg = ref<'black' | 'check'>('black')
const view = ref<HTMLCanvasElement | null>(null)

function paint() {
  const canvas = view.value
  if (!canvas) return
  const packed = drawPacked(layout.value, 1, bg.value === 'black' ? '#000' : undefined)
  canvas.width = packed.width
  canvas.height = packed.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(packed, 0, 0)
  const selected = layout.value.items.find((i) => i.uid === store.selectedUid)
  if (selected) {
    ctx.strokeStyle = '#409eff'
    ctx.lineWidth = 1
    ctx.strokeRect(selected.x + 0.5, selected.y + 0.5, selected.width - 1, selected.height - 1)
  }
}

function onClick(e: MouseEvent) {
  const canvas = view.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const scaleX = canvas.width / rect.width
  const scaleY = canvas.height / rect.height
  const x = (e.clientX - rect.left) * scaleX
  const y = (e.clientY - rect.top) * scaleY
  const uid = store.hitTest(x, y)
  if (uid) store.select(uid)
}

onMounted(paint)
watch(() => [layout.value, store.selectedUid, store.icons.length, bg.value], paint, { deep: true })
</script>

<style scoped lang="less">
.preview {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  color: #606266;
  border-bottom: 1px solid #ebeef5;
}
.stage {
  flex: 1;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
  padding: 16px;
}
.stage.black {
  background: #111;
}
.stage.check {
  background-image:
    linear-gradient(45deg, #ddd 25%, transparent 25%),
    linear-gradient(-45deg, #ddd 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #ddd 75%),
    linear-gradient(-45deg, transparent 75%, #ddd 75%);
  background-size: 16px 16px;
  background-position:
    0 0,
    0 8px,
    8px -8px,
    -8px 0;
  background-color: #fff;
}
canvas {
  image-rendering: pixelated;
  max-width: 100%;
  height: auto;
  cursor: pointer;
}
</style>
