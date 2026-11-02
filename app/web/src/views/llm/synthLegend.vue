<template>
  <el-card class="synth-page">
    <template #header>
      <div class="page-header">
        <span>合成训练图</span>
        <el-tag type="info">生成后写入「图例训练样本」</el-tag>
      </div>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      title="填写底图地址、图例种类和经纬度范围。点类型会从内置地图图标里随机抽取（图例与图上同一套）。每张图至少 2 种图例，并随机标 1～30 个要素。"
    />

    <el-form label-width="108px" class="form">
      <el-form-item label="底图地址">
        <el-input
          v-model="basemapText"
          type="textarea"
          :rows="3"
          placeholder="每行一个。请用完整地址，例如 http://127.0.0.1:8080/styles/xxx/style.json 或 http://host/{z}/{x}/{y}.png"
        />
        <el-button class="apply-btn" @click="previewBasemap">应用底图</el-button>
        <el-button class="apply-btn" :loading="configSaving" @click="saveConfig(true)">保存配置</el-button>
      </el-form-item>
      <el-form-item label="范围 左上/右下">
        <div class="row">
          <el-input v-model="nwLng" placeholder="西经 / 左上经度" />
          <el-input v-model="nwLat" placeholder="北纬 / 左上纬度" />
          <el-input v-model="seLng" placeholder="东经 / 右下经度" />
          <el-input v-model="seLat" placeholder="南纬 / 右下纬度" />
        </div>
      </el-form-item>
      <el-form-item label="生成设置">
        <div class="row wrap">
          <span>张数</span>
          <el-input-number v-model="imageCount" :min="1" :max="200" />
          <span>宽</span>
          <el-input-number v-model="mapWidth" :min="480" :max="1600" :step="80" />
          <span>高</span>
          <el-input-number v-model="mapHeight" :min="360" :max="1200" :step="80" />
          <span>缩放</span>
          <el-input-number v-model="minZoom" :min="3" :max="18" />
          <span>~</span>
          <el-input-number v-model="maxZoom" :min="3" :max="18" />
        </div>
        <div class="row wrap">
          <span>每张要素</span>
          <el-input-number v-model="minFeatures" :min="1" :max="30" />
          <span>~</span>
          <el-input-number v-model="maxFeatures" :min="1" :max="30" />
          <span>每张图例</span>
          <el-input-number v-model="minLegend" :min="2" :max="20" />
          <span>以上（且不必用完全部种类）</span>
        </div>
      </el-form-item>
    </el-form>

    <div class="block-title">图例种类</div>
    <div class="toolbar">
      <el-button size="small" @click="addItem">加一种</el-button>
    </div>
    <el-table :data="catalog" size="small">
      <el-table-column label="名称" min-width="140">
        <template #default="scope">
          <el-input v-model="scope.row.name" size="small" placeholder="景点 / 制高点 / 核心区" />
        </template>
      </el-table-column>
      <el-table-column label="类型" width="130">
        <template #default="scope">
          <el-select v-model="scope.row.shape" size="small">
            <el-option label="点" value="point" />
            <el-option label="线" value="line" />
            <el-option label="面" value="polygon" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="颜色" width="160">
        <template #default="scope">
          <el-input v-model="scope.row.color" size="small" placeholder="#RRGGBB" />
        </template>
      </el-table-column>
      <el-table-column label="描述" min-width="160">
        <template #default="scope">
          <el-input v-model="scope.row.description" size="small" />
        </template>
      </el-table-column>
      <el-table-column width="52">
        <template #default="scope">
          <el-button link type="danger" @click="catalog.splice(scope.$index, 1)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="toolbar">
      <el-button type="primary" :loading="running" @click="generate">开始生成</el-button>
      <el-button :disabled="running" @click="stop = true">停止</el-button>
      <span v-if="progress" class="progress">{{ progress }}</span>
    </div>

    <div class="preview-wrap">
      <div class="map-shell" :style="{ width: mapWidth + 'px', height: mapHeight + 'px' }">
        <div ref="mapEl" class="map" />
      </div>
      <div v-if="previews.length" class="thumbs">
        <img v-for="(url, i) in previews" :key="i" :src="url" class="thumb" alt="" />
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { getSynthLegendConfig, importTrainLegendSamples, saveSynthLegendConfig } from '@/api/llm'

mapboxgl.baseApiUrl = ''

type Item = {
  name: string
  shape: 'point' | 'line' | 'polygon'
  color: string
  description: string
  icon?: string
  iconId?: string
}

const DEFAULT_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const PALETTE = ['#c0392b', '#8e44ad', '#2980b9', '#16a085', '#d35400', '#2c3e50', '#e67e22', '#1abc9c']
const ICON_NAMES = [
  'attraction', 'mountain', 'park', 'hospital', 'school', 'museum', 'cafe',
  'monument', 'cinema', 'star', 'triangle', 'square', 'marker', 'castle',
  'campsite', 'town-hall', 'lodging', 'fuel', 'bus', 'water', 'cemetery',
  'college', 'fire-station', 'police', 'communications-tower', 'lighthouse',
  'embassy', 'soccer',
]

