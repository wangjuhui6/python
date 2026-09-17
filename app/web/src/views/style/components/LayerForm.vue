<template>
  <div v-if="layer" class="layer-form">
    <el-alert class="anim-help" type="info" :closable="false" show-icon>
      <template #title>动画怎么配</template>
      <div class="anim-help-body">
        <p><b>缩放升起（推荐写进样式 JSON）</b>：先填下面的「高度字段 / 底高字段」（数据里叫什么就填什么），再点「写入建筑升起动画」。拉近地图时建筑从地面长出来。</p>
        <p><b>过渡 transition</b>：改下面的「过渡时长 / 延迟」，再点「写入过渡时间」。只对常量变化生效。</p>
        <p><b>四种取值</b>：常量=固定值；字段=读矢量属性；缩放动画=随 zoom 插值；表达式=手写 Mapbox 表达式。</p>
      </div>
    </el-alert>

    <el-form label-position="top" size="small">
      <el-form-item label="图层 ID">
        <el-input :model-value="layer.id" @change="(v: string) => rename(v)" />
        <div class="field-tip">样式内唯一名称，导出后客户端用这个 id 找图层。</div>
      </el-form-item>
      <el-form-item label="类型">
        <el-select :model-value="layer.type" style="width: 100%" @change="(v: string) => store.updateLayer(layer.id, { type: v })">
          <el-option v-for="type in LAYER_TYPES" :key="type" :label="LAYER_TYPE_LABELS[type]" :value="type" />
        </el-select>
        <div class="field-tip">普通白膜用「拉伸 3D」；Mapbox 3.0 程序化建筑用「建筑 3D」。</div>
      </el-form-item>
      <el-form-item v-if="!SOURCELESS_TYPES.has(layer.type)" label="数据源">
        <el-select :model-value="layer.source" clearable filterable style="width: 100%" @change="(v: string) => store.updateLayer(layer.id, { source: v })">
          <el-option v-for="id in store.sourceIds" :key="id" :label="id" :value="id" />
        </el-select>
        <div class="field-tip">对应左侧「数据源」里的 id，例如 china-auto。</div>
      </el-form-item>
      <el-form-item v-if="!SOURCELESS_TYPES.has(layer.type)" label="矢量图层 source-layer">
        <el-input :model-value="layer['source-layer']" placeholder="如 building、transportation" @change="(v: string) => store.updateLayer(layer.id, { 'source-layer': v })" />
        <div class="field-tip">mbtiles / pbf 里的图层名，不是数据源 id。建筑常见 building。</div>
      </el-form-item>
      <el-form-item label="显示级别 minzoom / maxzoom">
        <div style="display: flex; gap: 8px">
          <el-input-number :model-value="layer.minzoom" :min="0" :max="24" @change="(v: number) => store.updateLayer(layer.id, { minzoom: v })" />
          <el-input-number :model-value="layer.maxzoom" :min="0" :max="24" @change="(v: number) => store.updateLayer(layer.id, { maxzoom: v })" />
        </div>
        <div class="field-tip">建筑拉伸建议 minzoom 14 或 15，太远看不清还耗性能。</div>
      </el-form-item>
      <el-form-item label="过滤 filter">
        <el-input :model-value="filterText" type="textarea" :rows="3" placeholder='例如 ["==","extrude",true]' @change="onFilter" />
        <div class="field-tip">只画符合条件的要素。空表示不过滤。</div>
      </el-form-item>
    </el-form>

    <div v-if="layer.type === 'fill-extrusion' || layer.type === 'building'" class="height-fields">
      <el-form label-position="top" size="small">
        <el-form-item label="高度字段">
          <el-input v-model="heightField" placeholder="如 height、h、render_height" @change="applyHeightField" />
        </el-form-item>
        <el-form-item label="底高字段">
          <el-input v-model="baseField" placeholder="如 min_height、min-height；可留空表示 0" @change="applyBaseField" />
        </el-form-item>
        <el-form-item label="升起缩放区间">
          <div class="num-row">
            <el-input-number v-model="zoomFrom" :min="0" :max="24" :step="0.05" controls-position="right" />
            <span>→</span>
            <el-input-number v-model="zoomTo" :min="0" :max="24" :step="0.05" controls-position="right" />
          </div>
          <div class="field-tip">区间越窄，拉近时升起越快。例如 15 → 15.05 几乎瞬间长高，15 → 17 更慢。</div>
        </el-form-item>
        <el-form-item label="过渡时长 / 延迟（毫秒）">
          <div class="num-row">
            <el-input-number v-model="animDuration" :min="0" :step="100" controls-position="right" />
            <span>时长</span>
            <el-input-number v-model="animDelay" :min="0" :step="50" controls-position="right" />
            <span>延迟</span>
          </div>
          <div class="field-tip">写入升起/过渡时会写进 *-transition。只对常量变化生效；缩放升起本身跟着 zoom 走，不靠这个毫秒。</div>
        </el-form-item>
      </el-form>
      <div class="presets">
        <el-button size="small" type="primary" plain @click="applyGrow">写入建筑升起动画</el-button>
        <el-button size="small" plain @click="applyBuildingTransition">写入过渡时间</el-button>
      </div>
      <div class="preset-tip">
        字段名必须和矢量数据属性一致。升起按上面的缩放区间从 0 长到高度字段；过渡按填写的毫秒写入。
      </div>
    </div>

    <el-collapse v-model="active">
      <el-collapse-item title="布局 · 基础" name="layout-base">
        <ExpressionField
          v-for="field in layoutFields.filter((f) => f.group === 'base')"
          :key="field.name"
          :field="field"
          :model-value="layer.layout?.[field.name]"
          @update:model-value="(v) => store.setLayerLayout(layer.id, field.name, v)"
        />
      </el-collapse-item>
      <el-collapse-item v-if="layoutFields.some((f) => f.group === '3d')" title="布局 · 3D / 建筑" name="layout-3d">
        <ExpressionField
          v-for="field in layoutFields.filter((f) => f.group === '3d')"
          :key="field.name"
          :field="field"
          :model-value="layer.layout?.[field.name]"
          :default-get-field="defaultGetFor(field.name)"
          @update:model-value="(v) => store.setLayerLayout(layer.id, field.name, v)"
        />
      </el-collapse-item>
      <el-collapse-item title="绘制 · 基础" name="paint-base">
        <ExpressionField
          v-for="field in paintFields.filter((f) => f.group === 'base')"
          :key="field.name"
          :field="field"
          :model-value="layer.paint?.[field.name]"
          @update:model-value="(v) => store.setLayerPaint(layer.id, field.name, v)"
        />
      </el-collapse-item>
      <el-collapse-item v-if="paintFields.some((f) => f.group === '3d')" title="绘制 · 3D / 建筑动画" name="paint-3d">
        <ExpressionField
          v-for="field in paintFields.filter((f) => f.group === '3d')"
          :key="field.name"
          :field="field"
          :model-value="layer.paint?.[field.name]"
          :default-get-field="defaultGetFor(field.name)"
          @update:model-value="(v) => store.setLayerPaint(layer.id, field.name, v)"
        />
      </el-collapse-item>
      <el-collapse-item title="过渡动画 transition" name="transition">
        <ExpressionField
          v-for="field in [...layoutFields, ...paintFields].filter((f) => f.group === 'transition')"
          :key="field.name"
          :field="field"
          :model-value="field.name.startsWith('building-height') || field.name.includes('layout') ? layer.layout?.[field.name] : layer.paint?.[field.name] ?? layer.layout?.[field.name]"
          @update:model-value="(v) => setTransition(field.name, v)"
        />
      </el-collapse-item>
    </el-collapse>
  </div>
  <el-empty v-else description="选择一个图层" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { LAYER_TYPE_LABELS, LAYER_TYPES, SOURCELESS_TYPES } from '@/views/style/lib/types'
