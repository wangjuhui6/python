<template>
  <el-card class="map-legend-page">
    <template #header>
      <div class="page-header">
        <span>地图图例识别</span>
        <el-tag :type="vision ? 'success' : loaded ? 'warning' : 'info'">
          {{ vision ? '视觉模型已加载' : loaded ? '当前是文本模型，请加载 Qwen2.5-VL + mmproj' : '未加载模型' }}
        </el-tag>
      </div>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      title="上传图片后识别点线面。底图只用来对照四个角的经纬度，不参与图上要素识别。"
    />

    <div class="toolbar">
      <input ref="fileInput" class="file-input" type="file" accept="image/*" @change="onNativeFile" />
      <el-button @click="fileInput?.click()">上传图片</el-button>
      <el-radio-group v-model="geoMode" size="small">
        <el-radio-button value="bounds">填写范围</el-radio-button>
        <el-radio-button value="auto">自动对照</el-radio-button>
        <el-radio-button value="points">控制点</el-radio-button>
      </el-radio-group>
      <el-button :type="drawingLegend ? 'warning' : 'default'" :disabled="!imageUrl" @click="toggleDrawLegend">
        {{ drawingLegend ? '正在框选图例' : '框选图例' }}
      </el-button>
      <el-button :disabled="!legendBox" @click="clearLegendBox">清除图例框</el-button>
      <el-button type="primary" :loading="running" :disabled="!canRun" @click="recognize">开始识别</el-button>
      <el-button :disabled="!imageFile" :loading="savingSample" @click="saveAsTrainSample">存为训练样本</el-button>
    </div>

    <el-form label-width="92px" class="form">
      <el-form-item label="左上 / 右下">
        <div class="bounds-row">
          <el-input v-model="nwLng" placeholder="左上经度" />
          <el-input v-model="nwLat" placeholder="左上纬度" />
          <el-input v-model="seLng" placeholder="右下经度" />
          <el-input v-model="seLat" placeholder="右下纬度" />
          <el-button v-if="geoMode === 'bounds'" @click="applyManualBounds">应用到图片</el-button>
          <el-button v-if="geoMode === 'auto'" type="primary" @click="applyApproxBounds(true)">定位底图</el-button>
          <el-button v-if="geoMode === 'auto'" @click="fillFromView">回填当前视野</el-button>
        </div>
        <div class="form-hint">左上=(西,北)，右下=(东,南)。必须填真实经纬度，空白不会当成 0。拖动底图后可点「回填当前视野」。</div>
      </el-form-item>
      <el-form-item v-if="geoMode === 'auto'" label="底图链接">
        <div class="bounds-row">
          <el-input
            v-model="basemapUrl"
            placeholder="style.json 或 {z}/{x}/{y}，空则用 OSM 看中国"
          />
          <el-button :loading="matching" :disabled="!imageUrl" @click="autoAlign">自动对照</el-button>
          <el-button @click="reloadBasemap">重载底图</el-button>
        </div>
        <div v-if="matchStatus" class="form-hint">{{ matchStatus }}</div>
      </el-form-item>
    </el-form>

    <el-input
      v-model="instruction"
      class="instruction"
      type="textarea"
      :rows="2"
      placeholder="可选说明，例如：只要学校和医院；图例在右下角。"
    />

    <div class="workspace" :class="{ 'with-map': geoMode === 'auto' }">
      <div class="pane">
        <div v-if="imageUrl" class="stage">
          <div class="stage-inner">
            <img
              ref="imgRef"
              :src="imageUrl"
              class="map-image"
              :class="{ clickable: geoMode === 'points', drawing: drawingLegend }"
              alt="地图"
              @click="onImageClick"
              @load="onImageLoad"
              @mousedown="onLegendMouseDown"
              @mousemove="onLegendMouseMove"
              @mouseup="onLegendMouseUp"
              @mouseleave="onLegendMouseUp"
            />
            <div v-if="legendBoxStyle" class="legend-box" :style="legendBoxStyle" />
            <button
              v-for="(point, index) in gcps"
              :key="'gcp-' + index"
              class="mark gcp"
              :class="{ active: index === activeIndex }"
              :style="markStyle(point)"
              type="button"
              @click.stop="activeIndex = index"
            >
              {{ index + 1 }}
            </button>
            <span
              v-for="(feat, index) in features"
              :key="'feat-' + index"
              class="mark feat"
              :style="featStyle(feat)"
              :title="feat.name"
            />
          </div>
        </div>
        <div v-else class="empty">上传一张带图例的地图图片</div>
      </div>

      <div v-show="geoMode === 'auto'" class="pane map-pane">
        <div class="map-shell" :style="{ width: mapSize.w + 'px', height: mapSize.h + 'px' }">
          <div ref="mapEl" class="map" />
        </div>
        <div class="form-hint">对照只看几条主路和水体的走向，不比线宽和样式。底图对齐或略大于图片后点自动对照即可。</div>
      </div>

      <div v-if="geoMode === 'points'" class="side">
        <div class="block-title">控制点 · {{ gcps.length }}</div>
        <div class="toolbar tight">
          <el-button size="small" :disabled="!gcps.length" @click="undoPoint">撤销</el-button>
          <el-button size="small" :disabled="!gcps.length" @click="clearPoints">清空</el-button>
        </div>
        <el-table :data="gcps" size="small" max-height="280" highlight-current-row @current-change="onRow">
          <el-table-column label="#" width="44">
            <template #default="scope">{{ scope.$index + 1 }}</template>
          </el-table-column>
          <el-table-column label="X" width="70">
            <template #default="scope">{{ Math.round(scope.row.x) }}</template>
          </el-table-column>
          <el-table-column label="Y" width="70">
            <template #default="scope">{{ Math.round(scope.row.y) }}</template>
          </el-table-column>
          <el-table-column label="经度">
            <template #default="scope">
              <el-input v-model="scope.row.lng" size="small" @focus="activeIndex = scope.$index" />
            </template>
          </el-table-column>
          <el-table-column label="纬度">
            <template #default="scope">
              <el-input v-model="scope.row.lat" size="small" @focus="activeIndex = scope.$index" />
            </template>
          </el-table-column>
          <el-table-column width="52">
            <template #default="scope">
              <el-button link type="danger" @click="removePoint(scope.$index)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div v-if="georef" class="meta">
      配准：{{ georef.kind === 'affine' ? '仿射' : '相似' }} · {{ georef.count }} 点 · 平均残差 {{ georef.mean_error_m }} 米
    </div>
    <div v-if="notes" class="notes">{{ notes }}</div>

    <div v-if="legend.length" class="result">
      <div class="block-title">图例</div>
      <el-table :data="legend" size="small">
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column prop="shape" label="形态" width="90" />
        <el-table-column label="颜色" width="120">
          <template #default="scope">
            <span class="swatch" :style="{ background: scope.row.color || '#ddd' }" />
            {{ scope.row.color || '-' }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="features.length" class="result">
      <div class="block-title">识别要素 · {{ features.length }}</div>
      <el-table :data="features" size="small" max-height="360">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="type" label="类型" width="90" />
        <el-table-column label="经度" min-width="110">
          <template #default="scope">{{ formatLngLat(scope.row.lng) }}</template>
        </el-table-column>
        <el-table-column label="纬度" min-width="110">
          <template #default="scope">{{ formatLngLat(scope.row.lat) }}</template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="geojson" class="result">
      <div class="block-title">GeoJSON · {{ geojson.features?.length || 0 }} 个要素</div>
      <el-input :model-value="geojsonText" type="textarea" :rows="10" readonly />
      <el-button class="copy-btn" @click="copyGeojson">复制 GeoJSON</el-button>
      <el-button class="copy-btn" @click="downloadGeojson">下载 .geojson</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { autoGeoref, getLlmConfig, importTrainLegendSamples, recognizeMapLegend } from '@/api/llm'
import { boundsToGcps } from './lib/georefFit'

type Gcp = { x: number; y: number; lng: string; lat: string; note?: string }
type Feature = {
  name: string
  description?: string
  color?: string
  x: number
  y: number
  lng: number
  lat: number
}

mapboxgl.baseApiUrl = ''

const loaded = ref(false)
const vision = ref(false)
const imageUrl = ref('')
const imageFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const mapEl = ref<HTMLDivElement | null>(null)
const natural = ref({ w: 1, h: 1 })
const gcps = ref<Gcp[]>([])
const activeIndex = ref(-1)
const instruction = ref('')
const running = ref(false)
const savingSample = ref(false)
const matching = ref(false)
const matchStatus = ref('')
const drawingLegend = ref(false)
const legendBox = ref<{ x: number; y: number; w: number; h: number } | null>(null)
let legendDrag: { x: number; y: number } | null = null
const legend = ref<any[]>([])
const features = ref<Feature[]>([])
const georef = ref<any>(null)
const notes = ref('')
const geojson = ref<any>(null)
const geoMode = ref<'bounds' | 'auto' | 'points'>('bounds')
const nwLng = ref('')
const nwLat = ref('')
const seLng = ref('')
const seLat = ref('')
const basemapUrl = ref('')
const mapSize = ref({ w: 480, h: 360 })
const CHINA_CENTER: [number, number] = [104.2, 35.6]
const CHINA_ZOOM = 3.6
const DEFAULT_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

let map: mapboxgl.Map | null = null
let mapResizeObs: ResizeObserver | null = null

const geojsonText = computed(() => geojson.value ? JSON.stringify(geojson.value, null, 2) : '')

const hasValidBounds = computed(() => {
  const b = parseBounds()
  return !!b
})

const readyGcps = computed(() =>
  gcps.value.filter((item) => {
    const lng = parseCoord(item.lng)
    const lat = parseCoord(item.lat)
    return Number.isFinite(lng) && Number.isFinite(lat)
  }),
)

const legendBoxStyle = computed(() => {
  const box = legendBox.value
  if (!box || !natural.value.w || !natural.value.h) return null
  return {
    left: `${(box.x / natural.value.w) * 100}%`,
    top: `${(box.y / natural.value.h) * 100}%`,
    width: `${(box.w / natural.value.w) * 100}%`,
    height: `${(box.h / natural.value.h) * 100}%`,
  }
})

const canRun = computed(() => !!imageFile.value)

onMounted(async () => {
  const data = await getLlmConfig()
  loaded.value = !!data?.loaded
  vision.value = !!data?.vision_enabled
})

onUnmounted(() => {
  destroyMap()
  if (imageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(imageUrl.value)
  }
})

watch(geoMode, async (mode) => {
  if (mode === 'auto') {
    await nextTick()
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    syncMapSize()
    await nextTick()
    createMap()
    window.setTimeout(() => {
      syncMapSize()
      map?.resize()
      applyChinaOrBounds()
    }, 80)
    window.setTimeout(() => {
      syncMapSize()
      map?.resize()
    }, 240)
  } else {
    destroyMap()
  }
})

watch([imageUrl, natural], () => {
  if (geoMode.value !== 'auto') return
  nextTick(() => {
    syncMapSize()
    map?.resize()
  })
})

function parseCoord(raw: string) {
  const text = String(raw ?? '').trim()
  if (!text) return NaN
  const n = Number(text)
  return Number.isFinite(n) ? n : NaN
}

function parseBounds() {
  const west = parseCoord(nwLng.value)
  const north = parseCoord(nwLat.value)
  const east = parseCoord(seLng.value)
  const south = parseCoord(seLat.value)
  if (![west, north, east, south].every(Number.isFinite)) return null
  if (west < -180 || east > 180 || south < -90 || north > 90) return null
  if (west >= east || south >= north) return null
  if (Math.abs(east - west) < 1e-7 && Math.abs(north - south) < 1e-7) return null
  return { west, south, east, north }
}

function applyManualBounds() {
  const b = parseBounds()
  if (!b) {
    ElMessage.warning('请填写完整的左上、右下经纬度')
    return false
  }
  if (!imageUrl.value) {
    ElMessage.warning('请先上传图片')
    return false
  }
  gcps.value = boundsToGcps(natural.value.w, natural.value.h, b.west, b.south, b.east, b.north).map((item) => ({
    x: item.x,
    y: item.y,
    lng: String(item.lng),
    lat: String(item.lat),
    note: item.note,
  }))
  activeIndex.value = 0
  return true
}

function setImage(file: File) {
  if (imageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(imageUrl.value)
  }
  imageFile.value = file
  imageUrl.value = URL.createObjectURL(file)
  gcps.value = []
  features.value = []
  legend.value = []
  georef.value = null
  notes.value = ''
  geojson.value = null
  activeIndex.value = -1
  legendBox.value = null
  drawingLegend.value = false
}

function onNativeFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  setImage(file)
  input.value = ''
}