const iconSvg = new Map<string, string>()
const iconCanvas = new Map<string, HTMLCanvasElement>()

const mapEl = ref<HTMLDivElement | null>(null)
const basemapText = ref('')
const nwLng = ref('116.20')
const nwLat = ref('40.05')
const seLng = ref('116.55')
const seLat = ref('39.80')
const imageCount = ref(20)
const mapWidth = ref(960)
const mapHeight = ref(640)
const minZoom = ref(11)
const maxZoom = ref(14)
const minFeatures = ref(3)
const maxFeatures = ref(18)
const minLegend = ref(2)
const running = ref(false)
const stop = ref(false)
const progress = ref('')
const configSaving = ref(false)
const previews = ref<string[]>([])
const catalog = ref<Item[]>([
  { name: '景点', shape: 'point', color: '#c0392b', description: '' },
  { name: '制高点', shape: 'point', color: '#8e44ad', description: '' },
  { name: '核心区', shape: 'polygon', color: '#27ae60', description: '' },
  { name: '往返路线', shape: 'line', color: '#2980b9', description: '' },
])

let map: mapboxgl.Map | null = null
let currentStyleKey = ''
let lastMapError = ''

function rand(min: number, max: number) {
  return min + Math.random() * (max - min)
}

function randInt(min: number, max: number) {
  return Math.floor(rand(min, max + 1))
}

function pick<T>(list: T[]): T {
  return list[randInt(0, list.length - 1)]
}

function shuffle<T>(list: T[]): T[] {
  const copy = [...list]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy
}

function parseCoord(raw: string) {
  const n = Number(String(raw ?? '').trim())
  return Number.isFinite(n) ? n : NaN
}

function parseBounds() {
  const west = parseCoord(nwLng.value)
  const north = parseCoord(nwLat.value)
  const east = parseCoord(seLng.value)
  const south = parseCoord(seLat.value)
  if (![west, north, east, south].every(Number.isFinite)) return null
  if (west >= east || south >= north) return null
  return { west, south, east, north }
}

function basemapUrls() {
  const lines = basemapText.value.split(/\n+/).map((item) => item.trim()).filter(Boolean)
  return (lines.length ? lines : [DEFAULT_TILES]).map((item) => normalizeBasemapUrl(item))
}

function isTileTemplate(url: string) {
  return /\{z\}/i.test(url) && /\{x\}/i.test(url) && /\{y\}/i.test(url)
}

function normalizeBasemapUrl(url: string) {
  let value = url.trim()
  if (!value) return DEFAULT_TILES
  if (value.startsWith('//')) value = `http:${value}`
  if (!/^https?:\/\//i.test(value)) value = `http://${value}`
  return value
}

function rasterStyle(tileUrl: string) {
  return {
    version: 8,
    transition: { duration: 0, delay: 0 },
    sources: { basemap: { type: 'raster', tiles: [tileUrl], tileSize: 256 } },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': '#dbe4ee' } },
      {
        id: 'basemap',
        type: 'raster',
        source: 'basemap',
        paint: { 'raster-fade-duration': 0 },
      },
    ],
  }
}

function emptyStyle() {
  return {
    version: 8,
    sources: {},
    layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#dbe4ee' } }],
  }
}

