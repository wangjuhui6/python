<template>
  <el-card class="page">
    <template #header>
      <span>图片转 MBTiles</span>
    </template>

    <el-alert
      class="hint"
      type="info"
      :closable="false"
      title="选择放有 json 和图片的文件夹。json 里每张图要有四个角（左上、右上、右下、左下）和像素尺寸。级别填 12 和 16，就会生成 12 到 16 级。结果写在这个文件夹里，文件名与 json 相同。"
    />

    <div class="form">
      <Upload
        v-model:value="form.folder"
        type="folder"
        label="图片文件夹"
        placeholder="请选择文件夹"
      />
      <div class="row">
        <span>最小级别</span>
        <el-input-number v-model="form.minzoom" :min="0" :max="22" :step="1" />
        <span>最大级别</span>
        <el-input-number v-model="form.maxzoom" :min="0" :max="22" :step="1" />
      </div>
      <div class="actions">
        <el-button type="primary" :loading="running" :disabled="running" @click="generate">
          生成 {{ form.minzoom }}–{{ form.maxzoom }} 级
        </el-button>
      </div>
    </div>

    <pre v-if="summary" class="result">{{ summary }}</pre>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import Upload from '@/components/Upload/index.vue'
import { imageToMbtiles } from '@/api/gdal'

const form = ref({
  folder: '',
  minzoom: 12,
  maxzoom: 16,
})

const running = ref(false)
const summary = ref('')

async function generate() {
  if (!form.value.folder) {
    ElMessage.error('请选择文件夹')
    return
  }
  if (form.value.minzoom == null || form.value.maxzoom == null) {
    ElMessage.error('请填写级别')
    return
  }
  if (form.value.minzoom > form.value.maxzoom) {
    ElMessage.error('最小级别不能大于最大级别')
    return
  }
  running.value = true
  summary.value = ''
  try {
    const data: any = await imageToMbtiles({
      folder: form.value.folder,
      minzoom: form.value.minzoom,
      maxzoom: form.value.maxzoom,
    })
    const [west, south, east, north] = data.bounds || []
    summary.value = [
      `已写入 ${data.output}`,
      `图片 ${data.images} 张，瓦片 ${data.tiles} 个，级别 ${data.minzoom}–${data.maxzoom}`,
      west == null ? '' : `范围 ${Number(west).toFixed(6)},${Number(south).toFixed(6)},${Number(east).toFixed(6)},${Number(north).toFixed(6)}`,
    ].filter(Boolean).join('\n')
    ElMessage.success('已生成')
  } catch (error) {
    ElMessage.error(typeof error === 'string' ? error : '生成失败')
  } finally {
    running.value = false
  }
}
</script>

<style scoped lang="less">
.page {
  max-width: 760px;
}
.hint {
  margin-bottom: 16px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.result {
  margin-top: 16px;
  padding: 12px;
  background: #111;
  color: #d6d6d6;
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.5;
}
</style>
