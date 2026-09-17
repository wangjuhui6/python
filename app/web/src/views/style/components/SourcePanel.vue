<template>
  <div class="source-panel">
    <el-form label-position="top" size="small">
      <el-form-item label="数据源 ID">
        <el-input v-model="form.id" />
      </el-form-item>
      <el-form-item label="类型">
        <el-select v-model="form.type" style="width: 100%">
          <el-option label="vector" value="vector" />
          <el-option label="raster" value="raster" />
          <el-option label="raster-dem" value="raster-dem" />
          <el-option label="geojson" value="geojson" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.type !== 'geojson'" label="TileJSON / mbtiles URL">
        <el-input v-model="form.url" placeholder="mbtiles://data.mbtiles 或 https://.../tiles.json" />
      </el-form-item>
      <el-form-item v-if="form.type !== 'geojson'" label="tiles 地址（每行一个）">
        <el-input v-model="form.tiles" type="textarea" :rows="3" placeholder="https://example.com/{z}/{x}/{y}.pbf" />
      </el-form-item>
      <el-form-item v-if="form.type === 'geojson'" label="GeoJSON URL 或内联 JSON">
        <el-input v-model="form.data" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="minzoom / maxzoom">
        <div style="display: flex; gap: 8px">
          <el-input-number v-model="form.minzoom" :min="0" :max="24" />
          <el-input-number v-model="form.maxzoom" :min="0" :max="24" />
        </div>
      </el-form-item>
      <el-button type="primary" size="small" @click="save">保存数据源</el-button>
    </el-form>

    <div class="source-list">
      <div v-for="(source, id) in store.style.sources" :key="id" class="source-item" @click="edit(String(id), source)">
        <div>
          <b>{{ id }}</b>
          <span class="muted"> {{ source.type }}</span>
        </div>
        <el-button link type="danger" size="small" @click.stop="store.removeSource(String(id))">删除</el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'

const store = useStyleEditorStore()
const form = reactive({
  id: 'openmaptiles',
  type: 'vector',
  url: 'mbtiles://data.mbtiles',
  tiles: '',
  data: '',
  minzoom: 0,
  maxzoom: 14,
  editingId: '',
})

function buildSource() {
  const source: any = { type: form.type }
  if (form.type === 'geojson') {
    const text = form.data.trim()
    if (text.startsWith('{') || text.startsWith('[')) source.data = JSON.parse(text)
    else source.data = text || { type: 'FeatureCollection', features: [] }
  } else {
    if (form.url) source.url = form.url
    const tiles = form.tiles
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    if (tiles.length) source.tiles = tiles
    source.minzoom = form.minzoom
    source.maxzoom = form.maxzoom
  }
  return source
}

function save() {
  if (!form.id) {
    ElMessage.error('请填写数据源 ID')
    return
  }
  try {
    const source = buildSource()
    if (form.editingId && form.editingId !== form.id) store.updateSource(form.editingId, source, form.id)
    else store.addSource(form.id, source)
    form.editingId = form.id
    ElMessage.success('数据源已更新')
  } catch (e: any) {
    ElMessage.error(e?.message || '数据源格式错误')
  }
}

function edit(id: string, source: any) {
  form.id = id
  form.editingId = id
  form.type = source.type || 'vector'
  form.url = source.url || ''
  form.tiles = Array.isArray(source.tiles) ? source.tiles.join('\n') : ''
  form.data = typeof source.data === 'string' ? source.data : JSON.stringify(source.data || '', null, 2)
  form.minzoom = source.minzoom ?? 0
  form.maxzoom = source.maxzoom ?? 14
}
</script>

<style scoped lang="less">
.source-list {
  margin-top: 12px;
}
.source-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #ebeef5;
  cursor: pointer;
  font-size: 12px;
}
.muted {
  color: #909399;
}
</style>