function proxyUrl(url: string) {
  if (!url) return url
  if (
    url.startsWith('/api/')
    || url.startsWith('blob:')
    || url.startsWith('data:')
    || url.startsWith('mbtiles:')
  ) {
    return url
  }
  if (!/^https?:\/\//i.test(url)) return url
  return `/api/llm/proxy?url=${encodeURIComponent(url)}`
}

function absolutize(value: string, baseUrl: string) {
  if (!value) return value
  if (/^(https?:|data:|mbtiles:)/i.test(value)) return value
  try {
    return new URL(value, baseUrl).href
  } catch {
    return value
  }
}

async function rewriteStyle(style: any, styleUrl: string) {
  const next = JSON.parse(JSON.stringify(style || {}))
  if (typeof next.sprite === 'string') next.sprite = absolutize(next.sprite, styleUrl)
  if (typeof next.glyphs === 'string') next.glyphs = absolutize(next.glyphs, styleUrl)
  const sources = next.sources || {}
  for (const key of Object.keys(sources)) {
    const src = sources[key]
    if (!src || typeof src !== 'object') continue
    if (typeof src.url === 'string' && !/^mbtiles:/i.test(src.url)) {
      src.url = absolutize(src.url, styleUrl)
      if (!src.tiles) {
        try {
          const res = await fetch(proxyUrl(src.url))
          if (res.ok) {
            const tilejson = await res.json()
            if (Array.isArray(tilejson?.tiles) && tilejson.tiles.length) {
              src.tiles = tilejson.tiles.map((item: string) => absolutize(item, src.url))
              if (tilejson.scheme) src.scheme = tilejson.scheme
              delete src.url
            }
          }
        } catch {
          /* keep url */
        }
      }
    }
    if (Array.isArray(src.tiles)) {
      src.tiles = src.tiles.map((item: string) => absolutize(item, styleUrl))
    }
  }
  next.transition = { duration: 0, delay: 0 }
  for (const layer of next.layers || []) {
    if (!layer || typeof layer !== 'object') continue
    layer.paint = layer.paint || {}
    if (layer.type === 'raster') layer.paint['raster-fade-duration'] = 0
  }
  return next
}

const styleCache = new Map<string, any>()

async function loadStyleObject(url: string) {
  const raw = normalizeBasemapUrl(url)
  if (styleCache.has(raw)) return styleCache.get(raw)
  if (isTileTemplate(raw)) {
    const spec = rasterStyle(raw)
    styleCache.set(raw, spec)
    return spec
  }
  const candidates = [raw]
  if (!/style\.json/i.test(raw)) {
    candidates.push(raw.replace(/\/?$/, '/style.json'))
  }
  let lastErr = ''
  for (const candidate of candidates) {
    try {
      const res = await fetch(proxyUrl(candidate))
      if (!res.ok) {
        lastErr = `HTTP ${res.status}`
        continue
      }
      const parsed = JSON.parse(await res.text())
      if (!parsed || parsed.version !== 8 || !parsed.sources) {
        lastErr = '不是 MapLibre/Mapbox style.json'
        continue
      }
      const spec = await rewriteStyle(parsed, candidate)
      styleCache.set(raw, spec)
      styleCache.set(candidate, spec)
      return spec
    } catch (err: any) {
      lastErr = err?.message || String(err)
    }
  }
  throw new Error(`底图无法加载：${raw}${lastErr ? `（${lastErr}）` : ''}。请填写 style.json 或带 {z}/{x}/{y} 的瓦片地址`)
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function waitUntilStyleReady(timeoutMs = 15000) {
  if (!map) return
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    if (map.isStyleLoaded()) return
    await sleep(120)
  }
}

function waitIdle(timeoutMs: number) {
  return new Promise<boolean>((resolve) => {
    if (!map) {
      resolve(false)
      return
    }
    let settled = false
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      map?.off('idle', onIdle)
      resolve(ok)
    }
    const onIdle = () => finish(true)
    const timer = window.setTimeout(() => finish(false), timeoutMs)
    map.once('idle', onIdle)
    map.triggerRepaint()
  })
}

function allSourcesLoaded() {
  if (!map?.isStyleLoaded()) return false
  const sources = map.getStyle()?.sources || {}
  return Object.keys(sources).every((id) => {
    try {
      return map!.isSourceLoaded(id)
    } catch {
      return false
    }
  })
}

function mapFingerprint() {
  if (!map) return ''
  const src = map.getCanvas()
  const w = Math.max(32, Math.min(180, src.width))
  const h = Math.max(24, Math.min(120, src.height))
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) return ''
  try {
    ctx.drawImage(src, 0, 0, w, h)
    const data = ctx.getImageData(0, 0, w, h).data
    let hash = `${w}x${h}`
    for (let i = 0; i < data.length; i += 48 * 4) {
      hash += `:${data[i]}:${data[i + 1]}:${data[i + 2]}`
    }
    return hash
  } catch {
    return `taint-${Date.now()}`
  }
}

async function waitUntilCanvasStable(timeoutMs = 8000) {
  const start = Date.now()
  let prev = ''
  let same = 0
  while (Date.now() - start < timeoutMs) {
    await sleep(320)
    const next = mapFingerprint()
    if (next && next === prev) {
      same += 1
      if (same >= 2 && map?.areTilesLoaded() && allSourcesLoaded()) return true
    } else {
      same = 0
      prev = next
    }
  }
  return same >= 1
}

async function waitForFullyRendered(timeoutMs = 20000) {
  if (!map) return
  map.resize()
  await waitUntilStyleReady(Math.min(12000, timeoutMs))
  await sleep(80)
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const gotIdle = await waitIdle(Math.min(10000, deadline - Date.now()))
    if (
      gotIdle
      && map.isStyleLoaded()
      && map.areTilesLoaded()
      && allSourcesLoaded()
      && !map.isMoving()
      && !map.isZooming()
    ) {
      const stable = await waitUntilCanvasStable(Math.min(6000, deadline - Date.now()))
      if (stable && map.areTilesLoaded() && allSourcesLoaded()) return
    }
    await sleep(200)
  }
}

