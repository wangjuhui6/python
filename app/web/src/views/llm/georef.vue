<template>
  <el-card class="georef-page">
    <template #header>
      <div class="page-header">
        <span>地图配准</span>
        <el-tag type="success">自动对照点线面，不必填控制点</el-tag>
      </div>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      title="上传图片，填底图链接并把右侧视野调到大致同一带即可。点「自动对照」后，程序用底图截图与图片的点线面纹理匹配范围，再把底图要素叠到图片上校验。范围不准也可以，先缩放到接近再对照。"
    />

    <el-form label-width="92px" class="form">
      <el-form-item label="底图链接">
        <el-input
          v-model="basemapUrl"
          placeholder="style.json 或瓦片模板，例如 http://host/styles/blue/style.json 或 https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      </el-form-item>
      <el-form-item label="大致范围">
        <div class="bounds-row">
          <el-input v-model="swLng" placeholder="左下经度" />
          <el-input v-model="swLat" placeholder="左下纬度" />
          <el-input v-model="neLng" placeholder="右上经度" />
          <el-input v-model="neLat" placeholder="右上纬度" />
          <el-button type="primary" @click="applyApproxBounds(true)">定位底图</el-button>
          <el-button @click="fillFromView">用当前视野</el-button>
          <el-button @click="reloadBasemap">重载底图</el-button>
        </div>
      </el-form-item>
    </el-form>

    <div class="toolbar">
      <input ref="fileInput" class="file-input" type="file" accept="image/*" @change="onNativeFile" />
      <el-button @click="fileInput?.click()">上传图片</el-button>
      <el-button type="primary" :loading="matching" :disabled="!imageUrl" @click="autoAlign">自动对照</el-button>
      <el-switch v-model="showVectors" active-text="叠底图要素" />
      <el-button :disabled="!gcps.length" @click="undoPoint">撤销点</el-button>
      <el-button :disabled="!gcps.length" @click="clearPoints">清空点</el-button>
      <span class="toolbar-hint">{{ clickHint }}</span>
      <span class="spacer" />
      <span class="opacity-label">叠图透明度</span>
      <el-slider v-model="overlayOpacity" :min="0" :max="100" class="opacity-slider" />
    </div>

    <div class="workspace">
      <div class="pane">
        <div class="pane-title">图片 · 底图点线面会叠在上面用于校验</div>
        <div v-if="imageUrl" class="stage">
          <div class="stage-inner">
            <img ref="imgRef" :src="imageUrl" class="map-image" alt="地图" @click="onImageClick" @load="onImageLoad" />
            <svg
              v-if="showVectors && vectorPaths.length"
              class="vector-overlay"
              :viewBox="`0 0 ${natural.w} ${natural.h}`"
              preserveAspectRatio="xMidYMid meet"
              overflow="hidden"
            >
              <path
                v-for="(item, index) in vectorPaths"
                :key="'v-' + index"
                :d="item.d"
                :class="item.kind"
              ></path>
            </svg>
            <button
              v-for="(point, index) in gcps"
              :key="'gcp-' + index"
              class="mark"
              :class="{ active: index === activeIndex, pending: !hasLngLat(point) }"
              :style="markStyle(point)"
              type="button"
              @click.stop="activeIndex = index"
            >
              {{ index + 1 }}
            </button>
          </div>
        </div>
        <div v-else class="empty">上传一张带图例的地图图片</div>
      </div>
      <div class="pane">
        <div class="pane-title">底图 · 调到与图片接近的范围后点自动对照</div>
        <div ref="mapEl" class="map" />
        <div v-if="cursorLngLat" class="cursor">{{ cursorLngLat }}</div>
      </div>
    </div>

    <el-collapse class="side">
      <el-collapse-item title="手动控制点（对照不准时再改）" name="gcps">
      <div class="block-title">控制点 · {{ gcps.length }}</div>
      <el-table :data="gcps" size="small" max-height="280" highlight-current-row @current-change="onRow">
        <el-table-column label="#" width="44">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="图 X" width="72">
          <template #default="scope">{{ Math.round(scope.row.x) }}</template>
        </el-table-column>
        <el-table-column label="图 Y" width="72">
          <template #default="scope">{{ Math.round(scope.row.y) }}</template>
        </el-table-column>
        <el-table-column label="经度" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.lng" size="small" @focus="activeIndex = scope.$index" />
          </template>
        </el-table-column>
        <el-table-column label="纬度" min-width="120">
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
      <div v-if="fitError" class="error">{{ fitError }}</div>
      <div v-else-if="georef" class="meta">
        配准：{{ georef.kind === 'affine' ? '仿射（3 点及以上）' : '相似（2 点）' }}
        · {{ georef.count }} 点 · 平均残差 {{ georef.mean_error_m }} 米
        <template v-if="matchScore != null"> · 对照得分 {{ matchScore }}</template>
      </div>
      </el-collapse-item>
    </el-collapse>

    <div v-if="extent" class="result">
      <div class="block-title">图片对应经纬度范围</div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="左下（图）">
          {{ fmt(extent.corners.bottomLeft) }}
        </el-descriptions-item>
        <el-descriptions-item label="右上（图）">
          {{ fmt(extent.corners.topRight) }}
        </el-descriptions-item>
        <el-descriptions-item label="西 / 东">
          {{ fmtNum(extent.west) }} / {{ fmtNum(extent.east) }}
        </el-descriptions-item>
        <el-descriptions-item label="南 / 北">
          {{ fmtNum(extent.south) }} / {{ fmtNum(extent.north) }}
        </el-descriptions-item>
        <el-descriptions-item label="bbox" :span="2">
          [{{ fmtNum(extent.west) }}, {{ fmtNum(extent.south) }}, {{ fmtNum(extent.east) }}, {{ fmtNum(extent.north) }}]
        </el-descriptions-item>
      </el-descriptions>
      <el-button class="copy-btn" @click="copyBbox">复制 bbox</el-button>
      <el-button class="copy-btn" @click="copyJson">复制完整 JSON</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { fitTransform, imageExtent, invertAffine, lngLatToPixel, roundLngLat, type FitResult, type ImageExtent } from './lib/georefFit'
