<template>
  <el-dialog
    v-model="dialogVisible"
    title="查看字段"
    width="700"
    :before-close="handleClose"
  >
    <!-- <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save" :loading="loading">
          保存
        </el-button>
      </div>
    </template> -->
  </el-dialog>
</template>

<script lang="ts" setup>
import { ref, reactive } from 'vue';
import { getDatasets as getDatasetsApi,
  getFeaturePropertiesKeys as getFeaturePropertiesKeysApi,
  getFeaturePropertiesValues as getFeaturePropertiesValuesApi
} from '@/api/postgis'

const datasets_id = ref<number | null>(null);
const dialogVisible = ref(false);

const handleClose = () => {
  dialogVisible.value = false;
};

async function open(id: number) {
  datasets_id.value = id;
  dialogVisible.value = true;
  const res: any = await getFeaturePropertiesKeysApi({ datasets_id: id })
  console.log(res)
}
defineExpose({
  open,
});
</script>

<style lang="less" scoped></style>
