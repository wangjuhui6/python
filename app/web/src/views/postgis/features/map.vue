<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>
    <div class="map-legend">
      <div class="map-legend-title">数据分类</div>
      <div class="map-legend-actions">
        <el-button link type="primary" @click="selectAll">全选</el-button>
        <el-button link @click="clearSelect">不选</el-button>
        <el-button link type="primary" @click="openCategoryEditor">编辑分类</el-button>
        <el-button link type="primary" @click="openUncategorized">未分类数据</el-button>
        <el-button link type="danger" :disabled="!categories.length" @click="clearCategories">清空分类</el-button>
      </div>
      <div class="map-legend-hint">不选则按当前视野规则查询。可在本页「编辑分类」配置。</div>
      <el-checkbox-group v-model="selectedIds" class="map-legend-list" @change="onCategoryChange">
        <div v-for="item in categories" :key="item.id" class="map-legend-row">
          <el-checkbox
            :value="item.id"
            :class="{ 'is-hidden-mbtiles': !item.show }"
          >
            <span class="map-legend-name">{{ item.name }}</span>
            <span class="map-legend-meta">
              z{{ item.minZoom }}-{{ item.maxZoom }}
              <template v-if="!item.show"> · 不入瓦片</template>
            </span>
            <div v-if="conditionText(item)" class="map-legend-cond">{{ conditionText(item) }}</div>
          </el-checkbox>
          <el-button link type="danger" @click.stop="removeCategory(item)">删除</el-button>
        </div>
      </el-checkbox-group>
      <div v-if="!categories.length" class="map-legend-empty">暂无分类，点击「编辑分类」按字段和取值添加</div>
    </div>
    <div v-if="statusText" class="map-status">{{ statusText }}</div>
    <el-drawer v-model="inspectOpen" title="点击位置的数据" size="420px">
      <div class="inspect-coord">{{ inspectLngLat }}</div>
      <div v-if="!inspectList.length" class="inspect-empty">该坐标下没有数据</div>
      <el-collapse v-else>
        <el-collapse-item v-for="item in inspectList" :key="item.id" :name="String(item.id)">
          <template #title>
            <span>#{{ item.id }} · {{ geomLabel(item.geom_type || item.geometry?.type) }}</span>
          </template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item
              v-for="(val, key) in (item.properties || {})"
              :key="String(key)"
              :label="String(key)"
            >
              {{ formatValue(val) }}
            </el-descriptions-item>
          </el-descriptions>
        </el-collapse-item>
      </el-collapse>
    </el-drawer>
    <el-dialog v-model="editorOpen" title="数据分类" width="960px" append-to-body destroy-on-close class="category-dialog">
      <CategoryEditor v-model="draftCategories" :dataset-id="Number(id)" />
      <template #footer>
        <el-button @click="editorOpen = false">取消</el-button>
        <el-button type="primary" @click="saveDraftCategories">保存分类</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="uncatOpen" title="未分类数据" width="720px" append-to-body @closed="onUncatClosed">
      <div class="uncat-toolbar">未分类共 {{ uncatTotal }} 条</div>
      <el-table :data="uncatList" size="small" max-height="360" v-loading="uncatLoading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="几何" width="90">
          <template #default="{ row }">{{ geomLabel(row.geometry?.type) }}</template>
        </el-table-column>
        <el-table-column label="属性">
          <template #default="{ row }">{{ propsPreview(row.properties) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="uncat-pager"
        background
        layout="total, prev, pager, next"
        :total="uncatTotal"
        :page-size="uncatPageSize"
        :current-page="uncatPage"
        @current-change="onUncatPageChange"
      />
      <el-collapse v-if="uncatList.length" class="uncat-detail">
        <el-collapse-item v-for="item in uncatList" :key="item.id" :name="String(item.id)">
          <template #title>#{{ item.id }} · {{ geomLabel(item.geometry?.type) }}</template>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item
              v-for="(val, key) in (item.properties || {})"
              :key="String(key)"
              :label="String(key)"
            >
              {{ formatValue(val) }}
            </el-descriptions-item>
          </el-descriptions>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { useRoute } from 'vue-router'
import mapboxgl from 'mapbox-gl'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getDataset,
  updateDatasetCategories,
  listFeatures,
  listFeaturesAtPoint,
} from '@/api/postgis'
import { useMap } from '@/hooks/useMap'
import CategoryEditor from '../components/CategoryEditor.vue'

const VIEW_LIMIT = 4000
const DEBOUNCE_MS = 280
const BBOX_PAD = 0.08