import { autoGeoref } from '@/api/llm'

type GcpRow = { x: number; y: number; lng: string; lat: string }

mapboxgl.baseApiUrl = ''

const fileInput = ref<HTMLInputElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const mapEl = ref<HTMLDivElement | null>(null)
const imageUrl = ref('')
const natural = ref({ w: 1, h: 1 })
const gcps = ref<GcpRow[]>([])
const activeIndex = ref(-1)
const overlayOpacity = ref(45)
const basemapUrl = ref('')
const swLng = ref('')
const swLat = ref('')
const neLng = ref('')
const neLat = ref('')
const cursorLngLat = ref('')
const matching = ref(false)
const showVectors = ref(false)
const matchScore = ref<number | null>(null)
const vectorPaths = ref<Array<{ d: string; kind: string }>>([])
const fitError = ref('')
const georef = ref<FitResult | null>(null)
const extent = ref<ImageExtent | null>(null)

let map: mapboxgl.Map | null = null
let mapClickHandler: ((e: mapboxgl.MapMouseEvent) => void) | null = null
let mapMoveHandler: ((e: mapboxgl.MapMouseEvent) => void) | null = null

const clickHint = computed(() => {
  if (!imageUrl.value) return '先上传图片并加载底图'
  if (matching.value) return '正在对照点线面…'
  if (extent.value) return '看左图叠线是否贴合道路/边界；不齐就微调底图后再对照'
  return '把右侧底图缩放到与图片接近的范围，然后点自动对照'
})

function hasLngLat(point: GcpRow) {
  return point.lng !== '' && point.lat !== '' && !Number.isNaN(Number(point.lng)) && !Number.isNaN(Number(point.lat))
}

function fmtNum(n: number) {
  return Number(n.toFixed(6))
}

function fmt(pair: [number, number]) {
  const [lng, lat] = roundLngLat(pair)
  return `${lng}, ${lat}`
}

function parseNum(value: string) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function setImage(file: File) {
  if (imageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(imageUrl.value)
  }
  imageUrl.value = URL.createObjectURL(file)
  gcps.value = []
  activeIndex.value = -1
  georef.value = null
  extent.value = null
  fitError.value = ''
  matchScore.value = null
  vectorPaths.value = []
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
  recompute()
  updateOverlay()
}

