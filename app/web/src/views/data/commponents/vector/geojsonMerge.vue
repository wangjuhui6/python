<template>
  <el-card>
    <template #header>
      <span>geojson合并</span>
    </template>
    <div class="upload-container">
      <el-button type="primary" @click="handleSelectFiles">添加</el-button>
      <template v-for="(, index) in data.files" :key="index">
        <Upload
          v-model:value="data.files[index]"
          type="file"
          dataType="geojson"
          label="选择文件"
          placeholder="请选择geojson文件"
        />
      </template>
      <Upload
        v-model:value="data.savePath"
        type="savePathAndFileName"
        dataType="json"
        label="保存路径及文件名"
        placeholder="请选择保存路径及文件名"
      />
      <el-button type="primary" @click="handleGeojsonMerge">合并</el-button>
    </div>
  </el-card>
</template>

<!-- 能选择多个文件 -->

<script setup lang="ts">
import { reactive } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { ElMessage } from 'element-plus'
import { readMultipleFiles, generateFile } from '@/api/gdal'
import * as turf from '@turf/turf'

const data = reactive<{ files: any[], savePath: string }>({
  files: [''],
  savePath: '',
})

const handleSelectFiles = () => {
  data.files.push('')
}

const handleGeojsonMerge = async () => {
  if (!data.files.length || !data.savePath) {
    ElMessage.error('请选择文件和保存路径')
    return
  }
  const res: any = await readMultipleFiles({ files: data.files.filter(file => file !== '') })
  const content: any = []
  res.forEach((item: any) => {
    const newData = JSON.parse(item)
    if (newData.type === 'FeatureCollection') {
      newData.features.forEach((feature: any) => {
        delete feature.properties.id
      })
      content.push(...newData.features)
    } else {
      delete newData.properties.id
      content.push(newData)
    }
  })
  const merged = turf.featureCollection(content)
  const res1: any = await generateFile({ file_path: data.savePath, content: JSON.stringify(merged) })
  if (res1) {
    ElMessage.success('合并成功')
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