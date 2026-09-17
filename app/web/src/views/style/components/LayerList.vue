<template>
  <div class="layer-list">
    <div class="layer-list-toolbar">
      <el-select v-model="filterSource" clearable placeholder="按数据源" size="small" style="width: 120px">
        <el-option v-for="id in store.sourceIds" :key="id" :label="id" :value="id" />
      </el-select>
      <el-select v-model="newType" size="small" style="width: 120px">
        <el-option v-for="type in LAYER_TYPES" :key="type" :label="LAYER_TYPE_LABELS[type]" :value="type" />
      </el-select>
      <el-button type="primary" size="small" @click="add">添加</el-button>
    </div>
    <div class="layer-list-items">
      <div
        v-for="(layer, index) in filtered"
        :key="layer.id"
        class="layer-item"
        :class="{ active: layer.id === store.selectedLayerId }"
        draggable="true"
        @click="store.selectLayer(layer.id)"
        @dragstart="onDragStart(index)"
        @dragover.prevent
        @drop="onDrop(index)"
      >
        <span class="type-badge">{{ LAYER_TYPE_LABELS[layer.type] || layer.type }}</span>
        <span class="layer-id">{{ layer.id }}</span>
        <el-button link size="small" @click.stop="toggleVis(layer)">
          {{ isHidden(layer) ? '显示' : '隐藏' }}
        </el-button>
        <el-button link size="small" @click.stop="store.duplicateLayer(layer.id)">复制</el-button>
        <el-button link type="danger" size="small" @click.stop="store.removeLayer(layer.id)">删</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { LAYER_TYPE_LABELS, LAYER_TYPES, type LayerType } from '@/views/style/lib/types'
import { defaultLayer } from '@/views/style/lib/layerTemplates'

const store = useStyleEditorStore()
const filterSource = ref('')
const newType = ref<LayerType>('fill')
const dragFrom = ref(-1)

const filtered = computed(() => {
  const layers = store.style.layers
  if (!filterSource.value) return layers.map((layer: any, index: number) => ({ ...layer, _index: index }))
  return layers
    .map((layer: any, index: number) => ({ ...layer, _index: index }))
    .filter((layer: any) => layer.source === filterSource.value)
})

function add() {
  const source = store.sourceIds[0]
  store.addLayer(defaultLayer(newType.value, newType.value, source))
}

function isHidden(layer: any) {
  return layer.layout?.visibility === 'none'
}

function toggleVis(layer: any) {
  store.setLayerLayout(layer.id, 'visibility', isHidden(layer) ? 'visible' : 'none')
}

function onDragStart(index: number) {
  dragFrom.value = filtered.value[index]._index
}

function onDrop(index: number) {
  const to = filtered.value[index]._index
  if (dragFrom.value < 0) return
  store.moveLayer(dragFrom.value, to)
  dragFrom.value = -1
}
</script>

<style scoped lang="less">
.layer-list-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.layer-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  &:hover {
    background: #f5f7fa;
  }
  &.active {
    background: #ecf5ff;
  }
}
.layer-id {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.type-badge {
  font-size: 10px;
  background: #ebeef5;
  border-radius: 3px;
  padding: 1px 4px;
  color: #606266;
  flex-shrink: 0;
}
</style>