function onImageLoad() {
  const img = imgRef.value
  if (!img) return
  natural.value = { w: img.naturalWidth || 1, h: img.naturalHeight || 1 }
  syncMapSize()
  if (geoMode.value === 'bounds' && hasValidBounds.value) {
    applyManualBounds()
  }
}

function imagePoint(event: MouseEvent) {
  const img = imgRef.value
  if (!img) return null
  const rect = img.getBoundingClientRect()
  return {
    x: ((event.clientX - rect.left) / rect.width) * natural.value.w,
    y: ((event.clientY - rect.top) / rect.height) * natural.value.h,
  }
}

function toggleDrawLegend() {
  drawingLegend.value = !drawingLegend.value
  if (drawingLegend.value) {
    ElMessage.info('在图片上拖拽框出整块图例，框内不会作为标注点')
  }
}

function clearLegendBox() {
  legendBox.value = null
  drawingLegend.value = false
}

function onLegendMouseDown(event: MouseEvent) {
  if (!drawingLegend.value) return
  event.preventDefault()
  const pt = imagePoint(event)
  if (!pt) return
  legendDrag = pt
  legendBox.value = { x: pt.x, y: pt.y, w: 1, h: 1 }
}

function onLegendMouseMove(event: MouseEvent) {
  if (!drawingLegend.value || !legendDrag) return
  const pt = imagePoint(event)
  if (!pt) return
  const x = Math.min(legendDrag.x, pt.x)
  const y = Math.min(legendDrag.y, pt.y)
  legendBox.value = {
    x,
    y,
    w: Math.abs(pt.x - legendDrag.x),
    h: Math.abs(pt.y - legendDrag.y),
  }
}

