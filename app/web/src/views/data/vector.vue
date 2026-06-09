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
    <el-card>
      <template #header>
        <div class="card-header">
          <span>Card name</span>
        </div>
      </template>
      <p v-for="o in 4" :key="o" class="text item">{{ 'List item ' + o }}</p>
      <template #footer>Footer content</template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { geojsonToShp } from '@/api/gdal'

// geoJSON转Shapefile
const oneData = reactive({
  file: '',
  savePath: '',
})

watch(() => oneData, async (newVal) => {
  if (newVal.file && newVal.savePath) {
    const res = await geojsonToShp({
      inputFile: newVal.file,
      outputPath: newVal.savePath,
    })
    console.log(res)
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
