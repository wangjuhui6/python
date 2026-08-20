<template>
  <el-card>
    <template #header>
      <span>裁剪3dtiles</span>
    </template>
    <div class="upload-container">
      <Upload
        v-model:value="data.inputPath"
        type="folder"
        dataType="shapefile"
        label="输入路径"
        placeholder="请选择输入路径"
      />
      <Upload
        v-model:value="data.outputPath"
        type="folder"
        dataType="shapefile"
        label="保存路径"
        placeholder="请选择保存路径"
      />
      <Upload
        v-model:value="data.clipPolygon"
        type="file"
        dataType="json"
        label="裁剪json"
        placeholder="请选择裁剪范围"
      />
      <div class="mode-container">
        <div>裁剪方式</div>
        <el-select v-model="data.mode" style="width: 200px">
          <el-option v-for="item in modeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>
      <div class="mode-container">
        <div>新模式</div>
        <el-switch v-model="data.isNew" />
      </div>
      <el-button type="primary" @click="save">裁剪</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { clip3dTiles } from '@/api/gdal'
import { ElMessage } from 'element-plus'


const data = reactive({
  inputPath: '',
  outputPath: '',
  clipPolygon: '',
  mode: 'remove',
  isNew: false
})

const modeOptions = ref([
  {
    label: '保留',
    value: 'keep',
  },
  {
    label: '删除',
    value: 'remove',
  },
])

async function save() {
  if (!data.inputPath || !data.outputPath || !data.clipPolygon) {
    ElMessage.error('请选择输入路径、输出路径和裁剪范围')
    return
  }
  const res: any = await clip3dTiles(data as any)
  if (res.code === 200) {
    ElMessage.success('裁剪成功')
  } else {
    ElMessage.error(res.msg)
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
.height-container{
  width: 460px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.mode-container{
  width: 460px;
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
