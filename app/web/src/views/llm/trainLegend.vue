<template>
  <el-card class="train-page">
    <template #header>
      <div class="page-header">
        <span>图例训练样本</span>
        <el-tag :type="vision ? 'success' : loaded ? 'warning' : 'info'">
          {{ vision ? '视觉模型已加载，可预标注' : loaded ? '当前是文本模型' : '未加载模型' }}
        </el-tag>
        <el-tag type="info">已确认 {{ dataset.counts?.accepted || 0 }} / 共 {{ dataset.counts?.total || 0 }}</el-tag>
      </div>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      :title="`先点选一条图例，再在地图上点击标出这类要素大概在哪。样本在 ${dataset.root || 'data/train-legend'}，保存后可下次继续。`"
    />

    <div class="toolbar">
      <input ref="fileInput" class="file-input" type="file" accept="image/*" multiple @change="onImport" />
      <el-button @click="fileInput?.click()">导入图片</el-button>
      <el-radio-group v-model="statusFilter" size="small" @change="reloadSamples">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="draft">草稿</el-radio-button>
        <el-radio-button value="review">待审</el-radio-button>
        <el-radio-button value="accepted">已确认</el-radio-button>
        <el-radio-button value="rejected">弃用</el-radio-button>
      </el-radio-group>
      <el-button type="primary" :loading="exporting" @click="doExport">导出已确认</el-button>
      <el-button @click="runVisible = true">记录训练</el-button>
    </div>

    <div class="workspace">
      <div class="list">
        <div
          v-for="item in samples"
          :key="item.id"
          class="list-item"
          :class="{ active: item.id === currentId }"
          @click="selectSample(item.id)"
        >
          <img :src="imageSrc(item.id)" class="thumb" alt="" />
          <div class="list-meta">
            <div class="list-name" :title="item.filename">{{ item.filename || item.id }}</div>
            <el-tag size="small" :type="statusType(item.status)">{{ statusLabel(item.status) }}</el-tag>
          </div>
        </div>
        <div v-if="!samples.length" class="empty">还没有样本，先导入地图图片</div>
      </div>

      <div class="editor">
        <template v-if="current">
          <div class="toolbar tight">
            <el-button :type="drawingLegend ? 'warning' : 'default'" @click="toggleDrawLegend">
              {{ drawingLegend ? '正在框选图例' : '框选图例' }}
            </el-button>
            <el-button :disabled="!legendBox" @click="legendBox = null">清除图例框</el-button>
            <el-button :disabled="!marks.length" @click="undoMark">撤销打点</el-button>
            <el-button type="primary" :loading="prelabeling" :disabled="!vision" @click="doPrelabel">预标注图例</el-button>
            <el-button :loading="saving" @click="doSave()">保存</el-button>
            <el-button type="success" :loading="saving" @click="doSave('accepted')">确认</el-button>
            <el-button :loading="saving" @click="doSave('rejected')">弃用</el-button>
            <el-button type="danger" link @click="doDelete">删除</el-button>
          </div>
          <el-input v-model="instruction" class="instruction" type="textarea" :rows="2" placeholder="可选说明，例如：图例在右下角。" />
          <div v-if="imageUrl" class="stage">
            <div class="stage-inner">
              <img
                ref="imgRef"
                :src="imageUrl"
                class="map-image"
                :class="{ drawing: drawingLegend || activeLegendIndex >= 0 }"
                alt="地图"
                @load="onImageLoad"
                @click="onMapClick"
                @mousedown="onLegendMouseDown"
                @mousemove="onLegendMouseMove"
                @mouseup="onLegendMouseUp"
                @mouseleave="onLegendMouseUp"
              />
              <div v-if="legendBoxStyle" class="legend-box" :style="legendBoxStyle" />
              <button
                v-for="(mark, index) in marks"
                :key="'mark-' + index"
                class="feat-mark"
                :class="{ poly: mark.shape === 'polygon', line: mark.shape === 'line' }"
                :style="markStyle(mark)"
                type="button"
                :title="mark.name"
                @click.stop="removeMark(index)"
              >
                {{ index + 1 }}
              </button>
            </div>
          </div>
          <div class="form-hint">
            {{
              drawingLegend
                ? '拖拽框出图例区域'
                : activeLegend
                  ? `已选「${activeLegend.name}」，在图上点击标注大概位置，点标记可删除`
                  : '在下表点选一条图例后，再在图上点击标注位置'
            }}
            · 已标 {{ marks.length }} 处
          </div>
          <div class="block-title">图例条目</div>
          <div class="toolbar tight">
            <el-button size="small" @click="addRow">加一行</el-button>
          </div>
          <el-table
            :data="legend"
            size="small"
            highlight-current-row
            @current-change="onLegendRow"
          >
            <el-table-column label="名称" min-width="140">
              <template #default="scope">
                <el-input v-model="scope.row.name" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="形态" width="120">
              <template #default="scope">
                <el-select v-model="scope.row.shape" size="small">
                  <el-option label="点" value="point" />
                  <el-option label="面" value="polygon" />
                  <el-option label="线" value="line" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="颜色" width="150">
              <template #default="scope">
                <el-input v-model="scope.row.color" size="small" placeholder="#RRGGBB" />
              </template>
            </el-table-column>
            <el-table-column label="描述" min-width="160">
              <template #default="scope">
                <el-input v-model="scope.row.description" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="图上" width="70">
              <template #default="scope">{{ markCount(scope.row.name) }}</template>
            </el-table-column>
            <el-table-column width="52">
              <template #default="scope">
                <el-button link type="danger" @click.stop="legend.splice(scope.$index, 1)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="notes" class="notes">{{ notes }}</div>
        </template>
        <div v-else class="empty">从左侧选择一张图开始标注</div>
      </div>
    </div>

    <div v-if="dataset.exports?.length" class="result">
      <div class="block-title">导出记录</div>
      <el-table :data="dataset.exports" size="small">
        <el-table-column prop="name" label="文件" min-width="180" />
        <el-table-column prop="path" label="路径" min-width="280" show-overflow-tooltip />
      </el-table>
    </div>

    <div v-if="dataset.runs?.length" class="result">
      <div class="block-title">训练记录</div>
      <el-table :data="dataset.runs" size="small">
        <el-table-column prop="created_at" label="时间" width="200" />
        <el-table-column prop="base_model" label="底座模型" min-width="180" show-overflow-tooltip />
        <el-table-column prop="output_path" label="输出" min-width="180" show-overflow-tooltip />
        <el-table-column prop="sample_count" label="条数" width="80" />
        <el-table-column prop="notes" label="备注" min-width="160" />
      </el-table>
    </div>

    <el-dialog v-model="runVisible" title="记录一次训练" width="520px">
      <el-form label-width="100px">
        <el-form-item label="导出目录">
          <el-input v-model="runForm.export_path" placeholder="exports 下某次导出的路径" />
        </el-form-item>
        <el-form-item label="底座模型">
          <el-input v-model="runForm.base_model" placeholder="例如 Qwen2.5-VL-3B" />
        </el-form-item>
        <el-form-item label="输出路径">
          <el-input v-model="runForm.output_path" placeholder="LoRA 或转好的 GGUF 路径" />
        </el-form-item>
        <el-form-item label="样本数">
          <el-input-number v-model="runForm.sample_count" :min="0" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="runForm.notes" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="runVisible = false">取消</el-button>
        <el-button type="primary" @click="saveRun">保存记录</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  addTrainLegendRun,
  deleteTrainLegendSample,
  exportTrainLegend,
  getLlmConfig,
  getTrainLegendDataset,
  getTrainLegendSample,
  importTrainLegendSamples,
  listTrainLegendSamples,
  prelabelTrainLegendSample,
  saveTrainLegendSample,
} from '@/api/llm'