import { getLayerFields } from '@/views/style/lib/specFields'
import {
  buildingGrowLayout,
  buildingGrowPaint,
  extractGetName,
  extractZoomStops,
  replaceGetName,
  transitionValue,
} from '@/views/style/lib/layerTemplates'
import ExpressionField from './ExpressionField.vue'

const store = useStyleEditorStore()
const active = ref(['paint-base', 'paint-3d', 'layout-3d'])
const layer = computed(() => store.selectedLayer)
const fields = computed(() => getLayerFields(layer.value?.type || 'fill'))
const layoutFields = computed(() => fields.value.layout)
const paintFields = computed(() => fields.value.paint)
const filterText = computed(() => (layer.value?.filter ? JSON.stringify(layer.value.filter, null, 2) : ''))
const heightField = ref('height')
const baseField = ref('min_height')
const zoomFrom = ref(15)
const zoomTo = ref(16)
const animDuration = ref(800)
const animDelay = ref(0)

function heightValue() {
  const current = layer.value
  if (!current) return undefined
  return current.paint?.['fill-extrusion-height'] ?? current.layout?.['building-height']
}

function baseValue() {
  const current = layer.value
  if (!current) return undefined
  return current.paint?.['fill-extrusion-base'] ?? current.layout?.['building-base']
}

watch(
  () => layer.value?.id,
  () => {
    heightField.value = extractGetName(heightValue()) || 'height'
    baseField.value = extractGetName(baseValue()) || 'min_height'
    const stops = extractZoomStops(heightValue())
    if (stops) {
      zoomFrom.value = stops.from
      zoomTo.value = stops.to
    }
    const trans =
      layer.value?.paint?.['fill-extrusion-height-transition'] ||
      layer.value?.layout?.['building-height-transition'] ||
      layer.value?.paint?.['building-vertical-scale-transition']
    if (trans && typeof trans === 'object') {
      if (typeof trans.duration === 'number') animDuration.value = trans.duration
      if (typeof trans.delay === 'number') animDelay.value = trans.delay
    }
  },
  { immediate: true },
)

watch(
  () => store.suggestedHeightField,
  (key) => {
    if (!key) return
    heightField.value = key
    if (layer.value?.type === 'fill-extrusion' || layer.value?.type === 'building') applyHeightField()
    ElMessage.success(`高度字段已设为 ${key}`)
  },
)

