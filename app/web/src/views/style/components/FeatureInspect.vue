<template>
  <div v-if="store.pickedFeatures.length" class="inspect">
    <div class="inspect-head">
      <span>点击要素属性</span>
      <el-button link size="small" @click="store.clearPickedFeatures()">关闭</el-button>
    </div>
    <el-select
      v-if="store.pickedFeatures.length > 1"
      :model-value="store.pickedIndex"
      size="small"
      style="width: 100%; margin-bottom: 8px"
      @change="onPickLayer"
    >
      <el-option
        v-for="(item, index) in store.pickedFeatures"
        :key="index"
        :label="`${item.layerId}${item.sourceLayer ? ' · ' + item.sourceLayer : ''}`"
        :value="index"
      />
    </el-select>
    <div class="inspect-meta">
      图层 {{ current?.layerId }}
      <span v-if="current?.sourceLayer"> / {{ current.sourceLayer }}</span>
    </div>
    <div v-if="rows.length" class="inspect-list">
      <div v-for="row in rows" :key="row.key" class="inspect-row">
        <div class="inspect-key" :title="'点击复制字段名'" @click="copyKey(row.key)">{{ row.key }}</div>
        <div class="inspect-val" :title="row.text">{{ row.text }}</div>
        <el-button link type="primary" size="small" @click="store.usePickedField('height', row.key)">高度</el-button>
        <el-button link size="small" @click="store.usePickedField('base', row.key)">底高</el-button>
      </div>
    </div>
    <div v-else class="inspect-empty">该要素没有属性字段</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'

const store = useStyleEditorStore()
const current = computed(() => store.pickedFeatures[store.pickedIndex] || store.pickedFeatures[0] || null)
const rows = computed(() => {
  const props = current.value?.properties || {}
  return Object.keys(props).map((key) => ({
    key,
    text: formatValue(props[key]),
  }))
})

function onPickLayer(index: number) {
  store.pickedIndex = index
  const item = store.pickedFeatures[index]
  if (item?.layerId) store.selectLayer(item.layerId)
}

function formatValue(value: unknown) {
  if (value == null) return 'null'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function copyKey(key: string) {
  try {
    await navigator.clipboard.writeText(key)
    ElMessage.success(`已复制 ${key}`)
  } catch {
    ElMessage.info(key)
  }
}
</script>

<style scoped lang="less">
.inspect {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 4;
  width: 320px;
  max-height: 46%;
  overflow: auto;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid #ebeef5;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  padding: 10px;
}
.inspect-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.inspect-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
}
.inspect-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto;
  gap: 4px;
  align-items: center;
  padding: 4px 0;
  border-bottom: 1px solid #f2f2f2;
  font-size: 12px;
}
.inspect-key {
  color: #409eff;
  cursor: pointer;
  word-break: break-all;
}
.inspect-val {
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inspect-empty {
  font-size: 12px;
  color: #909399;
}
</style>