function addItem() {
  catalog.value.push({
    name: '',
    shape: 'point',
    color: PALETTE[catalog.value.length % PALETTE.length],
    description: '',
  })
}

function validCatalog() {
  return catalog.value.filter((item) => item.name.trim() && ['point', 'line', 'polygon'].includes(item.shape))
}

function emptyFc() {
  return { type: 'FeatureCollection' as const, features: [] as any[] }
}

function ensureLayers() {
  if (!map) return
  if (!map.getSource('synth')) {
    map.addSource('synth', { type: 'geojson', data: emptyFc() })
  }
  if (!map.getLayer('synth-fill')) {
    map.addLayer({
      id: 'synth-fill',
      type: 'fill',
      source: 'synth',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.35 },
    })
  }
  if (!map.getLayer('synth-line')) {
    map.addLayer({
      id: 'synth-line',
      type: 'line',
      source: 'synth',
      filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': ['get', 'color'], 'line-width': 3 },
    })
  }
  if (!map.getLayer('synth-outline')) {
    map.addLayer({
      id: 'synth-outline',
      type: 'line',
      source: 'synth',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'line-color': ['get', 'color'], 'line-width': 2 },
    })
  }
  if (map.getLayer('synth-point')) {
    map.removeLayer('synth-point')
  }
  map.addLayer({
    id: 'synth-point',
    type: 'symbol',
    source: 'synth',
    filter: ['==', ['geometry-type'], 'Point'],
    layout: {
      'icon-image': ['get', 'iconId'],
      'icon-size': 1,
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
}

function createMap() {
  if (!mapEl.value) return
  if (map) {
    map.remove()
    map = null
  }
  currentStyleKey = ''
  lastMapError = ''
  const opts: any = {
    container: mapEl.value,
    style: emptyStyle() as any,
    center: [116.4, 39.9],
    zoom: 12,
    attributionControl: false,
    preserveDrawingBuffer: true,
    pixelRatio: 1,
    fadeDuration: 0,
  }
  try {
    map = new mapboxgl.Map({ ...opts, projection: 'mercator' })
  } catch {
    map = new mapboxgl.Map(opts)
  }
  map.on('error', (event: any) => {
    const msg = event?.error?.message || event?.message || ''
    if (msg) lastMapError = msg
  })
  map.on('style.load', () => {
    try {
      ensureLayers()
    } catch {
      /* style 切换中可能尚未就绪 */
    }
  })
}

async function applyStyle(url: string, force = false) {
  if (!map) createMap()
  if (!map) throw new Error('地图未创建')
  const key = normalizeBasemapUrl(url)
  if (!force && currentStyleKey === key && map.isStyleLoaded()) {
    ensureLayers()
    return
  }
  lastMapError = ''
  currentStyleKey = key

  const waitStyleLoad = () => new Promise<void>((resolve) => {
    const timer = window.setTimeout(() => resolve(), 12000)
    map!.once('style.load', () => {
      window.clearTimeout(timer)
      resolve()
    })
  })

  if (isTileTemplate(key)) {
    const pending = waitStyleLoad()
    map.setStyle(rasterStyle(key) as any)
    await pending
  } else {
    const pending = waitStyleLoad()
    map.setStyle(key)
    await pending
    const failed = /fetch|CORS|NetworkError|Failed|blocked/i.test(lastMapError)
    if (failed || !map.isStyleLoaded()) {
      lastMapError = ''
      const obj = await loadStyleObject(key)
      const pending2 = waitStyleLoad()
      map.setStyle(obj as any)
      await pending2
    }
  }
  await waitUntilStyleReady(8000)
  if (!map.isStyleLoaded()) {
    throw new Error(lastMapError || '底图样式仍未就绪，请检查地址是否可访问')
  }
  map.resize()
  ensureLayers()
}

async function previewBasemap() {
  try {
    progress.value = '正在加载底图…'
    styleCache.clear()
    await applyStyle(basemapUrls()[0], true)
    await nextTick()
    map?.resize()
    const bounds = parseBounds()
    if (bounds) {
      map?.fitBounds(
        [
          [bounds.west, bounds.south],
          [bounds.east, bounds.north],
        ],
        { padding: 16, duration: 0 },
      )
    }
    await waitForFullyRendered(18000)
    progress.value = '底图已应用'
    ElMessage.success('底图已应用，确认预览无误后再生成')
  } catch (err: any) {
    progress.value = ''
    ElMessage.error(typeof err === 'string' ? err : err?.message || '底图加载失败')
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function randomView(bounds: { west: number; south: number; east: number; north: number }) {
  const zoom = rand(Math.min(minZoom.value, maxZoom.value), Math.max(minZoom.value, maxZoom.value))
  const padLng = (bounds.east - bounds.west) * 0.08
  const padLat = (bounds.north - bounds.south) * 0.08
  const lng = rand(bounds.west + padLng, bounds.east - padLng)
  const lat = rand(bounds.south + padLat, bounds.north - padLat)
  return { lng, lat, zoom }
}

function visibleBox() {
  const b = map!.getBounds()
  if (!b) throw new Error('底图范围未就绪')
  return {
    west: b.getWest(),
    south: b.getSouth(),
    east: b.getEast(),
    north: b.getNorth(),
  }
}

function randomLngLat(box: { west: number; south: number; east: number; north: number }, inset = 0.12) {
  const lngSpan = box.east - box.west
  const latSpan = box.north - box.south
  return [
    rand(box.west + lngSpan * inset, box.east - lngSpan * inset),
    rand(box.south + latSpan * inset, box.north - latSpan * inset),
  ] as [number, number]
}

function makePoint(item: Item, box: ReturnType<typeof visibleBox>) {
  return {
    type: 'Feature',
    properties: {
      name: item.name,
      color: item.color,
      shape: item.shape,
      icon: item.icon || '',
      iconId: item.iconId || '',
    },
    geometry: { type: 'Point', coordinates: randomLngLat(box) },
  }
}

function makeLine(item: Item, box: ReturnType<typeof visibleBox>) {
  const n = randInt(4, 8)
  let [lng, lat] = randomLngLat(box, 0.18)
  const coords: number[][] = [[lng, lat]]
  const stepLng = (box.east - box.west) * 0.06
  const stepLat = (box.north - box.south) * 0.06
  for (let i = 1; i < n; i++) {
    lng = clamp(lng + rand(-stepLng, stepLng), box.west, box.east)
    lat = clamp(lat + rand(-stepLat, stepLat), box.south, box.north)
    coords.push([lng, lat])
  }
  return {
    type: 'Feature',
    properties: { name: item.name, color: item.color, shape: item.shape },
    geometry: { type: 'LineString', coordinates: coords },
  }
}

function makePolygon(item: Item, box: ReturnType<typeof visibleBox>) {
  const [cx, cy] = randomLngLat(box, 0.22)
  const rx = (box.east - box.west) * rand(0.04, 0.09)
  const ry = (box.north - box.south) * rand(0.04, 0.09)
  const coords: number[][] = []
  const n = randInt(5, 7)
  for (let i = 0; i < n; i++) {
    const a = (Math.PI * 2 * i) / n
    coords.push([cx + Math.cos(a) * rx * rand(0.7, 1.1), cy + Math.sin(a) * ry * rand(0.7, 1.1)])
  }
  coords.push(coords[0])
  return {
    type: 'Feature',
    properties: { name: item.name, color: item.color, shape: item.shape },
    geometry: { type: 'Polygon', coordinates: [coords] },
  }
}

function makeFeature(item: Item, box: ReturnType<typeof visibleBox>) {
  if (item.shape === 'line') return makeLine(item, box)
  if (item.shape === 'polygon') return makePolygon(item, box)
  return makePoint(item, box)
}

function pickLegendSet(items: Item[]) {
  const maxN = items.length
  const minN = Math.min(Math.max(2, minLegend.value), maxN)
  const n = randInt(minN, maxN)
  return assignPointIcons(shuffle(items).slice(0, n))
}

async function loadIconSvgs() {
  if (iconSvg.size) return
  await Promise.all(ICON_NAMES.map(async (name) => {
    try {
      const res = await fetch(`/legend-icons/${name}.svg`)
      if (res.ok) iconSvg.set(name, await res.text())
    } catch {
      /* skip missing icon */
    }
  }))
}

function assignPointIcons(items: Item[]): Item[] {
  const pool = shuffle([...iconSvg.keys()])
  let index = 0
  return items.map((item) => {
    if (item.shape !== 'point') return { ...item }
    const icon = pool[index % Math.max(pool.length, 1)] || 'marker'
    index += 1
    return { ...item, icon }
  })
}

async function rasterIcon(name: string, color: string, size = 36) {
  const key = `${name}|${color}|${size}`
  const cached = iconCanvas.get(key)
  if (cached) return cached
  let svg = iconSvg.get(name) || iconSvg.get('marker') || ''
  if (!svg) throw new Error('未找到点图标')
  const fill = color || '#222222'
  svg = svg
    .replace(/fill="[^"]*"/g, `fill="${fill}"`)
    .replace(/<svg\b/, `<svg fill="${fill}"`)
    .replace(/<path\b/g, `<path fill="${fill}"`)
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  try {
    const img = new Image()
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error(`图标无法绘制：${name}`))
      img.src = url
    })
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法绘制图标')
    ctx.drawImage(img, 1, 1, size - 2, size - 2)
    iconCanvas.set(key, canvas)
    return canvas
  } finally {
    URL.revokeObjectURL(url)
  }
}

async function preparePointIcons(items: Item[]) {
  if (!map) return items
  const next: Item[] = []
  for (const item of items) {
    if (item.shape !== 'point') {
      next.push(item)
      continue
    }
    const icon = item.icon || 'marker'
    const canvas = await rasterIcon(icon, item.color || '#222222')
    const iconId = `poi-${icon}-${(item.color || '222').replace('#', '')}`
    await waitUntilStyleReady(8000)
    if (map.hasImage(iconId)) {
      try {
        map.removeImage(iconId)
      } catch {
        /* ignore */
      }
    }
    const ctx = canvas.getContext('2d')
    const copied = ctx?.getImageData(0, 0, canvas.width, canvas.height)
    if (!copied) throw new Error('无法读取图标')
    map.addImage(iconId, copied)
    next.push({ ...item, icon, iconId })
  }
  return next
}

function paintLegend(
  ctx: CanvasRenderingContext2D,
  items: Item[],
  width: number,
  height: number,
) {
  const pad = 10
  const rowH = 28
  const titleH = 22
  const innerW = Math.max(...items.map((item) => ctx.measureText(item.name).width), 48) + 52
  const boxW = Math.ceil(innerW + pad * 2)
  const boxH = Math.ceil(titleH + items.length * rowH + pad * 2)
  const corners = [
    { x: 16, y: 16 },
    { x: width - boxW - 16, y: 16 },
    { x: 16, y: height - boxH - 16 },
    { x: width - boxW - 16, y: height - boxH - 16 },
  ]
  const origin = pick(corners)
  ctx.save()
  ctx.fillStyle = 'rgba(255,255,255,0.92)'
  ctx.strokeStyle = 'rgba(0,0,0,0.25)'
  ctx.lineWidth = 1
  ctx.fillRect(origin.x, origin.y, boxW, boxH)
  ctx.strokeRect(origin.x, origin.y, boxW, boxH)
  ctx.fillStyle = '#222'
  ctx.font = 'bold 13px sans-serif'
  ctx.fillText('图例', origin.x + pad, origin.y + pad + 14)
  ctx.font = '12px sans-serif'
  items.forEach((item, index) => {
    const y = origin.y + pad + titleH + index * rowH + 4
    const x = origin.x + pad
    ctx.fillStyle = item.color || '#666'
    if (item.shape === 'line') {
      ctx.strokeStyle = item.color || '#666'
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.moveTo(x, y + 8)
      ctx.lineTo(x + 18, y + 8)
      ctx.stroke()
    } else if (item.shape === 'polygon') {
      ctx.globalAlpha = 0.45
      ctx.fillRect(x, y, 18, 14)
      ctx.globalAlpha = 1
      ctx.strokeStyle = item.color || '#666'
      ctx.lineWidth = 1.5
      ctx.strokeRect(x, y, 18, 14)
    } else {
      const sprite = iconCanvas.get(`${item.icon || 'marker'}|${item.color || '#222222'}|36`)
      if (sprite) {
        ctx.drawImage(sprite, x, y - 2, 22, 22)
      } else {
        ctx.beginPath()
        ctx.arc(x + 8, y + 8, 6, 0, Math.PI * 2)
        ctx.fill()
      }
    }
    ctx.fillStyle = '#222'
    ctx.fillText(item.name, x + 28, y + 14)
  })
  ctx.restore()
  return { x: origin.x, y: origin.y, w: boxW, h: boxH }
}

function canvasToFile(canvas: HTMLCanvasElement, name: string) {
  return new Promise<File>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('截图失败，请确认底图允许跨域或使用本机 style.json'))
        return
      }
      resolve(new File([blob], name, { type: 'image/png' }))
    }, 'image/png')
  })
}

