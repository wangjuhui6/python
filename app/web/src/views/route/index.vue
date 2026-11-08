<template>
  <div class="route-page">
    <aside class="panel">
      <div class="panel-title">路线规划</div>
      <div class="hint">底图只负责显示。路网文件用来计算路线，在地图上单击右键设置起点、终点和途径点。橙色途径点可以拖动调整。</div>
      <el-form label-position="top">
        <el-form-item label="底图地址">
          <el-input
            v-model="basemap"
            placeholder="瓦片地址，需包含 {z}/{x}/{y}，或样式地址"
            clearable
          />
        </el-form-item>
        <el-form-item label="路网文件">
          <div class="file-row">
            <el-input v-model="pbfPath" placeholder="选择 .pbf 或 .osm 文件" />
            <el-button @click="pickFile">选择</el-button>
          </div>
        </el-form-item>
        <el-form-item label="高程">
          <el-button :type="elevation ? 'primary' : 'default'" :disabled="phase === 'starting'" @click="elevation = !elevation">
            {{ elevation ? '已开启' : '已关闭' }}
          </el-button>
          <span class="elev-note">{{ elevation ? '第一次建图需要联网' : '只用本地路网' }}</span>
        </el-form-item>
        <el-form-item label="出行方式">
          <el-radio-group v-model="profile">
            <el-radio-button v-for="item in profiles" :key="item.id" :value="item.id">
              {{ item.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <div class="actions">
        <el-button @click="applyBasemap">应用底图</el-button>
        <el-button type="primary" :loading="phase === 'starting'" @click="onStart">启动服务</el-button>
        <el-button :disabled="phase === 'stopped'" @click="onStop">停止</el-button>
      </div>
      <div class="status" :class="phase">{{ statusText }}</div>
      <div v-if="summary" class="summary">
        <span>{{ summary.distance }}</span>
        <span>{{ summary.time }}</span>
      </div>
      <el-button class="export" :disabled="!geojson" @click="exportGeoJSON">导出 GeoJSON</el-button>
      <div class="stops">
        <div class="stops-head">
          <span>点位</span>
          <el-button link type="danger" :disabled="!stops.length" @click="clearStops">清空</el-button>
        </div>
        <div v-if="!stops.length" class="empty">还没有点。在地图上右键添加。</div>
        <div v-for="(item, index) in orderedStops" :key="index" class="stop-row">
          <span class="badge" :class="item.role">{{ roleText(item.role) }}</span>
          <span class="coord">{{ item.lng.toFixed(5) }}, {{ item.lat.toFixed(5) }}</span>
          <el-button link type="danger" @click="removeStop(item)">删除</el-button>
        </div>
      </div>
      <div class="steps">
        <div class="stops-head"><span>路线说明</span></div>
        <div v-if="!instructions.length" class="empty">算出路线后会显示在这里</div>
        <div v-for="(item, index) in instructions" :key="index" class="step">
          <span class="step-no">{{ index + 1 }}</span>
          <span class="step-text">{{ item.text }}</span>
          <span class="step-dist">{{ formatDistance(item.distance) }}</span>
        </div>
      </div>
      <el-collapse v-if="phase === 'failed' && logs.length" class="fail-log">
        <el-collapse-item title="启动详情">
          <pre>{{ logs.join('\n') }}</pre>
        </el-collapse-item>
      </el-collapse>
    </aside>
    <div class="map-wrap">
      <div ref="mapEl" class="map"></div>
      <div v-if="menu.show" class="menu" :style="{ left: menu.x + 'px', top: menu.y + 'px' }" @mousedown.stop @click.stop @contextmenu.prevent>
        <button type="button" @click="choose('start')">设为起点</button>
        <button type="button" @click="choose('end')">设为终点</button>
        <button type="button" @click="choose('via')">添加途径点</button>
      </div>
      <div v-if="showOsmNote" class="attrib">© OpenStreetMap</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { ElMessage } from 'element-plus'
import { selectFile } from '@/api/file'
import {
  getRouteDefaults,
  getRouteStatus,
  downloadGeoJSON,
  planRoute,
  startRoute,
  stopRoute,
  type RouteGeoJSON,
  type RouteInstruction,
  type RouteProfile,
} from '@/api/route'

mapboxgl.baseApiUrl = ''

type Role = 'start' | 'end' | 'via'
interface Stop {
  role: Role
  lng: number
  lat: number
}

const basemap = ref('https://tile.openstreetmap.org/{z}/{x}/{y}.png')
const pbfPath = ref('')
const profile = ref('car')
const profiles = ref<RouteProfile[]>([
  { id: 'car', label: '驾车' },
  { id: 'foot', label: '步行' },
  { id: 'bike', label: '骑行' },
])
const phase = ref<'stopped' | 'starting' | 'ready' | 'failed'>('stopped')
const elevation = ref(false)
const statusText = ref('尚未启动')
const logs = ref<string[]>([])
const stops = ref<Stop[]>([])
const instructions = ref<RouteInstruction[]>([])
const summary = ref<{ distance: string; time: string } | null>(null)
const geojson = ref<RouteGeoJSON | null>(null)
const menu = ref({ show: false, x: 0, y: 0, lng: 0, lat: 0 })
const mapEl = ref<HTMLDivElement | null>(null)

let map: mapboxgl.Map | null = null
let markers: mapboxgl.Marker[] = []
let pollTimer = 0
let planTimer = 0
let planTicket = 0
let keepView = false
let lineCoords: number[][] = []

const orderedStops = computed(() => {
  const start = stops.value.filter((item) => item.role === 'start')
  const via = stops.value.filter((item) => item.role === 'via')
  const end = stops.value.filter((item) => item.role === 'end')
  return [...start, ...via, ...end]
})

const showOsmNote = computed(() => basemap.value.toLowerCase().includes('openstreetmap'))

function roleText(role: Role) {
  if (role === 'start') return '起'
  if (role === 'end') return '终'
  return '途'
}

function formatDistance(meters: number) {
  if (meters < 1000) return `${Math.round(meters)} 米`
  return `${(meters / 1000).toFixed(1)} 公里`
}

function formatDuration(ms: number) {
  const minutes = Math.max(1, Math.round(ms / 60000))
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  return `${hours} 小时 ${minutes % 60} 分钟`
}

function errorText(err: unknown, fallback: string) {
  if (typeof err === 'string' && err) return err
  if (err instanceof Error && err.message) return err.message
  return fallback
}

function isTileTemplate(url: string) {
  return /\{z\}/i.test(url) && /\{x\}/i.test(url) && /\{y\}/i.test(url)
}

function styleSpec() {
  const url = basemap.value.trim()
  if (!url) {
    return {
      version: 8,
      sources: {},
      layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#e7e2d6' } }],
    }
  }
  if (isTileTemplate(url)) {
    return {
      version: 8,
      sources: {
        basemap: { type: 'raster', tiles: [url], tileSize: 256 },
      },
      layers: [
        { id: 'bg', type: 'background', paint: { 'background-color': '#e7e2d6' } },
        { id: 'basemap', type: 'raster', source: 'basemap' },
      ],
    }
  }
  return url
}

function lineFeature() {
  return {
    type: 'Feature' as const,
    properties: {},
    geometry: { type: 'LineString' as const, coordinates: lineCoords },
  }
}

function ensureRouteLayer() {
  if (!map || !map.isStyleLoaded()) return
  if (!map.getSource('route')) {
    map.addSource('route', { type: 'geojson', data: lineFeature() })
    map.addLayer({
      id: 'route-casing',
      type: 'line',
      source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#1e3a8a', 'line-width': 8 },
    })
    map.addLayer({
      id: 'route-line',
      type: 'line',
      source: 'route',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#3b82f6', 'line-width': 4 },
    })
    return
  }
  ;(map.getSource('route') as mapboxgl.GeoJSONSource).setData(lineFeature())
}

function pinElement(role: Role) {
  const el = document.createElement('div')
  const color = role === 'start' ? '#16a34a' : role === 'end' ? '#dc2626' : '#d97706'
  el.textContent = roleText(role)
  if (role === 'via') {
    el.setAttribute('role', 'button')
    el.setAttribute('aria-label', '途径点，可拖动')
  }
  el.style.cssText = [
    'width:26px',
    'height:26px',
    'border-radius:50%',
    `background:${color}`,
    'color:#fff',
    'font-size:12px',
    'font-weight:700',
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'border:2px solid #fff',
    'box-shadow:0 1px 4px rgba(0,0,0,.35)',
    role === 'via' ? 'cursor:grab;touch-action:none' : '',
  ].filter(Boolean).join(';')
  return el
}

function drawMarkers() {
  markers.forEach((item) => item.remove())
  markers = []
  if (!map) return
  orderedStops.value.forEach((item) => {
    const marker = new mapboxgl.Marker({
      element: pinElement(item.role),
      anchor: 'center',
      draggable: item.role === 'via',
    })
      .setLngLat([item.lng, item.lat])
      .addTo(map as mapboxgl.Map)
    if (item.role === 'via') {
      marker.on('dragend', () => {
        const lngLat = marker.getLngLat()
        keepView = true
        item.lng = lngLat.lng
        item.lat = lngLat.lat
      })
    }
    markers.push(marker)
  })
}

function applyBasemap() {
  if (!map) return
  menu.value.show = false
  map.setStyle(styleSpec() as mapboxgl.StyleSpecification)
  map.once('style.load', () => {
    ensureRouteLayer()
    drawMarkers()
  })
}

function createMap() {
  if (!mapEl.value || map) return
  map = new mapboxgl.Map({
    container: mapEl.value,
    style: styleSpec() as mapboxgl.StyleSpecification,
    center: pbfPath.value ? [113.26, 23.13] : [104.2, 35.6],
    zoom: pbfPath.value ? 11 : 4,
    attributionControl: false,
    projection: 'mercator',
  })
  map.addControl(new mapboxgl.NavigationControl(), 'top-right')
  map.on('load', () => {
    map?.resize()
    ensureRouteLayer()
    drawMarkers()
  })
  map.on('contextmenu', (event) => {
    event.preventDefault()
    const width = mapEl.value?.clientWidth || 0
    const height = mapEl.value?.clientHeight || 0
    menu.value = {
      show: true,
      x: Math.max(8, Math.min(event.point.x, width - 148)),
      y: Math.max(8, Math.min(event.point.y, height - 120)),
      lng: event.lngLat.lng,
      lat: event.lngLat.lat,
    }
  })
  map.on('click', () => {
    menu.value.show = false
  })
}

function applyStatus(data: { phase: typeof phase.value; message: string; pbf: string; elevation?: boolean; log?: string[] }) {
  phase.value = data.phase
  statusText.value = data.message || '尚未启动'
  logs.value = data.log || []
  if (data.pbf && !pbfPath.value) pbfPath.value = data.pbf
  if ((data.phase === 'ready' || data.phase === 'starting') && typeof data.elevation === 'boolean') {
    elevation.value = data.elevation
  }
}

async function refreshStatus() {
  try {
    const data = await getRouteStatus()
    applyStatus(data)
    if (data.phase === 'starting') beginPoll()
  } catch {
    statusText.value = '无法连接路线服务'
  }
}

function beginPoll() {
  window.clearInterval(pollTimer)
  pollTimer = window.setInterval(async () => {
    try {
      const data = await getRouteStatus()
      applyStatus(data)
      if (data.phase !== 'starting') window.clearInterval(pollTimer)
      if (data.phase === 'ready') schedulePlan()
    } catch {
      window.clearInterval(pollTimer)
    }
  }, 2000)
}

async function pickFile() {
  try {
    const path = await selectFile({ filetypes: [['路网文件', '*.pbf *.osm'], ['所有文件', '*.*']] })
    if (path) pbfPath.value = path
  } catch {
    // 取消选择时接口会返回非成功状态
  }
}

async function onStart() {
  applyBasemap()
  if (!pbfPath.value.trim()) {
    ElMessage.warning('请先选择路网文件')
    return
  }
  try {
    const data = await startRoute(pbfPath.value.trim(), elevation.value)
    applyStatus(data)
    if (data.phase === 'starting') beginPoll()
    if (data.phase === 'ready') schedulePlan()
  } catch (err) {
    ElMessage.error(errorText(err, '启动失败'))
  }
}

async function onStop() {
  try {
    const data = await stopRoute()
    applyStatus(data)
    window.clearInterval(pollTimer)
  } catch (err) {
    ElMessage.error(errorText(err, '停止失败'))
  }
}

function choose(role: Role) {
  const lng = menu.value.lng
  const lat = menu.value.lat
  menu.value.show = false
  if (role === 'start') {
    const index = stops.value.findIndex((item) => item.role === 'start')
    const next = { role, lng, lat }
    if (index >= 0) stops.value.splice(index, 1, next)
    else stops.value.unshift(next)
    return
  }
  if (role === 'end') {
    const index = stops.value.findIndex((item) => item.role === 'end')
    const next = { role, lng, lat }
    if (index >= 0) stops.value.splice(index, 1, next)
    else stops.value.push(next)
    return
  }
  const endIndex = stops.value.findIndex((item) => item.role === 'end')
  const next = { role: 'via' as Role, lng, lat }
  if (endIndex >= 0) stops.value.splice(endIndex, 0, next)
  else stops.value.push(next)
}

function removeStop(item: Stop) {
  const index = stops.value.indexOf(item)
  if (index >= 0) stops.value.splice(index, 1)
}

function clearStops() {
  stops.value = []
}

function clearRoute() {
  lineCoords = []
  instructions.value = []
  summary.value = null
  geojson.value = null
  ensureRouteLayer()
}

function exportGeoJSON() {
  if (!geojson.value) return
  downloadGeoJSON(geojson.value)
}

function schedulePlan() {
  window.clearTimeout(planTimer)
  planTimer = window.setTimeout(runPlan, 350)
}

async function runPlan() {
  const points = orderedStops.value
  const start = points.find((item) => item.role === 'start')
  const end = points.find((item) => item.role === 'end')
  if (!start || !end) {
    clearRoute()
    return
  }
  if (phase.value !== 'ready') {
    clearRoute()
    return
  }
  const ticket = ++planTicket
  try {
    const data = await planRoute(
      profile.value,
      points.map((item) => [item.lng, item.lat]),
    )
    if (ticket !== planTicket) return
    lineCoords = data.coordinates
    instructions.value = data.instructions
    geojson.value = data.geojson
    summary.value = {
      distance: formatDistance(data.distance),
      time: formatDuration(data.time),
    }
    ensureRouteLayer()
    const fit = !keepView
    keepView = false
    if (fit && map && lineCoords.length > 1) {
      const lngs = lineCoords.map((item) => item[0])
      const lats = lineCoords.map((item) => item[1])
      map.fitBounds(
        [
          [Math.min(...lngs), Math.min(...lats)],
          [Math.max(...lngs), Math.max(...lats)],
        ],
        { padding: 64, maxZoom: 15, duration: 500 },
      )
    }
  } catch (err) {
    if (ticket !== planTicket) return
    clearRoute()
    ElMessage.error(errorText(err, '没有算出路线'))
  }
}

watch(profile, () => schedulePlan())
watch(stops, () => {
  drawMarkers()
  schedulePlan()
}, { deep: true })

onMounted(async () => {
  try {
    const data = await getRouteDefaults()
    if (data.basemap) basemap.value = data.basemap
    if (data.pbf_path) pbfPath.value = data.pbf_path
    if (data.profiles?.length) profiles.value = data.profiles
  } catch {
    // 使用页面上的默认底图
  }
  createMap()
  refreshStatus()
})

onBeforeUnmount(() => {
  window.clearInterval(pollTimer)
  window.clearTimeout(planTimer)
  markers.forEach((item) => item.remove())
  map?.remove()
  map = null
})
</script>

<style scoped lang="less">
.route-page {
  height: calc(100vh - 64px - 80px - 48px);
  display: flex;
  gap: 12px;
}
.panel {
  width: 340px;
  flex: 0 0 340px;
  overflow: auto;
  background: #fff;
  border: 1px solid #ece7df;
  border-radius: 8px;
  padding: 14px;
  box-sizing: border-box;
}
.panel-title {
  font-size: 16px;
  font-weight: 650;
  margin-bottom: 8px;
}
.hint {
  color: #666;
  font-size: 12px;
  line-height: 1.5;
  margin-bottom: 12px;
}
.file-row {
  display: flex;
  gap: 8px;
  width: 100%;
  :deep(.el-input) {
    flex: 1;
  }
}
.elev-note {
  margin-left: 8px;
  color: #888;
  font-size: 12px;
}
.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.status {
  font-size: 13px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f6f6f6;
  margin-bottom: 10px;
}
.status.ready {
  background: #ecfdf3;
  color: #166534;
}
.status.starting {
  background: #fff7ed;
  color: #9a3412;
}
.status.failed {
  background: #fef2f2;
  color: #991b1b;
}
.summary {
  display: flex;
  gap: 16px;
  font-size: 18px;
  font-weight: 650;
  margin-bottom: 10px;
}
.export {
  margin-bottom: 10px;
}
.stops-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  margin: 8px 0;
}
.empty {
  color: #999;
  font-size: 12px;
  margin-bottom: 8px;
}
.stop-row,
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
}
.coord,
.step-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge,
.step-no {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}
.badge.start,
.step-no {
  background: #16a34a;
}
.badge.end {
  background: #dc2626;
}
.badge.via {
  background: #d97706;
}
.step-no {
  background: #2563eb;
  font-size: 11px;
}
.step-dist {
  color: #666;
  flex: 0 0 auto;
}
.steps {
  max-height: 240px;
  overflow: auto;
}
.fail-log pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 11px;
  margin: 0;
}
.map-wrap {
  position: relative;
  flex: 1;
  min-width: 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ece7df;
}
.map {
  width: 100%;
  height: 100%;
}
.menu {
  position: absolute;
  z-index: 5;
  width: 132px;
  background: #fff;
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  padding: 4px;
  display: flex;
  flex-direction: column;
}
.menu button {
  border: 0;
  background: transparent;
  text-align: left;
  padding: 8px 10px;
  border-radius: 4px;
  cursor: pointer;
}
.menu button:hover {
  background: #f3f4f6;
}
.attrib {
  position: absolute;
  left: 8px;
  bottom: 6px;
  z-index: 2;
  font-size: 11px;
  color: #333;
  background: rgba(255, 255, 255, 0.8);
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
