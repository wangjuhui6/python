<template>
  <div class="vector">
    <el-card>
      <template #header>
        <span>geoJSON转Shapefile</span>
      </template>
      <div class="upload-container">
        <Upload
          v-model:value="oneData.file"
          type="file"
          dataType="geoJSON"
          label="选择文件"
          placeholder="请选择geoJSON文件"
        />
        <Upload
          v-model:value="oneData.savePath"
          type="folder"
          dataType="shapefile"
          label="选择路径"
          placeholder="请选择保存路径"
        />
      </div>
      <!-- <template #footer>Footer content</template> -->
    </el-card>
    <!-- <el-card>
      <template #header>
        <span>osm pbf转mbtiles</span>
      </template>
      <div class="upload-container">
        <Upload
          v-model:value="twoData.file"
          type="file"
          dataType="osmPbf"
          label="选择文件"
          placeholder="请选择osm pbf文件"
        />
        <Upload
          v-model:value="twoData.savePath"
          type="savePath"
          dataType="mbtiles"
          label="选择路径"
          placeholder="请选择保存路径"
        />
      </div>
    </el-card> -->
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { ElMessage } from 'element-plus'
import { geojsonToShp, osmPbfToMbtiles } from '@/api/gdal'

// geoJSON转Shapefile
const oneData = reactive({
  file: '',
  savePath: '',
})

watch(() => oneData, async (newVal) => {
  if (newVal.file && newVal.savePath) {
    await geojsonToShp({
      inputFile: newVal.file,
      outputPath: newVal.savePath,
    })
    ElMessage.success('添加完成')
    oneData.file = ''
    oneData.savePath = ''
  }
}, { deep: true })

// osm pbf转mbtiles
const twoData = reactive({
  file: '',
  savePath: '',
})

watch(() => twoData, async (newVal) => {
  if (newVal.file && newVal.savePath) {
    await osmPbfToMbtiles({
      inputFile: newVal.file,
      outputPath: newVal.savePath,
    })
    ElMessage.success('添加完成')
    twoData.file = ''
    twoData.savePath = ''
  }
}, { deep: true })
</script>

<style scoped lang="less">
.vector{
  display: flex;
  align-items: start;
  gap: 20px;
  flex-wrap: wrap;
}
.upload-container{
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 10px;
}
</style>