function canvasLooksEmpty(canvas: HTMLCanvasElement) {
  try {
    const ctx = canvas.getContext('2d')
    if (!ctx) return true
    const { width, height } = canvas
    if (width < 8 || height < 8) return true
    const step = Math.max(16, Math.floor(Math.min(width, height) / 12))
    const samples: number[] = []
    for (let y = 4; y < height - 4; y += step) {
      for (let x = 4; x < width - 4; x += step) {
        const p = ctx.getImageData(x, y, 1, 1).data
        samples.push(p[0] + p[1] + p[2])
      }
    }
    if (samples.length < 8) return true
    const avg = samples.reduce((a, b) => a + b, 0) / samples.length
    const variance = samples.reduce((a, b) => a + (b - avg) ** 2, 0) / samples.length
    return variance < 80
  } catch {
    return true
  }
}

async function capture(items: Item[]) {
  if (!map) throw new Error('地图未创建')
  const src = map.getCanvas()
  const canvas = document.createElement('canvas')
  canvas.width = src.width
  canvas.height = src.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法绘图')
  try {
    ctx.drawImage(src, 0, 0)
  } catch {
    throw new Error('底图截图被浏览器拦截（跨域），请用本机 style.json 或瓦片地址')
  }
  if (canvasLooksEmpty(canvas)) {
    throw new Error('底图尚未画上')
  }
  ctx.font = '12px sans-serif'
  const box = paintLegend(ctx, items, canvas.width, canvas.height)
  const file = await canvasToFile(canvas, `synth-${Date.now()}.png`)
  const url = URL.createObjectURL(file)
  return { file, box, url }
}