function onImageClick(event: MouseEvent) {
  const img = imgRef.value
  if (!img) return
  const rect = img.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * natural.value.w
  const y = ((event.clientY - rect.top) / rect.height) * natural.value.h
  gcps.value.push({ x, y, lng: '', lat: '' })
  activeIndex.value = gcps.value.length - 1
}

function markStyle(point: { x: number; y: number }) {
  return {
    left: `${(point.x / natural.value.w) * 100}%`,
    top: `${(point.y / natural.value.h) * 100}%`,
  }
}

function onRow(row: GcpRow) {
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

function readyGcps() {
  return gcps.value
    .filter(hasLngLat)
    .map((item) => ({
      x: item.x,
      y: item.y,
      lng: Number(item.lng),
      lat: Number(item.lat),
    }))
}

function recompute() {
  const points = readyGcps()
  if (points.length < 2) {
    georef.value = null
    extent.value = null
    fitError.value = ''
    vectorPaths.value = []
    return
  }
  try {
    const fitted = fitTransform(points)
    georef.value = fitted
    extent.value = imageExtent(natural.value.w, natural.value.h, fitted.matrix)
    fitError.value = ''
    refreshVectorOverlay()
  } catch (err: any) {
    georef.value = null
    extent.value = null
    fitError.value = typeof err?.message === 'string' ? err.message : '拟合失败'
  }
}

function waitMapIdle() {
  return new Promise<void>((resolve) => {
    if (!map) {
      resolve()
      return
    }
    let done = false
    const finish = () => {
      if (done) return
      done = true
      resolve()
    }
    map.once('idle', finish)
    window.setTimeout(finish, 5000)
    map.triggerRepaint()
  })
}

function canvasToBlob(canvas: HTMLCanvasElement) {
  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob)
      else reject(new Error('无法截取底图'))
    }, 'image/png')
  })
}

async function captureMapCss() {
  if (!map) throw new Error('底图未加载')
  const src = map.getCanvas()
  const w = Math.max(1, Math.round(src.clientWidth || src.width))
  const h = Math.max(1, Math.round(src.clientHeight || src.height))
  const out = document.createElement('canvas')
  out.width = w
  out.height = h
  const ctx = out.getContext('2d')
  if (!ctx) throw new Error('无法截取底图')
  ctx.drawImage(src, 0, 0, w, h)
  return { blob: await canvasToBlob(out), width: w, height: h }
}

async function autoAlign() {
  if (!map || !imageUrl.value) return
  matching.value = true
  showVectors.value = false
  try {
    if (map.getLayer('overlay-image')) {
      map.setLayoutProperty('overlay-image', 'visibility', 'none')
    }
    await waitMapIdle()
    const bounds = map.getBounds()
    if (!bounds) return
    const shot = await captureMapCss()
    const photoBlob = await fetch(imageUrl.value).then((res) => res.blob())
    const form = new FormData()
    form.append('file', photoBlob, 'map.png')
    form.append('canvas', shot.blob, 'canvas.png')
    form.append('west', String(bounds.getWest()))
    form.append('south', String(bounds.getSouth()))
    form.append('east', String(bounds.getEast()))
    form.append('north', String(bounds.getNorth()))
    const data = await autoGeoref(form)
    const rows = (data?.gcps || data?.pairs || []).map((item: any) => {
      const cx = Number(item.canvas_x)
      const cy = Number(item.canvas_y)
      let lng = Number(item.lng)
      let lat = Number(item.lat)
      if (Number.isFinite(cx) && Number.isFinite(cy) && map) {
        const ll = map.unproject([cx, cy])
        lng = ll.lng
        lat = ll.lat
      }
      return {
        x: item.x,
        y: item.y,
        lng: String(lng),
        lat: String(lat),
      }
    })
    gcps.value = rows
    matchScore.value = data?.score ?? null
    await nextTick()
    if (extent.value) {
      map.fitBounds(
        [
          [extent.value.west, extent.value.south],
          [extent.value.east, extent.value.north],
        ],
        { padding: 24, duration: 600 },
      )
    }
    ElMessage.success(`对照完成，得分 ${data?.score ?? '-'}。请看右侧半透明叠图是否对齐道路。`)
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : err?.message || '自动对照失败')
  } finally {
    matching.value = false
    updateOverlay()
  }
}

