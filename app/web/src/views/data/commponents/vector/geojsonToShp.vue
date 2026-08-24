<template>
  <el-card>
    <template #header>
      <span>geojson转shp</span>
    </template>
    <div class="upload-container">
      <Upload
        v-model:value="data.file"
        type="file"
        dataType="geojson"
        label="选择文件"
        placeholder="请选择geojson文件"
      />
      <Upload
        v-model:value="data.savePath"
        type="folder"
        dataType="shp"
        label="选择路径"
        placeholder="请选择保存路径"
      />
      <el-button type="primary" @click="handleGeojsonToShp">转换</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { ElMessage } from 'element-plus'
import { geojsonToShp } from '@/api/gdal'

const data = ref({
  file: '',
  savePath: '',
})

const handleGeojsonToShp = async () => {
  if (!data.value.file || !data.value.savePath) {
    ElMessage.error('请选择文件和保存路径')
    return
  }
  const res: any = await geojsonToShp(data.value)
  if (res) {
    ElMessage.success('转换成功')
  }
}
</script>

<style scoped lang="less">
.upload-container{
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 10px;
}
</style>