const route = useRoute()
const id = route.params.id as string
const mapContainer = ref<HTMLDivElement | null>(null)
const statusText = ref('加载地图…')
const categories = ref<any[]>([])
const selectedIds = ref<string[]>([])
const inspectOpen = ref(false)
const inspectList = ref<any[]>([])
const inspectLngLat = ref('')
const editorOpen = ref(false)
const draftCategories = ref<any[]>([])
const uncatOpen = ref(false)
const uncatLoading = ref(false)
const uncatList = ref<any[]>([])
const uncatTotal = ref(0)
const uncatPage = ref(1)
const uncatPageSize = 10
let uncatOnMap = false

let map: mapboxgl.Map | null = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let requestSeq = 0
let clickMarker: mapboxgl.Marker | null = null

useMap({
  mapRef: mapContainer,
  onMap: (instance) => {
    map = instance
    instance.getCanvas().style.cursor = 'pointer'
    loadViewport()
    instance.on('moveend', scheduleLoad)
    instance.on('click', onMapClick)
  },
})

loadDataset()

async function loadDataset() {
  try {
    const res: any = await getDataset(id)
    categories.value = Array.isArray(res?.categories) ? res.categories : []
  } catch {
    categories.value = []
  }
}

function paddedBbox(instance: mapboxgl.Map) {
  const bounds = instance.getBounds()
  if (!bounds) return [0, 0, 0, 0]
  const west = bounds.getWest()
  const south = bounds.getSouth()
  const east = bounds.getEast()
  const north = bounds.getNorth()
  const dx = (east - west) * BBOX_PAD
  const dy = (north - south) * BBOX_PAD
  return [
    west - dx,
    Math.max(-90, south - dy),
    east + dx,
    Math.min(90, north + dy),
  ]
}

function scheduleLoad() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadViewport, DEBOUNCE_MS)
}

function onCategoryChange() {
  loadViewport()
}

function selectAll() {
  selectedIds.value = categories.value.map((item) => item.id)
  loadViewport()
}

function clearSelect() {
  selectedIds.value = []
  loadViewport()
}

async function persistCategories(next: any[]) {
  const res: any = await updateDatasetCategories({
    datasets_id: id,
    categories: next,
  })
  categories.value = Array.isArray(res?.categories) ? res.categories : next
  selectedIds.value = selectedIds.value.filter((cid) => categories.value.some((item) => item.id === cid))
  loadViewport()
}