type Sample = {
  id: string
  filename?: string
  status?: string
  instruction?: string
  legend?: any[]
  legend_box?: { x: number; y: number; w: number; h: number } | null
  notes?: string
}

const loaded = ref(false)
const vision = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const dataset = ref<any>({ counts: {}, exports: [], runs: [] })
const samples = ref<Sample[]>([])
const statusFilter = ref('')
const currentId = ref('')
const current = ref<Sample | null>(null)
const instruction = ref('')
const legend = ref<any[]>([])
const legendBox = ref<Sample['legend_box']>(null)
const marks = ref<any[]>([])
const activeLegendIndex = ref(-1)
const notes = ref('')
const natural = ref({ w: 1, h: 1 })
const drawingLegend = ref(false)
const imgRef = ref<HTMLImageElement | null>(null)
const saving = ref(false)
const prelabeling = ref(false)
const exporting = ref(false)
const runVisible = ref(false)
const runForm = reactive({
  export_path: '',
  base_model: '',
  output_path: '',
  sample_count: 0,
  notes: '',
})
let legendDrag: { x: number; y: number } | null = null

const imageUrl = computed(() => (currentId.value ? imageSrc(currentId.value) : ''))
const activeLegend = computed(() => legend.value[activeLegendIndex.value] || null)