function onLegendMouseUp() {
  if (!drawingLegend.value) return
  legendDrag = null
  const box = legendBox.value
  if (box && (box.w < 8 || box.h < 8)) {
    legendBox.value = null
  } else if (box) {
    drawingLegend.value = false
  }
}

function onImageClick(event: MouseEvent) {
  if (drawingLegend.value || geoMode.value !== 'points') return
  const img = imgRef.value
  if (!img) return
  const rect = img.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * natural.value.w
  const y = ((event.clientY - rect.top) / rect.height) * natural.value.h
  gcps.value.push({ x, y, lng: '', lat: '', note: '' })
  activeIndex.value = gcps.value.length - 1
}

function markStyle(point: { x: number; y: number }) {
  return {
    left: `${(point.x / natural.value.w) * 100}%`,
    top: `${(point.y / natural.value.h) * 100}%`,
  }
}

function featStyle(feat: Feature) {
  return { ...markStyle(feat), background: feat.color || '#f56c6c' }
}

function onRow(row: Gcp) {
  activeIndex.value = gcps.value.indexOf(row)
}

function undoPoint() {
  gcps.value.pop()
  activeIndex.value = gcps.value.length - 1
}

function clearPoints() {
  gcps.value = []
  activeIndex.value = -1
}

function removePoint(index: number) {
  gcps.value.splice(index, 1)
  if (activeIndex.value >= gcps.value.length) {
    activeIndex.value = gcps.value.length - 1
  }
}