function refreshVectorOverlay() {
  vectorPaths.value = []
  if (!map || !georef.value) return
  let inv: number[][]
  try {
    inv = invertAffine(georef.value.matrix)
  } catch {
    return
  }
  const skip = new Set(['overlay-image', 'extent-line', 'gcps-circle'])
  const features = map.queryRenderedFeatures().filter((f) => f.layer?.id && !skip.has(f.layer.id))
  const paths: Array<{ d: string; kind: string }> = []
  for (const feat of features.slice(0, 180)) {
    const geom = feat.geometry as any
    if (!geom) continue
    const kind = String(geom.type || '').includes('Polygon') ? 'polygon' : String(geom.type || '').includes('Line') ? 'line' : 'point'
    const d = geometryToPath(geom, inv)
    if (d) paths.push({ d, kind })
    if (paths.length >= 220) break
  }
  vectorPaths.value = paths
}

function geometryToPath(geom: any, inv: number[][]) {
  if (geom.type === 'Point') {
    const [x, y] = lngLatToPixel(inv, geom.coordinates[0], geom.coordinates[1])
    if (!inImage(x, y)) return ''
    return `M ${x} ${y} l 4 0 l 0 4 l -4 0 z`
  }
  if (geom.type === 'MultiPoint') {
    return geom.coordinates.map((pt: number[]) => {
      const [x, y] = lngLatToPixel(inv, pt[0], pt[1])
      if (!inImage(x, y)) return ''
      return `M ${x} ${y} l 4 0 l 0 4 l -4 0 z`
    }).filter(Boolean).join(' ')
  }
  if (geom.type === 'LineString') {
    return lineToPath(geom.coordinates, inv)
  }
  if (geom.type === 'MultiLineString') {
    return geom.coordinates.map((line: number[][]) => lineToPath(line, inv)).filter(Boolean).join(' ')
  }
  if (geom.type === 'Polygon') {
    return geom.coordinates.map((ring: number[][]) => lineToPath(ring, inv)).filter(Boolean).join(' ')
  }
  if (geom.type === 'MultiPolygon') {
    return geom.coordinates.flat().map((ring: number[][]) => lineToPath(ring, inv)).filter(Boolean).join(' ')
  }
  return ''
}

function inImage(x: number, y: number) {
  const w = natural.value.w
  const h = natural.value.h
  return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && y >= 0 && x <= w && y <= h
}

function lineToPath(coords: number[][], inv: number[][]) {
  if (!coords.length) return ''
  const w = natural.value.w
  const h = natural.value.h
  const pad = Math.max(w, h) * 0.05
  const pts: Array<[number, number]> = []
  for (let i = 0; i < coords.length; i++) {
    if (i !== 0 && i !== coords.length - 1 && i % 3 !== 0) continue
    const [x, y] = lngLatToPixel(inv, coords[i][0], coords[i][1])
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue
    if (x < -pad || y < -pad || x > w + pad || y > h + pad) continue
    pts.push([x, y])
    if (pts.length >= 80) break
  }
  if (pts.length < 2) return ''
  return pts.map((pt, i) => `${i === 0 ? 'M' : 'L'} ${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`).join(' ')
}

function isTileTemplate(url: string) {
  return /\{z\}/i.test(url) && /\{x\}/i.test(url) && /\{y\}/i.test(url)
}

function styleSpec() {
  const url = basemapUrl.value.trim()
  if (!url) {
    return {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e8eef5' } }],
    }
  }
  if (isTileTemplate(url)) {
    return {
      version: 8,
      sources: {
        basemap: { type: 'raster', tiles: [url], tileSize: 256 },
      },
      layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': '#e8eef5' } },
        { id: 'basemap', type: 'raster', source: 'basemap' },
      ],
    }
  }
  return url
}

function destroyMap() {
  if (!map) return
  if (mapClickHandler) map.off('click', mapClickHandler)
  if (mapMoveHandler) map.off('mousemove', mapMoveHandler)
  map.remove()
  map = null
}

