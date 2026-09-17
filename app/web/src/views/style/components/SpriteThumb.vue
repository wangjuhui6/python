<template>
  <canvas ref="el" class="thumb" :style="{ width: size + 'px', height: size + 'px' }" />
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import { iconImages } from '@/views/style/lib/spritePack'

const props = withDefaults(defineProps<{ uid: string; size?: number }>(), { size: 32 })
const store = useSpriteEditorStore()
const el = ref<HTMLCanvasElement | null>(null)

function draw() {
  const canvas = el.value
  const src = iconImages.get(props.uid)
  if (!canvas || !src) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const max = props.size
  const scale = Math.min(max / src.width, max / src.height, 1)
  canvas.width = Math.max(1, Math.round(src.width * scale))
  canvas.height = Math.max(1, Math.round(src.height * scale))
  ctx.imageSmoothingEnabled = true
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(src, 0, 0, canvas.width, canvas.height)
}

onMounted(draw)
watch(() => [props.uid, props.size, store.icons.find((i) => i.uid === props.uid)?.width], draw)
</script>

<style scoped>
.thumb {
  width: 32px;
  height: 32px;
  object-fit: contain;
  background:
    linear-gradient(45deg, #333 25%, transparent 25%) 0 0 / 8px 8px,
    linear-gradient(-45deg, #333 25%, transparent 25%) 0 4px / 8px 8px,
    linear-gradient(45deg, transparent 75%, #333 75%) 4px -4px / 8px 8px,
    linear-gradient(-45deg, transparent 75%, #333 75%) -4px 0 / 8px 8px,
    #111;
  border-radius: 4px;
  flex-shrink: 0;
}
</style>