function isTileTemplate(url: string) {
  return /\{z\}/i.test(url) && /\{x\}/i.test(url) && /\{y\}/i.test(url)
}

function styleSpec() {
  const url = basemapUrl.value.trim() || DEFAULT_TILES
  if (isTileTemplate(url)) {
    return {
      version: 8,
      sources: { basemap: { type: 'raster', tiles: [url], tileSize: 256 } },
      layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': '#e8eef5' } },
        { id: 'basemap', type: 'raster', source: 'basemap' },
      ],
    }
  }
  return url
}

function bindMapResize() {
  mapResizeObs?.disconnect()
  const shell = mapEl.value?.parentElement
  if (!shell || typeof ResizeObserver === 'undefined') return
  mapResizeObs = new ResizeObserver(() => {
    map?.resize()
  })
  mapResizeObs.observe(shell)
}

function syncMapSize() {
  const img = imgRef.value
  const rect = img?.getBoundingClientRect()
  let w = rect && rect.width > 8 ? Math.round(rect.width) : 0
  let h = rect && rect.height > 8 ? Math.round(rect.height) : 0
  if ((!w || !h) && natural.value.w > 1) {
    const pane = mapEl.value?.closest('.map-pane') as HTMLElement | null
    w = Math.round(pane?.clientWidth || 480)
    h = Math.round(w * (natural.value.h / natural.value.w))
  }
  if (!w) w = 480
  if (!h) h = 360
  mapSize.value = { w, h }
}

