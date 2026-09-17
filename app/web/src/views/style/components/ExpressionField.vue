<template>
  <div class="expr-field">
    <div class="expr-field-head">
      <div class="expr-field-title">
        <span class="expr-field-label">{{ field.label || field.name }}</span>
        <span class="expr-field-name">{{ field.name }}</span>
      </div>
      <el-select v-model="mode" size="small" style="width: 110px" @change="onModeChange">
        <el-option label="常量" value="const" />
        <el-option label="字段" value="get" />
        <el-option label="缩放动画" value="zoom" />
        <el-option label="表达式" value="expr" />
      </el-select>
      <el-button v-if="hasValue" link type="danger" size="small" @click="clear">清除</el-button>
    </div>
    <div v-if="field.doc" class="expr-field-doc">{{ field.doc }}</div>
    <div class="expr-field-hint">{{ modeHint }}</div>

    <template v-if="mode === 'const'">
      <el-color-picker
        v-if="field.type === 'color'"
        :model-value="typeof modelValue === 'string' ? modelValue : '#000000'"
        show-alpha
        @change="emitValue"
      />
      <el-switch
        v-else-if="field.type === 'boolean'"
        :model-value="Boolean(modelValue ?? field.default)"
        @change="emitValue"
      />
      <el-select
        v-else-if="field.type === 'enum'"
        :model-value="(modelValue as string) ?? (field.default as string)"
        clearable
        filterable
        size="small"
        @change="emitValue"
      >
        <el-option v-for="item in field.values || []" :key="item" :label="item" :value="item" />
      </el-select>
      <el-input-number
        v-else-if="field.type === 'number'"
        :model-value="typeof modelValue === 'number' ? modelValue : Number(field.default ?? 0)"
        :min="field.minimum"
        :max="field.maximum"
        :step="step"
        size="small"
        controls-position="right"
        style="width: 100%"
        @change="emitValue"
      />
      <div v-else-if="isTransition" class="transition-row">
        <el-input-number
          :model-value="transition.duration"
          :min="0"
          size="small"
          controls-position="right"
          @change="(v: number) => emitValue({ ...transition, duration: v })"
        />
        <span>时长 ms</span>
        <el-input-number
          :model-value="transition.delay"
          :min="0"
          size="small"
          controls-position="right"
          @change="(v: number) => emitValue({ ...transition, delay: v })"
        />
        <span>延迟 ms</span>
      </div>
      <el-input
        v-else
        :model-value="constText"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 4 }"
        size="small"
        @change="onConstText"
      />
    </template>

    <el-input
      v-else-if="mode === 'get'"
      :model-value="getField"
      size="small"
      placeholder="矢量属性名，与数据字段一致"
      @change="(v: string) => emitValue(v ? ['get', v] : undefined)"
    />

    <div v-else-if="mode === 'zoom'" class="zoom-stops">
      <div class="zoom-stop-head">缩放级别 → 属性值（随 zoom 插值）</div>
      <div v-for="(stop, i) in zoomStops" :key="i" class="zoom-stop">
        <span class="zoom-stop-tag">级别</span>
        <el-input-number
          :model-value="stop.zoom"
          size="small"
          controls-position="right"
          @change="(v: number) => updateStop(i, { ...stop, zoom: v })"
        />
        <span class="zoom-stop-tag">值</span>
        <el-input :model-value="stringifyStop(stop.value)" size="small" :placeholder="zoomValuePlaceholder" @change="(v: string) => updateStopValue(i, v)" />
        <el-button link type="danger" @click="removeStop(i)">x</el-button>
      </div>
      <el-button size="small" @click="addStop">添加停靠</el-button>
    </div>

    <el-input
      v-else
      :model-value="exprText"
      type="textarea"
      :autosize="{ minRows: 3, maxRows: 8 }"
      size="small"
      @change="onExprText"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SpecField } from '@/views/style/lib/types'

const props = defineProps<{
  field: SpecField
  modelValue: unknown
  defaultGetField?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: unknown): void
}>()

const mode = ref<'const' | 'get' | 'zoom' | 'expr'>('const')
const exprText = ref('')
const zoomStops = ref<{ zoom: number; value: unknown }[]>([
  { zoom: 15, value: 0 },
  { zoom: 16, value: ['get', 'height'] },
])
const defaultGetField = computed(() => props.defaultGetField || 'height')
const zoomValuePlaceholder = computed(() => `数字或 ["get","${defaultGetField.value}"]`)

const isTransition = computed(() => props.field.name.endsWith('-transition'))
const hasValue = computed(() => props.modelValue !== undefined)
const modeHint = computed(() => {
  if (isTransition.value) return '改常量值时才会播放这段过渡；绑字段的高度一般不会用 transition。'
  if (mode.value === 'const') return '固定值，适合颜色、开关、过渡时长。'
  if (mode.value === 'get') return '从矢量要素属性取值，字段名须和 source-layer 里的属性一致。'
  if (mode.value === 'zoom') return `随地图缩放插值。建筑升起：15→0，16→["get","${defaultGetField.value}"]。`
  return '标准 Mapbox 表达式数组，例如 ["interpolate",["linear"],["zoom"],15,0,16,["get","height"]]。'
})
const step = computed(() => {
  if (props.field.maximum !== undefined && props.field.maximum <= 1) return 0.01
  return 1
})

