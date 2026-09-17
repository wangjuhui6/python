<template>
  <div class="icon-list">
    <el-input v-model="store.keyword" size="small" clearable placeholder="搜索图标名" />
    <div class="count">共 {{ store.icons.length }} 个</div>
    <div v-if="!store.filtered.length" class="empty">暂无图标，请添加或导入精灵图</div>
    <div
      v-for="icon in store.filtered"
      :key="icon.uid"
      :class="['row', { active: icon.uid === store.selectedUid }]"
      @click="store.select(icon.uid)"
    >
      <SpriteThumb :uid="icon.uid" />
      <div class="meta">
        <div class="name">{{ icon.name }}</div>
        <div class="size">{{ icon.width }}×{{ icon.height }} · {{ icon.pixelRatio }}x{{ icon.sdf ? ' · SDF' : '' }}</div>
      </div>
      <el-button link type="danger" @click.stop="store.remove(icon.uid)">删除</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSpriteEditorStore } from '@/stores/spriteEditor'
import SpriteThumb from './SpriteThumb.vue'

const store = useSpriteEditorStore()
</script>

<style scoped lang="less">
.icon-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.count,
.empty {
  font-size: 12px;
  color: #909399;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border-radius: 4px;
  cursor: pointer;
  background: #fff;
  border: 1px solid transparent;
}
.row:hover {
  background: #f5f7fa;
}
.row.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.meta {
  flex: 1;
  min-width: 0;
}
.name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.size {
  font-size: 12px;
  color: #909399;
}
</style>