function destroyMap() {
  mapResizeObs?.disconnect()
  mapResizeObs = null
  if (!map) return
  try {
    map.remove()
  } catch {
    /* ignore */
  }
  map = null
}

function applyChinaOrBounds() {
  if (!map) return
  const b = parseBounds()
  if (b) {
    map.fitBounds(
      [
        [b.west, b.south],
        [b.east, b.north],
      ],
      { padding: 8, duration: 0 },
    )
    return
  }
  map.jumpTo({ center: CHINA_CENTER, zoom: CHINA_ZOOM, bearing: 0, pitch: 0 })
}

function createMap() {
  if (!mapEl.value) return
  destroyMap()
  syncMapSize()
  const opts: any = {
    container: mapEl.value,
    style: styleSpec() as any,
    center: CHINA_CENTER,
    zoom: CHINA_ZOOM,
    attributionControl: false,
    preserveDrawingBuffer: true,
    pitch: 0,
    bearing: 0,
  }
  try {
    map = new mapboxgl.Map({ ...opts, projection: 'mercator' })
  } catch {
    map = new mapboxgl.Map(opts)
  }
  bindMapResize()
  const ready = () => {
    map?.resize()
    applyChinaOrBounds()
  }
  map.on('style.load', () => {
    map?.resize()
    applyChinaOrBounds()
  })
  if (map.loaded()) ready()
  else map.on('load', ready)
  requestAnimationFrame(() => {
    map?.resize()
    applyChinaOrBounds()
  })
}

function reloadBasemap() {
  syncMapSize()
  if (map) {
    const cam = {
      center: map.getCenter(),
      zoom: map.getZoom(),
      bearing: map.getBearing(),
      pitch: map.getPitch(),
    }
    map.setStyle(styleSpec() as any)
    map.once('style.load', () => {
      map?.jumpTo(cam)
      map?.resize()
      applyChinaOrBounds()
    })
    return
  }
  nextTick(() => createMap())
}

function applyApproxBounds(alertOnFail = true) {
  const b = parseBounds()
  if (!b) {
    if (alertOnFail) ElMessage.warning('请填写完整的左上、右下经纬度')
    return
  }
  map?.fitBounds(
    [
      [b.west, b.south],
      [b.east, b.north],
    ],
    { padding: 36, duration: 600 },
  )
}

function fillFromView() {
  if (!map) {
    ElMessage.warning('请先切换到「自动对照」并加载底图')
    return
  }
  const b = map.getBounds()
  if (!b) return
  nwLng.value = b.getWest().toFixed(6)
  nwLat.value = b.getNorth().toFixed(6)
  seLng.value = b.getEast().toFixed(6)
  seLat.value = b.getSouth().toFixed(6)
  ElMessage.success('已回填当前视野的左上、右下坐标')
}

function canvasToBlob(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('无法截取底图'))), 'image/png')
  })
}

function applyMatchData(data: any) {
  gcps.value = (data?.gcps || data?.pairs || []).map((item: any) => {
    const cx = Number(item.canvas_x)
    const cy = Number(item.canvas_y)
    let lng = Number(item.lng)
    let lat = Number(item.lat)
    if (Number.isFinite(cx) && Number.isFinite(cy) && map) {
      const ll = map.unproject([cx, cy])
      lng = ll.lng
      lat = ll.lat
    }
    return { x: item.x, y: item.y, lng: String(lng), lat: String(lat), note: item.note || '' }
  })
}

