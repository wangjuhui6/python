<template>
  <div class="assets-panel">
    <el-form label-position="top" size="small">
      <el-form-item label="样式名称">
        <el-input :model-value="store.style.name" @change="(v: string) => store.updateRoot({ name: v })" />
      </el-form-item>
      <el-form-item label="精灵图 sprite">
        <el-input :model-value="spriteText" placeholder="sprite 或 https://.../sprite" @change="onSprite" />
      </el-form-item>
      <el-button size="small" @click="loadSprite">读取 sprite.json 图标列表</el-button>
      <el-button size="small" @click="router.push('/style/sprite')">打开精灵图编辑器</el-button>
      <div v-if="icons.length" class="icon-list">{{ icons.slice(0, 80).join(', ') }}</div>
      <el-form-item label="字体 glyphs">
        <el-input
          :model-value="store.style.glyphs"
          placeholder="{fontstack}/{range}.pbf"
          @change="(v: string) => store.updateRoot({ glyphs: v })"
        />
      </el-form-item>
      <el-form-item label="已用字体">
        <div class="font-list">{{ fonts.join(' / ') || '暂无 symbol 图层字体' }}</div>
      </el-form-item>
      <el-form-item label="中心点 lng,lat">
        <el-input :model-value="centerText" @change="onCenter" />
      </el-form-item>
      <el-form-item label="zoom / pitch / bearing">
        <div style="display: flex; gap: 6px">
          <el-input-number :model-value="store.style.zoom" size="small" @change="(v: number) => store.updateRoot({ zoom: v })" />
          <el-input-number :model-value="store.style.pitch" size="small" @change="(v: number) => store.updateRoot({ pitch: v })" />
          <el-input-number :model-value="store.style.bearing" size="small" @change="(v: number) => store.updateRoot({ bearing: v })" />
        </div>
      </el-form-item>
      <el-form-item label="全局 transition">
        <div style="display: flex; gap: 6px">
          <el-input-number
            :model-value="store.style.transition?.duration ?? 300"
            size="small"
            @change="(v: number) => store.updateRoot({ transition: { ...store.style.transition, duration: v } })"
          />
          <el-input-number
            :model-value="store.style.transition?.delay ?? 0"
            size="small"
            @change="(v: number) => store.updateRoot({ transition: { ...store.style.transition, delay: v } })"
          />
        </div>
      </el-form-item>
      <el-form-item label="lights / terrain / fog（JSON）">
        <el-input :model-value="extraJson" type="textarea" :rows="8" @change="onExtra" />
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { readStyleFile } from '@/api/style'

const router = useRouter()
const store = useStyleEditorStore()
const icons = ref<string[]>([])

const spriteText = computed(() => {
  const s = store.style.sprite
  if (typeof s === 'string') return s
  if (Array.isArray(s)) return JSON.stringify(s)
  return ''
})

const centerText = computed(() => (store.style.center || []).join(','))

const fonts = computed(() => {
  const set = new Set<string>()
  for (const layer of store.style.layers) {
    const font = layer.layout?.['text-font']
    if (Array.isArray(font)) font.forEach((n: string) => set.add(n))
  }
  return [...set]
})

const extraJson = computed(() =>
  JSON.stringify(
    {
      lights: store.style.lights,
      light: store.style.light,
      terrain: store.style.terrain,
      fog: store.style.fog,
      projection: store.style.projection,
    },
    null,
    2,
  ),
)

function onSprite(v: string) {
  const t = v.trim()
  if (t.startsWith('[')) {
    try {
      store.updateRoot({ sprite: JSON.parse(t) })
      return
    } catch {
      /* ignore */
    }
  }
  store.updateRoot({ sprite: t })
}

function onCenter(v: string) {
  const parts = v.split(',').map((s) => Number(s.trim()))
  if (parts.length >= 2 && parts.every((n) => !Number.isNaN(n))) {
    store.updateRoot({ center: [parts[0], parts[1]] })
  }
}

function onExtra(text: string) {
  try {
    const data = JSON.parse(text)
    store.updateRoot({
      lights: data.lights,
      light: data.light,
      terrain: data.terrain,
      fog: data.fog,
      projection: data.projection,
    })
  } catch {
    ElMessage.error('JSON 无法解析')
  }
}

async function loadSprite() {
  const sprite = store.style.sprite
  const url = typeof sprite === 'string' ? sprite : sprite?.[0]?.url
  if (!url) return
  try {
    const jsonUrl = url.endsWith('.json') ? url : `${url}.json`
    if (/^https?:/i.test(jsonUrl)) {
      const res = await fetch(jsonUrl)
      const data = await res.json()
      icons.value = Object.keys(data)
    } else {
      const text = await readStyleFile(jsonUrl.endsWith('.json') ? jsonUrl : `${jsonUrl}`)
      const data = JSON.parse(text)
      icons.value = Object.keys(data)
    }
    ElMessage.success(`读取到 ${icons.value.length} 个图标`)
  } catch {
    ElMessage.error('无法读取 sprite.json，请确认路径或跨域')
  }
}
</script>

<style scoped lang="less">
.icon-list,
.font-list {
  font-size: 12px;
  color: #606266;
  margin: 8px 0;
  word-break: break-all;
}
</style>