const transition = computed(() => {
  const v = props.modelValue as any
  return {
    duration: typeof v?.duration === 'number' ? v.duration : 300,
    delay: typeof v?.delay === 'number' ? v.delay : 0,
  }
})

const getField = computed(() => {
  const v = props.modelValue
  if (Array.isArray(v) && v[0] === 'get') return String(v[1] ?? '')
  return ''
})

const constText = computed(() => {
  if (props.modelValue === undefined) return stringifyStop(props.field.default)
  if (typeof props.modelValue === 'string') return props.modelValue
  try {
    return JSON.stringify(props.modelValue)
  } catch {
    return String(props.modelValue)
  }
})

function detectMode(value: unknown): 'const' | 'get' | 'zoom' | 'expr' {
  if (value === undefined || value === null) return 'const'
  if (!Array.isArray(value)) return 'const'
  if (value[0] === 'get') return 'get'
  if (value[0] === 'interpolate' && Array.isArray(value[2]) && value[2][0] === 'zoom') return 'zoom'
  return 'expr'
}

function parseZoomStops(value: unknown) {
  if (!Array.isArray(value) || value[0] !== 'interpolate') return
  const stops: { zoom: number; value: unknown }[] = []
  for (let i = 3; i < value.length; i += 2) {
    stops.push({ zoom: Number(value[i]), value: value[i + 1] })
  }
  if (stops.length) zoomStops.value = stops
}

function syncFromValue() {
  mode.value = detectMode(props.modelValue)
  exprText.value = props.modelValue === undefined ? '' : JSON.stringify(props.modelValue, null, 2)
  if (mode.value === 'zoom') parseZoomStops(props.modelValue)
}

watch(() => props.modelValue, syncFromValue, { immediate: true })

function emitValue(value: unknown) {
  emit('update:modelValue', value)
}

function clear() {
  emitValue(undefined)
}

function onModeChange() {
  if (mode.value === 'get') emitValue(['get', defaultGetField.value])
  else if (mode.value === 'zoom') {
    zoomStops.value = [
      { zoom: 15, value: 0 },
      { zoom: 16, value: ['get', defaultGetField.value] },
    ]
    emitZoom()
  }
  else if (mode.value === 'expr') emitValue(props.modelValue ?? [])
  else emitValue(props.field.default)
}

function stringifyStop(value: unknown) {
  if (value === undefined || value === null) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function parseStop(text: string) {
  const t = text.trim()
  if (t === '') return 0
  if (t.startsWith('[') || t.startsWith('{')) {
    try {
      return JSON.parse(t)
    } catch {
      return t
    }
  }
  const n = Number(t)
  return Number.isNaN(n) ? t : n
}

function emitZoom() {
  const expr: unknown[] = ['interpolate', ['linear'], ['zoom']]
  for (const stop of zoomStops.value) {
    expr.push(stop.zoom, stop.value)
  }
  emitValue(expr)
}

function updateStop(i: number, stop: { zoom: number; value: unknown }) {
  zoomStops.value[i] = stop
  emitZoom()
}

function updateStopValue(i: number, text: string) {
  zoomStops.value[i] = { ...zoomStops.value[i], value: parseStop(text) }
  emitZoom()
}

function addStop() {
  const last = zoomStops.value[zoomStops.value.length - 1]
  zoomStops.value.push({ zoom: (last?.zoom ?? 14) + 1, value: last?.value ?? 0 })
  emitZoom()
}

function removeStop(i: number) {
  zoomStops.value.splice(i, 1)
  emitZoom()
}

function onConstText(text: string) {
  emitValue(parseStop(text))
}

function onExprText(text: string) {
  try {
    emitValue(JSON.parse(text))
  } catch {
    exprText.value = text
  }
}
</script>

<style scoped lang="less">
.expr-field {
  margin-bottom: 10px;
  &-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }
  &-title {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  &-label {
    font-size: 13px;
    color: #303133;
    font-weight: 600;
  }
  &-name {
    font-size: 11px;
    color: #909399;
    word-break: break-all;
  }
  &-doc {
    font-size: 12px;
    color: #606266;
    margin-bottom: 4px;
    line-height: 1.45;
  }
  &-hint {
    font-size: 11px;
    color: #909399;
    margin-bottom: 6px;
    line-height: 1.35;
  }
}
.transition-row,
.zoom-stop {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}
.zoom-stop-head,
.zoom-stop-tag {
  font-size: 11px;
  color: #909399;
}
.zoom-stop-head {
  margin-bottom: 4px;
}
.zoom-stops {
  display: flex;
  flex-direction: column;
}
</style>