function applyImageExtent(data: any) {
  const tl = data?.corners?.topLeft
  const br = data?.corners?.bottomRight
  if (Array.isArray(tl) && Array.isArray(br) && tl.length >= 2 && br.length >= 2) {
    nwLng.value = Number(tl[0]).toFixed(6)
    nwLat.value = Number(tl[1]).toFixed(6)
    seLng.value = Number(br[0]).toFixed(6)
    seLat.value = Number(br[1]).toFixed(6)
  } else if ([data?.west, data?.south, data?.east, data?.north].every((n: any) => Number.isFinite(Number(n)))) {
    nwLng.value = Number(data.west).toFixed(6)
    nwLat.value = Number(data.north).toFixed(6)
    seLng.value = Number(data.east).toFixed(6)
    seLat.value = Number(data.south).toFixed(6)
  } else {
    const lngs = gcps.value.map((p) => parseCoord(p.lng)).filter(Number.isFinite)
    const lats = gcps.value.map((p) => parseCoord(p.lat)).filter(Number.isFinite)
    if (lngs.length >= 2 && lats.length >= 2) {
      nwLng.value = Math.min(...lngs).toFixed(6)
      nwLat.value = Math.max(...lats).toFixed(6)
      seLng.value = Math.max(...lngs).toFixed(6)
      seLat.value = Math.min(...lats).toFixed(6)
    }
  }
  applyManualBounds()
}

async function fitMapToImage() {
  const b = parseBounds()
  if (!b || !map) return
  map.fitBounds(
    [
      [b.west, b.south],
      [b.east, b.north],
    ],
    { padding: 0, duration: 400, linear: true },
  )
  await new Promise<void>((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      resolve()
    }
    map!.once('idle', finish)
    window.setTimeout(finish, 1200)
  })
}

async function matchCurrentView(useAi = false) {
  if (!map || !imageUrl.value) return null
  const bounds = map.getBounds()
  if (!bounds) return null
  const canvasBlob = await captureStructureSketch()
  const photoBlob = await fetch(imageUrl.value).then((res) => res.blob())
  const form = new FormData()
  form.append('file', photoBlob, 'map.png')
  form.append('canvas', canvasBlob, 'canvas.png')
  form.append('west', String(bounds.getWest()))
  form.append('south', String(bounds.getSouth()))
  form.append('east', String(bounds.getEast()))
  form.append('north', String(bounds.getNorth()))
  form.append('use_ai', useAi ? '1' : '0')
  return await autoGeoref(form)
}

async function captureStructureSketch() {
  if (!map) throw new Error('底图未加载')
  const src = map.getCanvas()
  const w = Math.max(1, Math.round(src.clientWidth || src.width))
  const h = Math.max(1, Math.round(src.clientHeight || src.height))
  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  const ctx = out.getContext('2d')
  if (!ctx) throw new Error('无法绘制轮廓')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, w, h)
  const skip = new Set(['overlay-image', 'extent-line', 'gcps-circle'])
  const features = map.queryRenderedFeatures().filter((f) => f.layer?.id && !skip.has(f.layer.id))
  let water = 0
  let roads = 0
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'
  for (const feat of features) {
    const id = String(feat.layer?.id || '').toLowerCase()
    const kind = String((feat as any).sourceLayer || feat.layer?.type || '').toLowerCase()
    const text = `${id} ${kind}`
    const isWater = /water|river|lake|ocean|reservoir|canal|stream|海|湖|河/.test(text)
    const isRoad = /road|street|path|highway|bridge|tunnel|rail|路/.test(text)
    if (isWater) {
      ctx.fillStyle = 'rgba(70,140,210,0.85)'
      ctx.strokeStyle = '#2a6aa8'
      ctx.lineWidth = 1.2
      water += drawGeomSketch(ctx, feat.geometry, true)
    } else if (isRoad) {
      ctx.strokeStyle = '#111111'
      ctx.lineWidth = 1.1
      roads += drawGeomSketch(ctx, feat.geometry, false)
    }
  }
  if (water + roads < 12) {
    ctx.drawImage(src, 0, 0, w, h)
  }
  return canvasToBlob(out)
}

