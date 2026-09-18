<template>
  <el-dialog
    v-model="dialogVisible"
    title="添加数据"
    width="700"
    :before-close="handleClose"
  >
    <el-form :model="formData" label-width="120px" :rules="rules" ref="formRef">
      <el-form-item label="数据类型" prop="data_type">
        <el-select v-model="formData.data_type" :options="DATA_TYPE_OPTIONS" placeholder="请选择数据类型" />
      </el-form-item>
      <el-form-item label="文件路径" v-if="formData.data_type" prop="file_path">
        <Upload v-model:value="formData.file_path" :type="DATA_TYPE_OPTIONS_OBJ[formData.data_type].type" :dataType="DATA_TYPE_OPTIONS_OBJ[formData.data_type].dataType" />
      </el-form-item>
      <el-form-item v-if="formData.data_type === 'pbf'">
        <el-alert type="info" :closable="false" show-icon title="全国级 PBF（约 1GB+）导入会在后台批量写入，请保持页面打开，完成后会提示。" />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="loading">
          导入数据
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import Upload from '@/components/Upload/index.vue';
import { importData as importDataApi } from '@/api/postgis';

const DATA_TYPE_OPTIONS = [
  { label: 'PBF', value: 'pbf', type: 'file', dataType: 'osmPbf' },
  // { label: 'XML', value: 'xml' },
  // { label: 'JSON', value: 'json' },
  // { label: 'CSV', value: 'csv' },
  // { label: 'SHP', value: 'shp' },
  // { label: 'GPX', value: 'gpx' },
]

const loading = ref(false);

const rules = reactive({
  data_type: [
    { required: true, message: '请选择数据类型', trigger: 'change' },
  ],
  file_path: [
    { required: true, message: '请选择文件路径', trigger: 'change' },
  ],
})

const DATA_TYPE_OPTIONS_OBJ: any = {}
DATA_TYPE_OPTIONS.forEach((item) => {
  DATA_TYPE_OPTIONS_OBJ[item.value] = item
})

const formRef = ref<any>(null);
const datasets_id = ref<number | null>(null);
const dialogVisible = ref(false);
const formData = ref({
  data_type: '',
  file_path: '',
});

const handleClose = () => {
  dialogVisible.value = false;
};

async function save() {
  await formRef.value.validate()
  loading.value = true;
  try {
    const res = await importDataApi({
      ...formData.value,
      datasets_id: datasets_id.value,
    })
    if (res) {
      ElMessage.success('数据导入成功');
      dialogVisible.value = false;
    } else {
      ElMessage.error('导入数据失败');
    }
  } catch (error) {
    ElMessage.error('导入数据失败');
  } finally {
    loading.value = false;
  }
}

function open(id: number) {
  datasets_id.value = id;
  dialogVisible.value = true;
}
defineExpose({
  open,
});
</script>

<style lang="less" scoped></style>
