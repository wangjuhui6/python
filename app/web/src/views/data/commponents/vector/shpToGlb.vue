<template>
  <el-card>
    <template #header>
      <span>shp生成白膜</span>
    </template>
    <div class="upload-container">
      <Upload
        v-model:value="data.file"
        type="file"
        dataType="shp"
        label="选择文件"
        placeholder="请选择shp文件"
      />
      <Upload
        v-model:value="data.savePath"
        type="folder"
        dataType="shapefile"
        label="选择路径"
        placeholder="请选择保存路径"
      />
      <div class="height-container">
        <div>建筑高度</div>
        <el-select v-model="data.heightType" style="width: 100px">
          <el-option v-for="item in heightOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-input-number style="width: 100px" v-if="data.heightType === 'fixed'" v-model="data.height" :min="1" />
        <div v-else-if="data.heightType === 'heightField'" style="display: flex; align-items: center; gap: 10px;">
          <el-select v-model="data.heightField" style="width: 100px" placeholder="高度字段">
            <el-option v-for="item in heightFieldOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          *
          <el-input-number style="width: 100px" v-model="data.heightMultiple" :min="1" />
        </div>
      </div>
      <div class="height-container">
        <div>底部高度</div>
        <el-select v-model="data.bottomHeightType" style="width: 100px">
          <el-option v-for="item in heightOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-input-number style="width: 100px" v-if="data.bottomHeightType === 'fixed'" v-model="data.bottomHeight" :min="0" />
        <div v-else-if="data.bottomHeightType === 'heightField'" style="display: flex; align-items: center; gap: 10px;">
          <el-select v-model="data.bottomHeightField" style="width: 100px" placeholder="高度字段">
            <el-option v-for="item in heightFieldOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          *
          <el-input-number style="width: 100px" v-model="data.bottomHeightMultiple" :min="1" />
        </div>
      </div>
      <el-button type="primary" @click="save">生成白膜</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { getShpFields, generateGlb } from '@/api/gdal'
import { ElMessage } from 'element-plus'

const heightOptions = ref([
  {
    label: '固定高度',
    value: 'fixed',
  },
  {
    label: '高度字段',
    value: 'heightField',
  },
])

const heightFieldOptions = ref<any[]>([]);

const data = reactive({
  file: '',
  savePath: '',
  heightType: 'fixed',
  height: 10,
  heightField: '',
  heightMultiple: 1,
  bottomHeightType: 'fixed',
  bottomHeight: 0,
  bottomHeightField: '',
  bottomHeightMultiple: 1,
})

watch(() => data.file, async (newVal) => {
  if (newVal) {
    const res: any = await getShpFields({ file: newVal })
    heightFieldOptions.value = res.map((item: string) => ({
      label: item,
      value: item,
    }))
  }
}, { immediate: true })

async function save() {
  if (!data.file || !data.savePath) {
    ElMessage.error('请选择文件和保存路径')
    return
  }
  const res: any = await generateGlb(data as any)
  if (res.code === 200) {
    ElMessage.success('生成白膜成功')
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
</style>