async function captureReady(items: Item[]) {
  let lastErr = '底图尚未画上'
  for (let attempt = 0; attempt < 4; attempt++) {
    await waitForFullyRendered(attempt === 0 ? 18000 : 8000)
    try {
      return await capture(items)
    } catch (err: any) {
      lastErr = err?.message || String(err)
      if (String(lastErr).includes('跨域')) throw err
    }
  }
  throw new Error(lastErr)
}

async function generate() {
  const bounds = parseBounds()
  if (!bounds) {
    ElMessage.warning('请填写有效的左上 / 右下经纬度')
    return
  }
  const items = validCatalog()
  if (items.length < 2) {
    ElMessage.warning('至少需要 2 种已填写名称的图例')
    return
  }
  if (!map) createMap()
  await loadIconSvgs()
  if (!iconSvg.size) {
    ElMessage.error('点图标未加载，请确认 /legend-icons 目录存在')
    return
  }
  running.value = true
  stop.value = false
  previews.value.forEach((url) => URL.revokeObjectURL(url))
  previews.value = []
  let ok = 0
  let skipped = 0
  try {
    for (let i = 0; i < imageCount.value; i++) {
      if (stop.value) break
      progress.value = `正在生成 ${i + 1} / ${imageCount.value}`
      try {
        const styleUrl = pick(basemapUrls())
        await applyStyle(styleUrl, i === 0)
        const view = randomView(bounds)
        map!.jumpTo({ center: [view.lng, view.lat], zoom: view.zoom, bearing: rand(-12, 12), pitch: 0 })
        await waitForFullyRendered(20000)
        const box = visibleBox()
        const legendItems = await preparePointIcons(pickLegendSet(items))
        const featMin = Math.min(minFeatures.value, maxFeatures.value)
        const featMax = Math.max(minFeatures.value, maxFeatures.value)
        const featCount = randInt(featMin, featMax)
        const features: any[] = legendItems.map((item) => makeFeature(item, box))
        while (features.length < featCount) {
          features.push(makeFeature(pick(legendItems), box))
        }
        const source = map!.getSource('synth') as mapboxgl.GeoJSONSource
        if (!source) throw new Error('标注图层未就绪，请先点「应用底图」确认底图可用')
        source.setData({ type: 'FeatureCollection', features })
        const shot = await captureReady(legendItems)
        const pixelFeats = features.map((feat: any) => {
          const geom = feat.geometry
          let coord = [0, 0]
          if (geom?.type === 'Point') coord = geom.coordinates
          else if (geom?.type === 'LineString' && geom.coordinates?.length) {
            coord = geom.coordinates[Math.floor(geom.coordinates.length / 2)]
          } else if (geom?.type === 'Polygon' && geom.coordinates?.[0]?.length) {
            const ring = geom.coordinates[0]
            coord = [
              ring.reduce((s: number, p: number[]) => s + p[0], 0) / ring.length,
              ring.reduce((s: number, p: number[]) => s + p[1], 0) / ring.length,
            ]
          }
          const pt = map!.project(coord as [number, number])
          return {
            name: feat.properties?.name,
            shape: feat.properties?.shape,
            color: feat.properties?.color,
            x: pt.x,
            y: pt.y,
          }
        })
        const form = new FormData()
        form.append('file', shot.file)
        form.append('legend', JSON.stringify(legendItems.map((item) => ({
          name: item.name,
          shape: item.shape,
          color: item.color,
          description: item.description || '',
        }))))
        form.append('legend_box', JSON.stringify(shot.box))
        form.append('features', JSON.stringify(pixelFeats))
        form.append('instruction', '')
        form.append('status', 'accepted')
        form.append('source', 'synthetic')
        await importTrainLegendSamples(form)
        previews.value = [shot.url, ...previews.value].slice(0, 8)
        ok += 1
      } catch (err: any) {
        skipped += 1
        progress.value = `第 ${i + 1} 张跳过：${typeof err === 'string' ? err : err?.message || '失败'}，继续 ${i + 2 > imageCount.value ? '' : i + 2 + '/' + imageCount.value}`
      }
    }
    if (ok) {
      ElMessage.success(`已生成并入库 ${ok} 张${skipped ? `，跳过 ${skipped} 张` : ''}，请到「图例训练样本」查看`)
    } else {
      ElMessage.error(skipped ? '全部失败。请先点「应用底图」确认预览有底图后再生成' : '未生成')
    }
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : err?.message || '生成失败')
  } finally {
    running.value = false
    progress.value = ok ? `完成 ${ok} 张${skipped ? `，跳过 ${skipped}` : ''}` : ''
  }
}