async function clearCategories() {
  try {
    await ElMessageBox.confirm('确定清空当前数据源的全部分类？', '清空分类', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
    await persistCategories([])
    ElMessage.success('已清空分类')
  } catch {
    // cancel
  }
}

async function removeCategory(item: any) {
  try {
    await ElMessageBox.confirm(`确定删除分类「${item.name || item.id}」？`, '删除分类', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await persistCategories(categories.value.filter((row) => row.id !== item.id))
    ElMessage.success('已删除分类')
  } catch {
    // cancel
  }
}

function openCategoryEditor() {
  draftCategories.value = JSON.parse(JSON.stringify(categories.value || []))
  editorOpen.value = true
}

async function saveDraftCategories() {
  await persistCategories(draftCategories.value)
  editorOpen.value = false
  ElMessage.success('分类已保存')
}

async function openUncategorized() {
  uncatOpen.value = true
  uncatPage.value = 1
  await loadUncategorized()
}

async function onUncatPageChange(page: number) {
  uncatPage.value = page
  await loadUncategorized()
}

async function loadUncategorized() {
  uncatLoading.value = true
  try {
    const res: any = await listFeatures({
      datasets_id: id,
      is_geojson: true,
      uncategorized: true,
      page: uncatPage.value,
      page_size: uncatPageSize,
    })
    const raw = Array.isArray(res?.data) ? res.data : []
    uncatList.value = raw.filter((item: any) => item?.type === 'Feature' && item.geometry)
    uncatTotal.value = Number(res?.total || 0)
    const source = map?.getSource('geojson-source') as mapboxgl.GeoJSONSource | undefined
    source?.setData({
      type: 'FeatureCollection',
      features: uncatList.value,
    })
    uncatOnMap = true
    statusText.value = `未分类共 ${uncatTotal.value} 条`
  } catch {
    uncatList.value = []
    uncatTotal.value = 0
    ElMessage.error('查询未分类数据失败')
  } finally {
    uncatLoading.value = false
  }
}

function onUncatClosed() {
  if (!uncatOnMap) return
  uncatOnMap = false
  loadViewport()
}

function propsPreview(properties: any) {
  if (!properties || typeof properties !== 'object') return ''
  return Object.entries(properties)
    .slice(0, 6)
    .map(([key, val]) => `${key}=${formatValue(val)}`)
    .join('；')
}

function conditionText(item: any) {
  const parts = (item.conditions || [])
    .map((cond: any) => {
      if (!cond.key) return ''
      const values = cond.values || []
      const exclude = !!cond.exclude
      if (!values.length) return exclude ? `无${cond.key}` : cond.key
      const joined = values.join(',')
      if (exclude) return values.length === 1 ? `${cond.key}≠${joined}` : `${cond.key}∉${joined}`
      return values.length === 1 ? `${cond.key}=${joined}` : `${cond.key}∈${joined}`
    })
    .filter(Boolean)
  return parts.join(' 且 ')
}

async function loadViewport() {
  if (!map || uncatOpen.value) return
  const seq = ++requestSeq
  const bbox = paddedBbox(map)
  const zoom = map.getZoom()
  statusText.value = '加载视野数据…'
  try {
    const params: any = {
      datasets_id: id,
      is_geojson: true,
      bbox: bbox.join(','),
      zoom: zoom.toFixed(2),
      limit: VIEW_LIMIT,
    }
    if (selectedIds.value.length) {
      params.category_ids = selectedIds.value.join(',')
    }
    const res: any = await listFeatures(params)
    if (seq !== requestSeq) return
    const raw = Array.isArray(res?.data) ? res.data : []
    const features = raw.filter((item: any) => item?.type === 'Feature' && item.geometry)
    const source = map.getSource('geojson-source') as mapboxgl.GeoJSONSource | undefined
    source?.setData({
      type: 'FeatureCollection',
      features,
    })
    if (res?.hint) {
      statusText.value = `${features.length} 条 · ${res.hint}`
    } else {
      statusText.value = `已加载 ${features.length} 条`
    }
  } catch {
    if (seq !== requestSeq) return
    statusText.value = '视野数据加载失败'
  }
}

async function onMapClick(e: mapboxgl.MapMouseEvent) {
  if (!map) return
  const { lng, lat } = e.lngLat
  inspectLngLat.value = `${lng.toFixed(6)}, ${lat.toFixed(6)}`
  clickMarker?.remove()
  clickMarker = new mapboxgl.Marker({ color: '#dc2626' }).setLngLat([lng, lat]).addTo(map)
  inspectOpen.value = true
  inspectList.value = []
  try {
    const res: any = await listFeaturesAtPoint({
      datasets_id: id,
      lng,
      lat,
      zoom: map.getZoom().toFixed(2),
      limit: 80,
    })
    inspectList.value = Array.isArray(res?.data) ? res.data : []
  } catch {
    inspectList.value = []
    ElMessage.error('查询点击位置失败')
  }
}

function geomLabel(type?: string) {
  const value = (type || '').toLowerCase()
  if (value.includes('point')) return '点'
  if (value.includes('line')) return '线'
  if (value.includes('polygon')) return '面'
  return type || '未知'
}

function formatValue(val: any) {
  if (val == null) return ''
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  map?.off('moveend', scheduleLoad)
  map?.off('click', onMapClick)
  clickMarker?.remove()
})
</script>

<style scoped>
.map-wrapper{
  width: 100%;
  height: 100%;
  position: relative;
}
.map-container{
  width: 100%;
  height: 100%;
}
.map-legend{
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  width: 300px;
  max-height: 80vh;
  overflow: auto;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}
.map-legend-title{
  font-weight: 600;
  margin-bottom: 4px;
}
.map-legend-actions{
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.map-legend-hint,
.map-legend-empty,
.map-legend-meta{
  color: #78716c;
  font-size: 12px;
}
.map-legend-hint{
  margin: 6px 0 8px;
  line-height: 1.4;
}
.map-legend-list{
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}
.map-legend-row{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 4px;
}
.map-legend-row :deep(.el-checkbox){
  flex: 1;
  height: auto;
  white-space: normal;
}
.map-legend-cond{
  width: 100%;
  color: #a8a29e;
  font-size: 11px;
  line-height: 1.3;
  white-space: normal;
}
.is-hidden-mbtiles :deep(.el-checkbox__label){
  opacity: 0.7;
}
.map-status{
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 2;
  max-width: calc(100% - 24px);
  padding: 6px 10px;
  border-radius: 4px;
  background: rgba(28, 25, 23, 0.78);
  color: #fff;
  font-size: 12px;
  line-height: 1.4;
  pointer-events: none;
}
.inspect-coord{
  margin-bottom: 12px;
  color: #57534e;
  font-size: 13px;
}
.uncat-toolbar{
  margin-bottom: 8px;
  color: #57534e;
  font-size: 13px;
}
.uncat-pager{
  margin: 12px 0;
  justify-content: flex-end;
}
</style>
<style>
.category-dialog .el-dialog__body {
  max-height: 80vh;
  overflow: auto;
}
</style>