const legendBoxStyle = computed(() => {
  const box = legendBox.value
  if (!box || !natural.value.w) return null
  return {
    left: `${(box.x / natural.value.w) * 100}%`,
    top: `${(box.y / natural.value.h) * 100}%`,
    width: `${(box.w / natural.value.w) * 100}%`,
    height: `${(box.h / natural.value.h) * 100}%`,
  }
})

function imageSrc(id: string) {
  return `/api/llm/train-legend/samples/${id}/image`
}

function statusLabel(status?: string) {
  return { draft: '草稿', review: '待审', accepted: '已确认', rejected: '弃用' }[status || 'draft'] || status
}

function statusType(status?: string) {
  return { draft: 'info', review: 'warning', accepted: 'success', rejected: 'danger' }[status || 'draft'] as any
}

async function loadStatus() {
  try {
    const data = await getLlmConfig()
    loaded.value = !!data?.loaded
    vision.value = !!data?.vision_enabled
  } catch {
    loaded.value = false
    vision.value = false
  }
}

async function reloadDataset() {
  dataset.value = (await getTrainLegendDataset()) || { counts: {} }
}

async function reloadSamples() {
  samples.value = (await listTrainLegendSamples(statusFilter.value || undefined)) || []
  if (currentId.value && !samples.value.some((item) => item.id === currentId.value)) {
    current.value = null
    currentId.value = ''
  }
}

async function selectSample(id: string) {
  const data = await getTrainLegendSample(id)
  currentId.value = id
  current.value = data
  instruction.value = data?.instruction || ''
  legend.value = (data?.legend || []).map((row: any) => ({ ...row }))
  legendBox.value = data?.legend_box || null
  marks.value = (data?.features || []).map((row: any) => ({ ...row }))
  notes.value = data?.notes || ''
  activeLegendIndex.value = legend.value.length ? 0 : -1
}

function onImageLoad(ev: Event) {
  const img = ev.target as HTMLImageElement
  natural.value = { w: img.naturalWidth || 1, h: img.naturalHeight || 1 }
}

function clientToImage(ev: MouseEvent) {
  const img = imgRef.value
  if (!img) return null
  const rect = img.getBoundingClientRect()
  const x = ((ev.clientX - rect.left) / rect.width) * natural.value.w
  const y = ((ev.clientY - rect.top) / rect.height) * natural.value.h
  return { x, y }
}

function markCount(name: string) {
  return marks.value.filter((item) => item.name === name).length
}

function markStyle(mark: any) {
  const color = mark.color || '#409eff'
  return {
    left: `${(mark.x / natural.value.w) * 100}%`,
    top: `${(mark.y / natural.value.h) * 100}%`,
    background: color,
    borderColor: '#fff',
  }
}

function onLegendRow(_row: any, _unused: any) {
  const index = legend.value.findIndex((item) => item === _row)
  activeLegendIndex.value = index
  if (index >= 0 && _row?.name) {
    drawingLegend.value = false
    ElMessage.info(`在图上点击标出「${_row.name}」的大概位置`)
  }
}

function onMapClick(ev: MouseEvent) {
  if (drawingLegend.value) return
  const item = activeLegend.value
  if (!item?.name) {
    ElMessage.warning('请先在下表点选一条图例')
    return
  }
  const pt = clientToImage(ev)
  if (!pt) return
  marks.value.push({
    name: item.name,
    shape: item.shape || 'point',
    color: item.color || '',
    x: pt.x,
    y: pt.y,
  })
}

function removeMark(index: number) {
  marks.value.splice(index, 1)
}

function undoMark() {
  marks.value.pop()
}

function toggleDrawLegend() {
  drawingLegend.value = !drawingLegend.value
  if (drawingLegend.value) ElMessage.info('在图片上拖拽框出整块图例')
}

function onLegendMouseDown(ev: MouseEvent) {
  if (!drawingLegend.value) return
  ev.preventDefault()
  legendDrag = clientToImage(ev)
  if (!legendDrag) return
  legendBox.value = { x: legendDrag.x, y: legendDrag.y, w: 1, h: 1 }
}

function onLegendMouseMove(ev: MouseEvent) {
  if (!drawingLegend.value || !legendDrag) return
  const pt = clientToImage(ev)
  if (!pt) return
  legendBox.value = {
    x: Math.min(legendDrag.x, pt.x),
    y: Math.min(legendDrag.y, pt.y),
    w: Math.abs(pt.x - legendDrag.x),
    h: Math.abs(pt.y - legendDrag.y),
  }
}

function onLegendMouseUp() {
  legendDrag = null
  drawingLegend.value = false
}

function addRow() {
  legend.value.push({ name: '', shape: 'point', color: '', description: '' })
}

