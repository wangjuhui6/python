<template>
  <el-card>
    <template #header>
      <span>线去重</span>
    </template>
    <div class="upload-container">
      <Upload
        v-model:value="oneData.file"
        type="file"
        dataType="json"
        label="选择文件"jso
        placeholder="请选择json文件"
      />
      <Upload
        v-model:value="oneData.savePath"
        type="savePathAndFileName"
        dataType="json"
        label="保存路径及文件名"
        placeholder="请选择保存路径及文件名"
      />
      <el-button type="primary" @click="handleLineDeduplication">线去重</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { lineDeduplication } from '@/api/gdal'
import { ElMessage } from 'element-plus'
const oneData = ref({
  file: '',
  savePath: '',
})

const handleLineDeduplication = async () => {
  const res: any = await lineDeduplication({
    inputPath: oneData.value.file,
    outputPath: oneData.value.savePath,
  })
  if (res.code === 200) {
    ElMessage.success('线去重成功')
  } else {
    ElMessage.error(res.msg)
  }
}
</script>

<style scoped>
.upload-container{
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 10px;
}
</style>