function drawGeomSketch(ctx: CanvasRenderingContext2D, geom: any, fillPoly: boolean): number {
  if (!geom || !map) return 0
  const type = geom.type
  if (type === 'LineString') return drawSketchRing(ctx, geom.coordinates, false)
  if (type === 'MultiLineString') {
    return geom.coordinates.reduce((n: number, line: number[][]) => n + drawSketchRing(ctx, line, false), 0)
  }
  if (type === 'Polygon') {
    return geom.coordinates.reduce((n: number, ring: number[][]) => n + drawSketchRing(ctx, ring, fillPoly), 0)
  }
  if (type === 'MultiPolygon') {
    return geom.coordinates.flat().reduce((n: number, ring: number[][]) => n + drawSketchRing(ctx, ring, fillPoly), 0)
  }
  return 0
}

function drawSketchRing(ctx: CanvasRenderingContext2D, coords: number[][], fillPoly: boolean): number {
  if (!map || !coords || coords.length < 2) return 0
  ctx.beginPath()
  coords.forEach((c, i) => {
    const p = map!.project(c as [number, number])
    if (i === 0) ctx.moveTo(p.x, p.y)
    else ctx.lineTo(p.x, p.y)
  })
  if (fillPoly) ctx.fill()
  ctx.stroke()
  return coords.length
}

async function autoAlign() {
  if (!map || !imageUrl.value) return
  matching.value = true
  matchStatus.value = vision.value ? '当前视野对照长路 / 水体…' : '当前视野按轮廓对照…'
  try {
    const data = await matchCurrentView(!!vision.value)
    if (!data?.matched) {
      throw new Error('当前视野未对上。请把底图再对齐一点（可略大于图片）后重试，或直接填写左上/右下后识别。')
    }
    applyMatchData(data)
    applyImageExtent(data)
    await fitMapToImage()
    const how = String(data.method || '').includes('vision') ? '视觉模型' : '轮廓匹配'
    matchStatus.value = `对照完成（${how}），已对齐底图并回填范围，得分 ${data.score}`
    ElMessage.success(`对照完成（${how}），已对齐底图`)
  } catch (err: any) {
    matchStatus.value = ''
    ElMessage.error(typeof err === 'string' ? err : err?.message || '自动对照失败')
  } finally {
    matching.value = false
  }
}

async function recognize() {
  if (!imageFile.value) return
  if (geoMode.value === 'auto' && map && !parseBounds()) {
    fillFromView()
  }
  if (geoMode.value === 'bounds' || (geoMode.value === 'auto' && readyGcps.value.length < 2)) {
    if (!applyManualBounds()) return
  }
  const points = gcps.value
    .map((item) => ({
      x: item.x,
      y: item.y,
      lng: parseCoord(item.lng),
      lat: parseCoord(item.lat),
      note: item.note || '',
    }))
    .filter((item) => Number.isFinite(item.lng) && Number.isFinite(item.lat) && Math.abs(item.lng) <= 180 && Math.abs(item.lat) <= 90)
  const lngSpan = points.length ? Math.max(...points.map((p) => p.lng)) - Math.min(...points.map((p) => p.lng)) : 0
  const latSpan = points.length ? Math.max(...points.map((p) => p.lat)) - Math.min(...points.map((p) => p.lat)) : 0
  if (points.length < 2 || (lngSpan < 1e-7 && latSpan < 1e-7)) {
    ElMessage.error('请填写真实的左上/右下经纬度（空值不会再被当成 0），或至少标注 2 个控制点')
    return
  }
  running.value = true
  try {
    const form = new FormData()
    form.append('file', imageFile.value)
    form.append('gcps', JSON.stringify(points))
    form.append('instruction', instruction.value)
    if (legendBox.value && (legendBox.value.w * legendBox.value.h) / Math.max(1, natural.value.w * natural.value.h) <= 0.28) {
      form.append('legend_box', JSON.stringify(legendBox.value))
    }
    const data = await recognizeMapLegend(form)
    legend.value = data?.legend || []
    features.value = data?.features || []
    georef.value = data?.georef || null
    notes.value = data?.notes || ''
    geojson.value = data?.geojson || null
    if (data?.legend_box && !legendBox.value) {
      legendBox.value = data.legend_box
    }
    const count = (data?.features || []).length || data?.geojson?.features?.length || 0
    if (count) {
      ElMessage.success(`识别完成，生成 ${count} 条`)
    } else {
      ElMessage.warning(data?.notes || '图例已返回，但地图要素为空')
    }
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '识别失败')
  } finally {
    running.value = false
  }
}