async function onImport(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files || [])
  input.value = ''
  if (!files.length) return
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  try {
    const created = await importTrainLegendSamples(form)
    ElMessage.success(`已导入 ${created?.length || files.length} 张`)
    await reloadDataset()
    await reloadSamples()
    if (created?.[0]?.id) await selectSample(created[0].id)
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '导入失败')
  }
}

async function doSave(status?: string) {
  if (!currentId.value) return
  saving.value = true
  try {
    const data = await saveTrainLegendSample(currentId.value, {
      legend: legend.value,
      legend_box: legendBox.value,
      features: marks.value,
      instruction: instruction.value,
      notes: notes.value,
      status: status || current.value?.status || 'review',
      source: 'human',
    })
    current.value = data
    ElMessage.success(status === 'accepted' ? '已确认并保存' : '已保存')
    await reloadDataset()
    await reloadSamples()
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '保存失败')
  } finally {
    saving.value = false
  }
}

async function doPrelabel() {
  if (!currentId.value) return
  prelabeling.value = true
  try {
    const data = await prelabelTrainLegendSample(currentId.value, instruction.value)
    current.value = data
    legend.value = (data?.legend || []).map((row: any) => ({ ...row }))
    legendBox.value = data?.legend_box || legendBox.value
    if (Array.isArray(data?.features)) marks.value = data.features.map((row: any) => ({ ...row }))
    notes.value = data?.notes || ''
    ElMessage.success('预标注完成，请核对后保存')
    await reloadDataset()
    await reloadSamples()
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '预标注失败')
  } finally {
    prelabeling.value = false
  }
}

async function doDelete() {
  if (!currentId.value) return
  await deleteTrainLegendSample(currentId.value)
  currentId.value = ''
  current.value = null
  ElMessage.success('已删除')
  await reloadDataset()
  await reloadSamples()
}

async function doExport() {
  exporting.value = true
  try {
    const data = await exportTrainLegend(['accepted'])
    ElMessage.success(`已导出 ${data?.count || 0} 条到 ${data?.path || ''}`)
    runForm.export_path = data?.path || ''
    runForm.sample_count = data?.count || 0
    await reloadDataset()
  } catch (err: any) {
    ElMessage.error(typeof err === 'string' ? err : '导出失败')
  } finally {
    exporting.value = false
  }
}

async function saveRun() {
  await addTrainLegendRun({ ...runForm })
  runVisible.value = false
  ElMessage.success('训练记录已保存')
  await reloadDataset()
}

onMounted(async () => {
  await loadStatus()
  await reloadDataset()
  await reloadSamples()
})
</script>

<style scoped lang="less">
.train-page {
  max-width: 1400px;
}
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint,
.toolbar,
.instruction,
.result {
  margin-bottom: 12px;
}
.file-input {
  display: none;
}
.toolbar.tight {
  margin-bottom: 8px;
}
.workspace {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: 16px;
  min-height: 480px;
}
.list {
  border: 1px solid #eee;
  border-radius: 8px;
  overflow: auto;
  max-height: 640px;
}
.list-item {
  display: flex;
  gap: 8px;
  padding: 8px;
  cursor: pointer;
  align-items: center;
}
.list-item.active,
.list-item:hover {
  background: #f5f7fa;
}
.thumb {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 4px;
  background: #ddd;
}
.list-name {
  font-size: 12px;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.list-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stage {
  overflow: auto;
  background: #f6f6f6;
  border-radius: 8px;
  margin-bottom: 12px;
}
.stage-inner {
  position: relative;
  display: inline-block;
}
.map-image {
  max-width: 100%;
  display: block;
}
.map-image.drawing {
  cursor: crosshair;
}
.legend-box {
  position: absolute;
  border: 2px solid #e6a23c;
  background: rgba(230, 162, 60, 0.15);
  pointer-events: none;
}
.form-hint {
  color: #888;
  font-size: 12px;
  margin: 8px 0 12px;
}
.feat-mark {
  position: absolute;
  width: 18px;
  height: 18px;
  margin-left: -9px;
  margin-top: -9px;
  border-radius: 50%;
  border: 2px solid #fff;
  color: #fff;
  font-size: 10px;
  line-height: 14px;
  padding: 0;
  cursor: pointer;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
}
.feat-mark.poly {
  border-radius: 3px;
}
.feat-mark.line {
  border-radius: 2px;
  width: 16px;
  height: 10px;
  margin-top: -5px;
}
.block-title {
  font-weight: 600;
  margin: 8px 0;
}
.empty {
  color: #888;
  padding: 24px;
}
.notes {
  color: #666;
  font-size: 12px;
  margin-top: 8px;
}
</style>