watch([mapWidth, mapHeight], async () => {
  await nextTick()
  map?.resize()
})

const STORAGE_KEY = 'maptool-synth-legend'
let persistReady = false
let persistTimer = 0

function snapshotConfig() {
  return {
    basemapText: basemapText.value,
    nwLng: nwLng.value,
    nwLat: nwLat.value,
    seLng: seLng.value,
    seLat: seLat.value,
    imageCount: imageCount.value,
    mapWidth: mapWidth.value,
    mapHeight: mapHeight.value,
    minZoom: minZoom.value,
    maxZoom: maxZoom.value,
    minFeatures: minFeatures.value,
    maxFeatures: maxFeatures.value,
    minLegend: minLegend.value,
    catalog: catalog.value.map((item) => ({
      name: item.name,
      shape: item.shape,
      color: item.color,
      description: item.description || '',
    })),
  }
}

function applyConfig(data: any) {
  if (!data || typeof data !== 'object') return
  if (typeof data.basemapText === 'string') basemapText.value = data.basemapText
  if (typeof data.nwLng === 'string') nwLng.value = data.nwLng
  if (typeof data.nwLat === 'string') nwLat.value = data.nwLat
  if (typeof data.seLng === 'string') seLng.value = data.seLng
  if (typeof data.seLat === 'string') seLat.value = data.seLat
  const nums: Array<[typeof imageCount, any]> = [
    [imageCount, data.imageCount],
    [mapWidth, data.mapWidth],
    [mapHeight, data.mapHeight],
    [minZoom, data.minZoom],
    [maxZoom, data.maxZoom],
    [minFeatures, data.minFeatures],
    [maxFeatures, data.maxFeatures],
    [minLegend, data.minLegend],
  ]
  nums.forEach(([target, value]) => {
    const n = Number(value)
    if (Number.isFinite(n)) target.value = n
  })
  if (Array.isArray(data.catalog) && data.catalog.length) {
    catalog.value = data.catalog.map((row: any) => ({
      name: String(row?.name || ''),
      shape: row?.shape === 'line' || row?.shape === 'polygon' ? row.shape : 'point',
      color: String(row?.color || ''),
      description: String(row?.description || ''),
    }))
  }
}

