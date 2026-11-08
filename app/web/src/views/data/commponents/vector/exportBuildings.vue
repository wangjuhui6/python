<template>
  <el-card>
    <template #header>
      <span>导出建筑</span>
    </template>
    <div class="upload-container">
      <Upload
        v-model:value="data.file"
        type="file"
        dataType="shpOrPbf"
        label="选择文件"
        placeholder="请选择 shp 或 pbf"
      />
      <Upload
        v-model:value="data.savePath"
        type="savePathAndFileName"
        dataType="shp"
        label="保存路径及文件名"
        placeholder="请选择导出的建筑 shp"
      />
      <div v-if="loading && !summary" class="summary">正在读取。PBF 会按建筑标签扫一遍，文件大时要等一会儿。</div>
      <div v-if="summary" class="summary">
        <div>{{ summary.line }}</div>
        <div>{{ summary.reason }}</div>
        <div v-if="summary.polygon">按当前选择将导出约 {{ selectedCount }} 条面</div>
      </div>
      <div class="row">
        <div>筛选字段</div>
        <el-select
          v-model="data.field"
          style="width: 220px"
          placeholder="导出全部面"
          :disabled="!fields.length"
        >
          <el-option :label="summary?.format === 'pbf' ? '全部建筑' : '导出全部面'" value="" />
          <el-option v-for="item in fields" :key="item" :label="item" :value="item" />
        </el-select>
      </div>
      <template v-if="data.field">
        <el-input v-model="keyword" placeholder="搜索取值" clearable />
        <div class="actions">
          <el-button link type="primary" @click="checkBuildings">勾选建筑取值</el-button>
          <el-button link type="primary" @click="checkAll">全选</el-button>
          <el-button link @click="checked = []">清空</el-button>
        </div>
        <div v-if="truncated" class="summary">取值较多，只列出前 300 个，已优先保留像建筑的取值。</div>
        <el-checkbox-group v-model="checked" class="value-list">
          <el-checkbox
            v-for="item in fieldValues"
            v-show="matchValue(item.value)"
            :key="item.value"
            :value="item.value"
          >
            {{ item.value || '（空）' }}（{{ item.count }}）
          </el-checkbox>
        </el-checkbox-group>
      </template>
      <el-button type="primary" :loading="loading || exporting" @click="save">导出建筑 shp</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import Upload from '@/components/Upload/index.vue'
import { buildingFieldValues, exportBuildingShp, inspectBuildingShp } from '@/api/gdal'
import { ElMessage } from 'element-plus'

type ValueItem = {
  value: string
  count: number
  building: boolean
}

const fields = ref<string[]>([])
const fieldValues = ref<ValueItem[]>([])
const checked = ref<string[]>([])
const keyword = ref('')
const truncated = ref(false)
const loading = ref(false)
const exporting = ref(false)
const silentField = ref(false)
const summary = ref<{ total: number; polygon: number; reason: string; format: string; line: string } | null>(null)

const data = reactive({
  file: '',
  savePath: '',
  field: '',
})

const selectedCount = computed(() => {
  if (!summary.value) return 0
  if (!data.field) return summary.value.polygon
  const picked = new Set(checked.value)
  return fieldValues.value
    .filter((item) => picked.has(item.value))
    .reduce((sum, item) => sum + item.count, 0)
})

function errorText(error: unknown) {
  if (typeof error === 'string' && error) return error
  if (error instanceof Error && error.message) return error.message
  return '处理失败'
}

function matchValue(value: string) {
  const text = keyword.value.trim().toLowerCase()
  if (!text) return true
  return (value || '（空）').toLowerCase().includes(text)
}

function checkBuildings() {
  checked.value = fieldValues.value.filter((item) => item.building).map((item) => item.value)
}

function checkAll() {
  checked.value = fieldValues.value.map((item) => item.value)
}

async function loadFieldValues(field: string) {
  keyword.value = ''
  checked.value = []
  fieldValues.value = []
  truncated.value = false
  if (!field || !data.file) return
  loading.value = true
  try {
    const res: any = await buildingFieldValues({ file: data.file, field })
    fieldValues.value = res.values || []
    truncated.value = !!res.truncated
    checkBuildings()
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
  }
}

watch(() => data.field, (field) => {
  if (silentField.value) return
  loadFieldValues(field)
})

watch(() => data.file, async (file) => {
  summary.value = null
  fields.value = []
  fieldValues.value = []
  checked.value = []
  keyword.value = ''
  truncated.value = false
  silentField.value = true
  data.field = ''
  if (!file) {
    await nextTick()
    silentField.value = false
    return
  }
  loading.value = true
  try {
    const res: any = await inspectBuildingShp({ file })
    summary.value = {
      total: res.total || 0,
      polygon: res.polygon || 0,
      reason: res.suggestion?.reason || '',
      format: res.format || 'shp',
      line: res.line || `共 ${res.total || 0} 条，其中面 ${res.polygon || 0} 条`,
    }
    fields.value = res.fields || []
    data.field = res.suggestion?.field || ''
    fieldValues.value = res.values || []
    truncated.value = !!res.truncated
    checked.value = res.suggestion?.values || []
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    loading.value = false
    await nextTick()
    silentField.value = false
  }
})

async function save() {
  if (!data.file || !data.savePath) {
    ElMessage.error('请选择文件和保存路径')
    return
  }
  if (data.field && !checked.value.length) {
    ElMessage.error(summary.value?.format === 'pbf' ? '请至少勾选一个取值，或改为全部建筑' : '请至少勾选一个取值，或改为导出全部面')
    return
  }
  exporting.value = true
  try {
    const res: any = await exportBuildingShp({
      file: data.file,
      outputPath: data.savePath,
      field: data.field,
      values: checked.value,
    })
    ElMessage.success(`已导出 ${res.count} 条建筑`)
  } catch (error) {
    ElMessage.error(errorText(error))
  } finally {
    exporting.value = false
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
.summary{
  width: 460px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}
.row{
  width: 460px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.actions{
  width: 460px;
  display: flex;
  gap: 8px;
}
.value-list{
  width: 460px;
  max-height: 220px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
</style>
