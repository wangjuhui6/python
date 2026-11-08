<template>
  <el-card class="page">
    <template #header>
      <span>底图服务</span>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      :title="hint"
    />

    <div class="form">
      <Upload
        v-model:value="form.mbtiles"
        type="file"
        dataType="mbtiles"
        label="MBTiles"
        placeholder="请选择 .mbtiles"
      />
      <Upload
        v-model:value="form.style"
        type="file"
        dataType="json"
        label="样式"
        placeholder="请选择 style.json"
      />
      <div class="actions">
        <el-button type="primary" :loading="starting" :disabled="running" @click="startService">
          启动服务
        </el-button>
        <el-button :disabled="!running" @click="stopService">停止</el-button>
        <el-tag v-if="running" type="success">服务中</el-tag>
        <el-tag v-else type="info">未启动</el-tag>
      </div>
      <div v-if="running" class="urls">
        <div class="url-row">
          <span class="url-text">样式：{{ info.styleUrl }}</span>
          <el-button link type="primary" @click="copyText(info.styleUrl)">复制</el-button>
        </div>
        <div class="url-row">
          <span class="url-text">瓦片：{{ info.tileUrl }}</span>
          <el-button link type="primary" @click="copyText(info.tileUrl)">复制</el-button>
        </div>
      </div>
    </div>

    <div ref="mapEl" class="map"></div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import Upload from '@/components/Upload/index.vue'
import { basemapStart, basemapStatus, basemapStop } from '@/api/basemap'

mapboxgl.accessToken = 'local'

const form = ref({
  mbtiles: '',
  style: '',
})
const info = ref<any>({})
const starting = ref(false)
const mapEl = ref<HTMLDivElement | null>(null)
let map: mapboxgl.Map | null = null

const running = computed(() => !!info.value.running)
let riseFrame = 0
let pitched = false

async function copyText(text: string) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const input = document.createElement('textarea')
    input.value = text
    input.style.position = 'fixed'
    input.style.left = '-9999px'
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    input.remove()
  }
  ElMessage.success('已复制')
}

function stopRise() {
  if (riseFrame) cancelAnimationFrame(riseFrame)
  riseFrame = 0
}

const heightOf = (scale: number): mapboxgl.ExpressionSpecification => [
  '*',
  ['to-number', ['get', 'render_height'], 0],
  scale,
]
const baseOf = (scale: number): mapboxgl.ExpressionSpecification => [
  '*',
  ['to-number', ['get', 'render_min_height'], 0],
  scale,
]

function riseBuildings() {
  if (!map?.getLayer('building-3d')) return
  stopRise()
  const start = performance.now()
  const duration = 3000
  map.setPaintProperty('building-3d', 'fill-extrusion-height', heightOf(0))
  map.setPaintProperty('building-3d', 'fill-extrusion-base', baseOf(0))
  const step = (now: number) => {
    if (!map?.getLayer('building-3d')) {
      riseFrame = 0
      return
    }
    const t = Math.min((now - start) / duration, 1)
    map.setPaintProperty('building-3d', 'fill-extrusion-height', heightOf(t))
    map.setPaintProperty('building-3d', 'fill-extrusion-base', baseOf(t))
    if (t < 1) riseFrame = requestAnimationFrame(step)
    else riseFrame = 0
  }
  riseFrame = requestAnimationFrame(step)
}

function presentBuildings() {
  if (!map || pitched || map.getZoom() < 14 || !map.getLayer('building-3d')) return
  pitched = true
  map.easeTo({ pitch: 52, duration: 900 })
  riseBuildings()
}
const hint = computed(() => {
  const dir = info.value.dir || 'tools/basemap'
  return `从外部目录读取 mbtiles 和样式，不打进安装包。默认目录：${dir}。样式里引用的 sprite、字体放在 style.json 旁边，会一起提供。`
})

function destroyMap() {
  stopRise()
  pitched = false
  map?.remove()
  map = null
}

function showMap(styleUrl: string) {
  if (!mapEl.value || !styleUrl) return
  if (!map) {
    map = new mapboxgl.Map({
      container: mapEl.value,
      style: styleUrl,
      attributionControl: false,
      localFontFamily: '"Microsoft YaHei", "PingFang SC", sans-serif',
    })
    map.addControl(new mapboxgl.NavigationControl(), 'top-right')
    map.on('style.load', () => {
      map?.resize()
      presentBuildings()
    })
    map.on('zoomend', presentBuildings)
    return
  }
  map.setStyle(styleUrl)
}

watch(
  () => [info.value.running, info.value.styleUrl],
  () => {
    if (info.value.running && info.value.styleUrl) showMap(info.value.styleUrl)
    else destroyMap()
  },
)

async function loadStatus() {
  const data: any = await basemapStatus()
  info.value = data || {}
  if (!form.value.mbtiles && data?.mbtiles) form.value.mbtiles = data.mbtiles
  if (!form.value.style && data?.style) form.value.style = data.style
}

async function startService() {
  if (!form.value.mbtiles || !form.value.style) {
    ElMessage.error('请选择 mbtiles 和样式 json')
    return
  }
  starting.value = true
  try {
    const data: any = await basemapStart({
      mbtiles: form.value.mbtiles,
      style: form.value.style,
    })
    if (!data?.started) {
      ElMessage.warning(data?.message || '未能启动')
      return
    }
    ElMessage.success('底图服务已启动')
    await loadStatus()
  } catch (error) {
    ElMessage.error(typeof error === 'string' ? error : '启动失败')
  } finally {
    starting.value = false
  }
}

async function stopService() {
  await basemapStop()
  destroyMap()
  await loadStatus()
  ElMessage.warning('已停止')
}

onMounted(loadStatus)
onUnmounted(destroyMap)
</script>

<style scoped lang="less">
.page {
  max-width: 960px;
}
.hint {
  margin-bottom: 16px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.urls {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #333;
  font-size: 13px;
}
.url-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.url-text {
  word-break: break-all;
}
.map {
  height: 480px;
  margin-top: 16px;
  border-radius: 6px;
  overflow: hidden;
  background: #d5dde6;
}
</style>