async function saveConfig(manual = false) {
  const data = snapshotConfig()
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    /* ignore */
  }
  configSaving.value = true
  try {
    await saveSynthLegendConfig(data)
    if (manual) ElMessage.success('配置已保存')
  } catch (err: any) {
    if (manual) ElMessage.error(typeof err === 'string' ? err : '配置保存失败')
  } finally {
    configSaving.value = false
  }
}

function scheduleSave() {
  if (!persistReady) return
  window.clearTimeout(persistTimer)
  persistTimer = window.setTimeout(() => {
    saveConfig(false)
  }, 700)
}

async function restoreConfig() {
  let data: any = null
  try {
    data = await getSynthLegendConfig()
  } catch {
    data = null
  }
  if (!data || !Object.keys(data).length) {
    try {
      data = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    } catch {
      data = {}
    }
  }
  applyConfig(data)
  persistReady = true
}

watch([mapWidth, mapHeight], async () => {
  await nextTick()
  map?.resize()
})

watch(
  [
    basemapText, nwLng, nwLat, seLng, seLat,
    imageCount, mapWidth, mapHeight, minZoom, maxZoom,
    minFeatures, maxFeatures, minLegend,
  ],
  scheduleSave,
)
watch(catalog, scheduleSave, { deep: true })

onMounted(async () => {
  createMap()
  loadIconSvgs()
  await restoreConfig()
})

onUnmounted(() => {
  previews.value.forEach((url) => URL.revokeObjectURL(url))
  map?.remove()
  map = null
})
</script>

<style scoped lang="less">
.synth-page {
  max-width: 1400px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint,
.form,
.toolbar,
.block-title {
  margin-bottom: 12px;
}
.row {
  display: flex;
  gap: 8px;
  width: 100%;
}
.row.wrap {
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 8px;
}
.block-title {
  font-weight: 600;
}
.apply-btn {
  margin-top: 8px;
}
.progress {
  margin-left: 12px;
  color: #666;
}
.preview-wrap {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.map-shell {
  border: 1px solid #e5e5e5;
  border-radius: 8px;
  overflow: hidden;
  flex: 0 0 auto;
}
.map {
  width: 100%;
  height: 100%;
}
.thumbs {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 640px;
  overflow: auto;
}
.thumb {
  width: 180px;
  border-radius: 4px;
  border: 1px solid #eee;
}
:deep(.mapboxgl-ctrl-logo),
:deep(.mapboxgl-ctrl-attrib) {
  display: none !important;
}
</style>