async function saveAsTrainSample() {
  if (!imageFile.value) return
  savingSample.value = true
  try {
    const form = new FormData()
    form.append('file', imageFile.value)
    form.append('legend', JSON.stringify(legend.value || []))
    if (legendBox.value) form.append('legend_box', JSON.stringify(legendBox.value))
    form.append('instruction', instruction.value)
    form.append('status', (legend.value || []).length ? 'review' : 'draft')
    form.append('source', (legend.value || []).length ? 'model' : 'human')
    await importTrainLegendSamples(form)
    ElMessage.success('已写入图例训练样本，可在「图例训练样本」页继续改')
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '保存训练样本失败')
  } finally {
    savingSample.value = false
  }
}

function formatLngLat(value: number) {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  return n.toFixed(6)
}

async function copyGeojson() {
  if (!geojsonText.value) return
  await navigator.clipboard.writeText(geojsonText.value)
  ElMessage.success('已复制 GeoJSON')
}

function downloadGeojson() {
  if (!geojsonText.value) return
  const blob = new Blob([geojsonText.value], { type: 'application/geo+json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'map-legend.geojson'
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped lang="less">
.map-legend-page {
  max-width: 1400px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint,
.instruction,
.toolbar,
.form {
  margin-bottom: 12px;
}
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.toolbar.tight {
  margin-bottom: 8px;
}
.bounds-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
  :deep(.el-input) {
    width: 140px;
  }
}
.form-hint {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}
.workspace.with-map {
  grid-template-columns: 1fr 1fr;
}
.stage {
  border: 1px solid #ebeef5;
  background: #f5f7fa;
  overflow: hidden;
}
.stage-inner {
  position: relative;
  width: 100%;
}
.map-image {
  display: block;
  width: 100%;
  height: auto;
}
.map-image.drawing {
  cursor: crosshair;
}
.legend-box {
  position: absolute;
  border: 2px dashed #e6a23c;
  background: rgba(230, 162, 60, 0.18);
  pointer-events: none;
  box-sizing: border-box;
}
.map-shell {
  width: 480px;
  height: 360px;
  max-width: 100%;
  position: relative;
  border: 1px solid #ebeef5;
  background: #d7dee8;
  :deep(.mapboxgl-ctrl-logo),
  :deep(.mapboxgl-ctrl-attrib),
  :deep(.mapboxgl-ctrl-bottom-left),
  :deep(.mapboxgl-ctrl-bottom-right),
  :deep(.mapboxgl-ctrl-top-right),
  :deep(.mapboxgl-ctrl-top-left) {
    display: none !important;
  }
}
.map {
  width: 100%;
  height: 100%;
}
.file-input {
  display: none;
}
.mark {
  position: absolute;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  pointer-events: auto;
}
.gcp {
  width: 22px;
  height: 22px;
  border: 2px solid #fff;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  line-height: 18px;
  padding: 0;
  cursor: pointer;
}
.gcp.active {
  background: #e6a23c;
}
.feat {
  width: 10px;
  height: 10px;
  border: 1px solid #fff;
  pointer-events: none;
}
.empty {
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  border: 1px dashed #dcdfe6;
}
.block-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.meta,
.notes {
  margin-top: 8px;
  color: #606266;
  font-size: 13px;
}
.result {
  margin-top: 20px;
}
.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
  border: 1px solid #ddd;
}
.copy-btn {
  margin-top: 8px;
  margin-right: 8px;
}
@media (max-width: 960px) {
  .workspace,
  .workspace.with-map {
    grid-template-columns: 1fr;
  }
}
</style>