watch(
  () => store.suggestedBaseField,
  (key) => {
    if (!key) return
    baseField.value = key
    if (layer.value?.type === 'fill-extrusion' || layer.value?.type === 'building') applyBaseField()
    ElMessage.success(`底高字段已设为 ${key}`)
  },
)

function defaultGetFor(name: string) {
  if (/height$/.test(name) && !name.includes('base')) return heightField.value
  if (name.includes('base')) return baseField.value
  return heightField.value
}

function setHeightExpr(value: unknown) {
  if (!layer.value) return
  if (layer.value.type === 'building') store.setLayerLayout(layer.value.id, 'building-height', value)
  else store.setLayerPaint(layer.value.id, 'fill-extrusion-height', value)
}

function setBaseExpr(value: unknown) {
  if (!layer.value) return
  if (layer.value.type === 'building') store.setLayerLayout(layer.value.id, 'building-base', value)
  else store.setLayerPaint(layer.value.id, 'fill-extrusion-base', value)
}

function applyHeightField() {
  const name = heightField.value.trim() || 'height'
  const current = heightValue()
  if (Array.isArray(current)) setHeightExpr(replaceGetName(current, name))
  else setHeightExpr(['get', name])
}

function applyBaseField() {
  if (!baseField.value.trim()) {
    setBaseExpr(0)
    return
  }
  const current = baseValue()
  if (Array.isArray(current)) setBaseExpr(replaceGetName(current, baseField.value))
  else setBaseExpr(['coalesce', ['get', baseField.value.trim()], 0])
}

function rename(id: string) {
  if (!layer.value || !id) return
  store.updateLayer(layer.value.id, { id })
}

function onFilter(text: string) {
  if (!layer.value) return
  if (!text.trim()) {
    store.updateLayer(layer.value.id, { filter: undefined })
    return
  }
  try {
    store.updateLayer(layer.value.id, { filter: JSON.parse(text) })
  } catch {
    ElMessage.error('filter JSON 无效')
  }
}

function applyGrow() {
  if (!layer.value) return
  const trans = transitionValue(animDuration.value, animDelay.value)
  if (layer.value.type === 'fill-extrusion') {
    Object.entries(buildingGrowPaint(heightField.value, baseField.value, zoomFrom.value, zoomTo.value)).forEach(
      ([k, v]) => store.setLayerPaint(layer.value.id, k, v),
    )
    store.setLayerPaint(layer.value.id, 'fill-extrusion-height-transition', trans)
    store.setLayerPaint(layer.value.id, 'fill-extrusion-base-transition', trans)
  } else {
    Object.entries(buildingGrowLayout(heightField.value, baseField.value, zoomFrom.value, zoomTo.value)).forEach(
      ([k, v]) => store.setLayerLayout(layer.value.id, k, v),
    )
    store.setLayerLayout(layer.value.id, 'building-height-transition', trans)
    store.setLayerLayout(layer.value.id, 'building-base-transition', trans)
    store.setLayerPaint(layer.value.id, 'building-vertical-scale-transition', trans)
  }
  ElMessage.success(`已写入升起：${zoomFrom.value}→${zoomTo.value}，过渡 ${animDuration.value}ms`)
}

function applyBuildingTransition() {
  if (!layer.value) return
  const trans = transitionValue(animDuration.value, animDelay.value)
  if (layer.value.type === 'fill-extrusion') {
    store.setLayerPaint(layer.value.id, 'fill-extrusion-height-transition', trans)
    store.setLayerPaint(layer.value.id, 'fill-extrusion-base-transition', trans)
    store.setLayerPaint(layer.value.id, 'fill-extrusion-vertical-scale-transition', trans)
  } else {
    store.setLayerLayout(layer.value.id, 'building-height-transition', trans)
    store.setLayerLayout(layer.value.id, 'building-base-transition', trans)
    store.setLayerPaint(layer.value.id, 'building-vertical-scale-transition', trans)
  }
  ElMessage.success(`已写入过渡 ${animDuration.value}ms / 延迟 ${animDelay.value}ms`)
}

function setTransition(name: string, value: unknown) {
  if (!layer.value) return
  if (layoutFields.value.some((f) => f.name === name)) store.setLayerLayout(layer.value.id, name, value)
  else store.setLayerPaint(layer.value.id, name, value)
}
</script>

<style scoped lang="less">
.layer-form {
  padding-bottom: 24px;
}
.height-fields {
  margin-bottom: 12px;
}
.presets {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.num-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.field-tip,
.preset-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.45;
  margin-top: 4px;
}
.anim-help {
  margin-bottom: 12px;
}
.anim-help-body {
  font-size: 12px;
  line-height: 1.5;
  p {
    margin: 0 0 6px;
  }
  p:last-child {
    margin-bottom: 0;
  }
  code {
    font-size: 11px;
    background: #f4f4f5;
    padding: 0 4px;
    border-radius: 3px;
  }
}
</style>
