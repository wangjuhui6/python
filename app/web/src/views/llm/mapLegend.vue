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
      title="先上传图片，在图上点选至少 2 个能对上实地的位置并填写经纬度。识别时模型只读图例，点位和经纬度由控制点换算。"
    />

    <div class="toolbar">
      <input ref="fileInput" class="file-input" type="file" accept="image/*" @change="onNativeFile" />
      <el-button @click="fileInput?.click()">上传图片</el-button>
      <el-button :disabled="!imageUrl" @click="undoPoint">撤销点</el-button>
      <el-button :disabled="!gcps.length" @click="clearPoints">清空点</el-button>
      <el-button type="primary" :loading="running" :disabled="!canRun" @click="recognize">开始识别</el-button>
    </div>

    <el-input
      v-model="instruction"
      class="instruction"
      type="textarea"
      :rows="2"
      placeholder="可选说明，例如：只要学校和医院；图例在右下角。"
    />

    <div class="workspace">
      <div class="stage" v-if="imageUrl">
        <div class="stage-inner">
          <img ref="imgRef" :src="imageUrl" class="map-image" alt="地图" @click="onImageClick" @load="onImageLoad" />
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
      <div v-else class="empty">上传一张地图图片，点击图面添加控制点</div>

      <div class="side">
        <div class="block-title">控制点 · {{ gcps.length }}</div>
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
          <el-table-column label="" width="52">
            <template #default="scope">
              <el-button link type="danger" @click="removePoint(scope.$index)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="georef" class="meta">
          配准：{{ georef.kind === 'affine' ? '仿射' : '相似' }} · {{ georef.count }} 点 · 平均残差 {{ georef.mean_error_m }} 米
        </div>
      </div>
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
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="type" label="类型" width="90" />
        <el-table-column prop="lng" label="经度" min-width="110" />
        <el-table-column prop="lat" label="纬度" min-width="110" />
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLlmConfig, recognizeMapLegend } from '@/api/llm'

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

const loaded = ref(false)
const vision = ref(false)
const imageUrl = ref('')
const imageFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const natural = ref({ w: 1, h: 1 })
const gcps = ref<Gcp[]>([])
const activeIndex = ref(-1)
const instruction = ref('')
const running = ref(false)
const legend = ref<any[]>([])
const features = ref<Feature[]>([])
const georef = ref<any>(null)
const notes = ref('')
const geojson = ref<any>(null)

const canRun = computed(() => !!imageFile.value && gcps.value.length >= 2)
const geojsonText = computed(() => geojson.value ? JSON.stringify(geojson.value, null, 2) : '')

onMounted(async () => {
  const data = await getLlmConfig()
  loaded.value = !!data?.loaded
  vision.value = !!data?.vision_enabled
})

onUnmounted(() => {
  if (imageUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(imageUrl.value)
  }
})

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
}

function onNativeFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) {
    return
  }
  setImage(file)
  input.value = ''
}

function onImageLoad() {
  const img = imgRef.value
  if (!img) {
    return
  }
  natural.value = { w: img.naturalWidth || 1, h: img.naturalHeight || 1 }
}

function onImageClick(event: MouseEvent) {
  const img = imgRef.value
  if (!img) {
    return
  }
  const rect = img.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * natural.value.w
  const y = ((event.clientY - rect.top) / rect.height) * natural.value.h
  gcps.value.push({
    x,
    y,
    lng: '',
    lat: '',
    note: '',
  })
  activeIndex.value = gcps.value.length - 1
}

function markStyle(point: { x: number; y: number }) {
  return {
    left: `${(point.x / natural.value.w) * 100}%`,
    top: `${(point.y / natural.value.h) * 100}%`,
  }
}

function featStyle(feat: Feature) {
  const style = markStyle(feat)
  return { ...style, background: feat.color || '#f56c6c' }
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

async function recognize() {
  if (!imageFile.value) {
    return
  }
  const points = gcps.value.map((item) => ({
    x: item.x,
    y: item.y,
    lng: Number(item.lng),
    lat: Number(item.lat),
    note: item.note || '',
  }))
  if (points.some((item) => Number.isNaN(item.lng) || Number.isNaN(item.lat))) {
    ElMessage.error('每个控制点都要填写有效的经纬度')
    return
  }
  running.value = true
  try {
    const form = new FormData()
    form.append('file', imageFile.value)
    form.append('gcps', JSON.stringify(points))
    form.append('instruction', instruction.value)
    const data = await recognizeMapLegend(form)
    legend.value = data?.legend || []
    features.value = data?.features || []
    georef.value = data?.georef || null
    notes.value = data?.notes || ''
    geojson.value = data?.geojson || null
    const count = data?.geojson?.features?.length || 0
    if (count) {
      ElMessage.success(`识别完成，生成 ${count} 条 GeoJSON`)
    } else {
      ElMessage.warning(data?.notes || '图例已返回，但地图要素为空')
    }
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '识别失败')
  } finally {
    running.value = false
  }
}

async function copyGeojson() {
  if (!geojsonText.value) {
    return
  }
  await navigator.clipboard.writeText(geojsonText.value)
  ElMessage.success('已复制 GeoJSON')
}

function downloadGeojson() {
  if (!geojsonText.value) {
    return
  }
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
  max-width: 1200px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint,
.instruction,
.toolbar {
  margin-bottom: 12px;
}
.toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}
.stage {
  border: 1px solid #ebeef5;
  background: #f5f7fa;
  overflow: auto;
  max-height: 640px;
}
.stage-inner {
  position: relative;
  width: 100%;
}
.map-image {
  display: block;
  width: 100%;
  height: auto;
  cursor: crosshair;
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
  .workspace {
    grid-template-columns: 1fr;
  }
}
</style>