function createMap() {
  if (!mapEl.value) return
  destroyMap()
  map = new mapboxgl.Map({
    container: mapEl.value,
    style: styleSpec() as any,
    center: [116.342, 39.933],
    zoom: 8,
    attributionControl: false,
    preserveDrawingBuffer: true,
    pitch: 0,
    bearing: 0,
    projection: 'mercator',
  })
  map.addControl(new mapboxgl.NavigationControl(), 'top-right')
  mapClickHandler = (e) => {
    const lng = Number(e.lngLat.lng.toFixed(8))
    const lat = Number(e.lngLat.lat.toFixed(8))
    let index = gcps.value.findIndex((item) => !hasLngLat(item))
    if (index < 0) index = activeIndex.value
    if (index < 0 || index >= gcps.value.length) {
      ElMessage.warning('请先在左侧图片上点一个位置')
      return
    }
    gcps.value[index].lng = String(lng)
    gcps.value[index].lat = String(lat)
    activeIndex.value = index
  }
  mapMoveHandler = (e) => {
    cursorLngLat.value = `${e.lngLat.lng.toFixed(6)}, ${e.lngLat.lat.toFixed(6)}`
  }
  map.on('click', mapClickHandler)
  map.on('mousemove', mapMoveHandler)
  map.on('load', () => {
    map?.resize()
    applyApproxBounds(false)
    syncMapMarkers()
    updateOverlay()
  })
}

function applyApproxBounds(alertOnFail = true) {
  const west = parseNum(swLng.value)
  const south = parseNum(swLat.value)
  const east = parseNum(neLng.value)
  const north = parseNum(neLat.value)
  if (west == null || south == null || east == null || north == null) {
    if (alertOnFail) ElMessage.warning('请填写完整的左下、右上经纬度')
    return
  }
  if (!map) return
  map.fitBounds(
    [
      [west, south],
      [east, north],
    ],
    { padding: 36, duration: 600 },
  )
}

function fillFromView() {
  if (!map) return
  const b = map.getBounds()
  if (!b) return
  swLng.value = b.getWest().toFixed(6)
  swLat.value = b.getSouth().toFixed(6)
  neLng.value = b.getEast().toFixed(6)
  neLat.value = b.getNorth().toFixed(6)
}

function reloadBasemap() {
  createMap()
}

function syncMapMarkers() {
  if (!map?.isStyleLoaded()) return
  if (!map.getSource('gcps')) {
    map.addSource('gcps', { type: 'geojson', data: emptyFc() })
    map.addLayer({
      id: 'gcps-circle',
      type: 'circle',
      source: 'gcps',
      paint: {
        'circle-radius': 7,
        'circle-color': '#409eff',
        'circle-stroke-width': 2,
        'circle-stroke-color': '#fff',
      },
    })
  }
  const features = gcps.value
    .filter(hasLngLat)
    .map((item, index) => ({
      type: 'Feature' as const,
      properties: { n: index + 1 },
      geometry: {
        type: 'Point' as const,
        coordinates: [Number(item.lng), Number(item.lat)],
      },
    }))
  const source = map.getSource('gcps') as mapboxgl.GeoJSONSource
  source.setData({ type: 'FeatureCollection', features })
}

function emptyFc() {
  return { type: 'FeatureCollection' as const, features: [] }
}

function overlayCoordinates(): [[number, number], [number, number], [number, number], [number, number]] | null {
  if (!extent.value) return null
  const { topLeft, topRight, bottomRight, bottomLeft } = extent.value.corners
  return [topLeft, topRight, bottomRight, bottomLeft]
}

function ensureExtentLayer() {
  if (!map?.isStyleLoaded()) return
  if (!map.getSource('extent')) {
    map.addSource('extent', { type: 'geojson', data: emptyFc() })
    map.addLayer({
      id: 'extent-line',
      type: 'line',
      source: 'extent',
      paint: { 'line-color': '#e6a23c', 'line-width': 2, 'line-dasharray': [2, 1] },
    })
  }
}

