<template>
  <div class="category-editor">
    <div class="category-editor-bar">
      <el-button size="small" :icon="Plus" @click="addRow">新增分类</el-button>
      <el-button size="small" type="danger" plain :disabled="!modelValue.length" @click="clearAll">清空分类</el-button>
    </div>
    <div v-if="!modelValue.length" class="category-editor-empty">
      手动添加分类。先选字段，再从该字段的取值里勾选；一组分类可加多条条件（同时满足）。
    </div>
    <div v-for="(row, index) in modelValue" :key="row.id || index" class="category-card">
      <el-row :gutter="8" align="middle">
        <el-col :span="8">
          <el-input v-model="row.name" size="small" placeholder="分类名称" />
        </el-col>
        <el-col :span="4">
          <el-select v-model="row.geom_type" size="small" placeholder="几何不限">
            <el-option label="不限" value="" />
            <el-option label="点" value="point" />
            <el-option label="线" value="line" />
            <el-option label="面" value="polygon" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-input-number v-model="row.minZoom" size="small" :min="0" :max="22" controls-position="right" />
        </el-col>
        <el-col :span="4">
          <el-input-number v-model="row.maxZoom" size="small" :min="0" :max="22" controls-position="right" />
        </el-col>
        <el-col :span="3">
          <el-switch v-model="row.show" active-text="show" />
        </el-col>
      </el-row>
      <div class="category-card-label">minZoom / maxZoom · 条件之间为「且」；同一字段多个取值，正向为「或」，「非」为排除这些值</div>
      <div v-for="(cond, cIndex) in row.conditions" :key="cIndex" class="category-cond">
        <el-select
          v-model="cond.key"
          filterable
          allow-create
          default-first-option
          size="small"
          placeholder="选择字段"
          class="category-cond-key"
          @change="onKeyChange(cond)"
        >
          <el-option v-for="key in keys" :key="key" :label="key" :value="key" />
        </el-select>
        <el-select v-model="cond.exclude" size="small" class="category-cond-op">
          <el-option label="是" :value="false" />
          <el-option label="非" :value="true" />
        </el-select>
        <el-select
          v-model="cond.values"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          collapse-tags-tooltip
          size="small"
          :placeholder="valuePlaceholder(cond)"
          class="category-cond-value"
          :disabled="!cond.key"
          :loading="!!loadingValues[cond.key]"
        >
          <el-option
            v-for="val in valuesOf(cond.key)"
            :key="String(val)"
            :label="String(val)"
            :value="String(val)"
          />
        </el-select>
        <el-icon class="category-editor-remove" @click="removeCondition(row, cIndex)"><Delete /></el-icon>
      </div>
      <el-button size="small" :icon="Plus" text type="primary" @click="addCondition(row)">添加条件</el-button>
      <el-button size="small" type="danger" text @click="removeRow(index)">删除分类</el-button>
    </div>
    <div class="category-editor-tip">show=false 的分类以后生成 mbtiles 时不会写入；地图里仍可勾选查看。</div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getFeaturePropertiesKeys, getFeaturePropertiesValues } from '@/api/postgis'

const props = defineProps<{
  modelValue: any[]
  datasetId?: number | null
}>()

const emit = defineEmits(['update:modelValue'])
const keys = ref<string[]>([])
const valuesMap = ref<Record<string, string[]>>({})
const loadingValues = ref<Record<string, boolean>>({})

onMounted(() => {
  loadKeys()
})

watch(
  () => props.datasetId,
  () => {
    keys.value = []
    valuesMap.value = {}
    loadKeys()
  },
)

watch(
  () => props.modelValue,
  (list) => {
    for (const row of list || []) {
      if (!Array.isArray(row.conditions) || !row.conditions.length) {
        row.conditions = [{ key: '', values: [] }]
      }
      for (const cond of row.conditions) {
        if (!Array.isArray(cond.values)) cond.values = []
        if (cond.exclude == null) cond.exclude = false
        if (cond?.key) loadValues(cond.key)
      }
    }
  },
  { deep: true, immediate: true },
)

async function loadKeys() {
  if (!props.datasetId) return
  const res: any = await getFeaturePropertiesKeys({ datasets_id: props.datasetId })
  keys.value = Array.isArray(res) ? res : []
}

async function loadValues(key: string) {
  if (!props.datasetId || !key || valuesMap.value[key] || loadingValues.value[key]) return
  loadingValues.value = { ...loadingValues.value, [key]: true }
  try {
    const res: any = await getFeaturePropertiesValues({
      datasets_id: props.datasetId,
      key,
    })
    const list = Array.isArray(res) ? res.map((item: any) => String(item)) : []
    valuesMap.value = { ...valuesMap.value, [key]: list }
  } finally {
    loadingValues.value = { ...loadingValues.value, [key]: false }
  }
}

function valuesOf(key: string) {
  return valuesMap.value[key] || []
}

function valuePlaceholder(cond: any) {
  if (!cond.key) return '先选字段'
  if (cond.exclude) return '排除这些取值，不选表示没有该字段'
  return '选择取值，不选表示只要有该字段'
}

function onKeyChange(cond: any) {
  cond.values = []
  if (cond.exclude == null) cond.exclude = false
  if (cond.key) loadValues(cond.key)
}

function addRow() {
  emit('update:modelValue', [
    ...props.modelValue,
    {
      id: `custom-${Date.now()}`,
      name: '',
      geom_type: '',
      conditions: [{ key: '', values: [], exclude: false }],
      minZoom: 0,
      maxZoom: 22,
      show: true,
    },
  ])
}

function removeRow(index: number) {
  const next = props.modelValue.slice()
  next.splice(index, 1)
  emit('update:modelValue', next)
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('确定清空当前全部分类？', '清空分类', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
    emit('update:modelValue', [])
    ElMessage.success('已清空分类')
  } catch {
    // cancel
  }
}

function addCondition(row: any) {
  if (!Array.isArray(row.conditions)) row.conditions = []
  row.conditions.push({ key: '', values: [], exclude: false })
}

function removeCondition(row: any, index: number) {
  row.conditions.splice(index, 1)
  if (!row.conditions.length) {
    row.conditions.push({ key: '', values: [], exclude: false })
  }
}
</script>

<style scoped lang="less">
.category-editor {
  max-height: 80vh;
  overflow: auto;
  padding-right: 4px;
}
.category-editor-bar {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
}
.category-editor-empty,
.category-editor-tip,
.category-card-label {
  color: #909399;
  font-size: 12px;
}
.category-editor-empty {
  margin-bottom: 8px;
}
.category-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
}
.category-card-label {
  margin: 8px 0 6px;
}
.category-cond {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.category-cond-key {
  width: 160px;
}
.category-cond-op {
  width: 72px;
  flex-shrink: 0;
}
.category-cond-value {
  flex: 1;
}
.category-editor-remove {
  cursor: pointer;
  color: #f56c6c;
  flex-shrink: 0;
}
.category-editor-tip {
  margin-top: 8px;
}
</style>