function updateOverlay() {
  if (!map?.isStyleLoaded()) return
  ensureExtentLayer()
  const coords = overlayCoordinates()
  if (imageUrl.value && coords) {
    if (map.getSource('overlay')) {
      const source = map.getSource('overlay') as mapboxgl.ImageSource
      source.updateImage({ url: imageUrl.value, coordinates: coords })
    } else {
      map.addSource('overlay', {
        type: 'image',
        url: imageUrl.value,
        coordinates: coords,
      })
      map.addLayer({
        id: 'overlay-image',
        type: 'raster',
        source: 'overlay',
        paint: { 'raster-opacity': overlayOpacity.value / 100 },
      })
    }
    if (map.getLayer('overlay-image')) {
      map.setLayoutProperty('overlay-image', 'visibility', 'visible')
      map.setPaintProperty('overlay-image', 'raster-opacity', overlayOpacity.value / 100)
    }
  } else if (map.getLayer('overlay-image')) {
    map.setLayoutProperty('overlay-image', 'visibility', 'none')
  }
  const extentSource = map.getSource('extent') as mapboxgl.GeoJSONSource | undefined
  if (extentSource && coords) {
    const ring = [...coords, coords[0]]
    extentSource.setData({
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          properties: {},
          geometry: { type: 'Polygon', coordinates: [ring] },
        },
      ],
    })
  } else if (extentSource) {
    extentSource.setData(emptyFc())
  }
}

async function copyBbox() {
  if (!extent.value) return
  const text = JSON.stringify(extent.value.bbox.map((n) => Number(n.toFixed(6))))
  await navigator.clipboard.writeText(text)
  ElMessage.success('已复制 bbox')
}

async function copyJson() {
  if (!extent.value || !georef.value) return
  const payload = {
    bbox: extent.value.bbox.map((n) => Number(n.toFixed(6))),
    corners: {
      bottomLeft: roundLngLat(extent.value.corners.bottomLeft),
      topRight: roundLngLat(extent.value.corners.topRight),
      topLeft: roundLngLat(extent.value.corners.topLeft),
      bottomRight: roundLngLat(extent.value.corners.bottomRight),
    },
    west: fmtNum(extent.value.west),
    south: fmtNum(extent.value.south),
    east: fmtNum(extent.value.east),
    north: fmtNum(extent.value.north),
    width: extent.value.width,
    height: extent.value.height,
    georef: {
      kind: georef.value.kind,
      count: georef.value.count,
      mean_error_m: georef.value.mean_error_m,
    },
  }
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
  ElMessage.success('已复制 JSON')
}

watch(gcps, () => {
  recompute()
  syncMapMarkers()
  updateOverlay()
}, { deep: true })

watch(showVectors, () => refreshVectorOverlay())

onMounted(async () => {
  await nextTick()
  createMap()
})

onBeforeUnmount(() => {
  destroyMap()
  if (imageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(imageUrl.value)
  }
})
</script>

<style scoped lang="less">
.georef-page {
  max-width: 1400px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint,
.form {
  margin-bottom: 12px;
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
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-hint {
  color: #606266;
  font-size: 13px;
}
.spacer {
  flex: 1;
}
.opacity-label {
  font-size: 12px;
  color: #909399;
}
.opacity-slider {
  width: 140px;
}
.workspace {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 420px;
}
.pane-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.stage {
  border: 1px solid #ebeef5;
  background: #f5f7fa;
  overflow: hidden;
  max-height: 560px;
}
.stage-inner {
  position: relative;
  width: 100%;
  overflow: hidden;
}
.vector-overlay {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
}
.vector-overlay .line {
  fill: none;
  stroke: #f56c6c;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.vector-overlay .polygon {
  fill: rgba(230, 162, 60, 0.18);
  stroke: #e6a23c;
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}
.vector-overlay .point {
  fill: #409eff;
  stroke: #fff;
  stroke-width: 1;
}
.map-image {
  display: block;
  width: 100%;
  height: auto;
  cursor: crosshair;
}
.map {
  height: 520px;
  border: 1px solid #ebeef5;
}
.cursor {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.file-input {
  display: none;
}
.mark {
  position: absolute;
  transform: translate(-50%, -50%);
  width: 22px;
  height: 22px;
  border: 2px solid #fff;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  line-height: 18px;
  padding: 0;
  cursor: pointer;
}
.mark.active {
  background: #e6a23c;
}
.mark.pending {
  background: #f56c6c;
}
.empty {
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  border: 1px dashed #dcdfe6;
}
.side {
  margin-top: 16px;
}
.block-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.meta {
  margin-top: 8px;
  color: #606266;
  font-size: 13px;
}
.error {
  margin-top: 8px;
  color: #f56c6c;
  font-size: 13px;
}
.result {
  margin-top: 20px;
}
.copy-btn {
  margin-top: 8px;
  margin-right: 8px;
}
@media (max-width: 960px) {
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
