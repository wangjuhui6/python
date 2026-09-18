<template>
  <div class="postgis-container">
    <div class="postgis-header">
      <el-button type="primary" @click="addDataset">新增数据源</el-button>
    </div>
    <div class="postgis-content">
      <el-collapse v-model="activeName" accordion>
        <el-collapse-item v-for="(item) in list" :key="item.id" :title="item.name" :name="item.code">
          <div style="display: flex; align-items: center; justify-content: flex-end;">
            <el-button @click="addData(item.id)">添加数据</el-button>
            <el-button @click="listFeatures(item.id)">查看数据</el-button>
            <el-button @click="listFeaturesMap(item.id)">地图查看</el-button>
            <el-button type="primary" @click="addDataset(item)">编辑</el-button>
            <el-button type="danger" @click="deleteDataset(item.id)">删除</el-button>
            <el-button type="danger" @click="deleteFeatures(item.id)">删除数据</el-button>
            <el-button type="primary" @click="getFeaturePropertiesKeys(item.id)">查看字段</el-button>
          </div>
          <el-row>
            <el-col :span="12">
              <div>数据源编码: {{ item.code }}</div>
            </el-col>
            <el-col :span="12">
              <div>数据源坐标系: {{ SRID_OPTIONS_OBJ[item.srid] }}</div>
            </el-col>
            <el-col :span="24">
              <div>数据源描述: {{ item.description }}</div>
            </el-col>
          </el-row>
          <el-row>
            <el-col :span="24">
              <template v-for="(val, index) in item.mapping" :key="index">
                <div>{{ val.oldValue }} => {{ val.newValue }}</div>
              </template>
              <template v-if="item.categories?.length">
                <div>分类 {{ item.categories.length }} 项（show {{ item.categories.filter((c: any) => c.show).length }} 将进入 mbtiles）</div>
              </template>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
  <!-- 新增编辑弹窗 -->
  <el-dialog
    v-model="dialogVisible"
    title="数据源"
    width="960"
    :before-close="handleClose"
  >
    <el-form :model="formData" label-width="80px" :rules="rules" ref="addFormRef">
      <el-row>
        <el-col :span="12">
          <el-form-item label="名称" prop="name">
            <el-input v-model="formData.name" placeholder="请输入名称" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="编码" prop="code">
            <el-input v-model="formData.code" placeholder="请输入代码" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="坐标系" prop="srid">
            <el-select v-model="formData.srid" placeholder="请选择坐标系" >
              <el-option v-for="item in SRID_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="描述">
            <el-input :rows="2" type="textarea" v-model="formData.description" placeholder="请输入描述" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="字段映射">
            <template v-for="(item, index) in formData.mapping" :key="index">
              <el-row>
                <el-col :span="10">
                  <el-input v-model="item.oldValue" placeholder="请输入字段名称" />
                </el-col>
                <span style="width: 10px;"></span>
                <el-col :span="10">
                  <el-input v-model="item.newValue" placeholder="请输入字段映射新名称" />
                </el-col>
                <span style="width: 10px;"></span>
                <el-col :span="2">
                  <div style="display: flex; align-items: center; justify-content: center; height: 100%;">
                    <el-icon style="cursor: pointer;" @click="deleteMapping(index)"><RemoveFilled /></el-icon>
                  </div>
                </el-col>
              </el-row>
            </template>
            <el-button :icon="Plus" @click="addMapping">新增</el-button>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="数据分类">
            <CategoryEditor v-model="formData.categories" :dataset-id="formData.id" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">
          保存
        </el-button>
      </div>
    </template>
  </el-dialog>
  <AddData ref="addDataRef" />
  <ShowKeys ref="showKeysRef" />
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { Plus, RemoveFilled } from '@element-plus/icons-vue'
import { getDatasets as getDatasetsApi,
  addDataset as addDatasetApi,
  deleteDataset as deleteDatasetApi,
  listFeatures as listFeaturesApi,
  deleteFeatures as deleteFeaturesApi
} from '@/api/postgis'
import { ElMessage } from 'element-plus'
import AddData from './components/addData.vue'
import ShowKeys from './components/showKeys.vue'
import CategoryEditor from './components/CategoryEditor.vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const SRID_OPTIONS = [
  { label: 'WGS84坐标系', value: 'WGS84' },
  { label: '火星坐标系', value: 'GCJ-02' },
  { label: '百度坐标系', value: 'BD-09' },
]

const SRID_OPTIONS_OBJ: any = {}

SRID_OPTIONS.forEach((item) => {
  SRID_OPTIONS_OBJ[item.value] = item.label
})

const addDataRef = ref<any>()

const rules = reactive({
  name: [
    { required: true, message: '请输入数据源名称', trigger: 'blur' },
  ],
  code: [
    { required: true, message: '请输入数据源代码', trigger: 'blur' },
  ],
  srid: [
    { required: true, message: '请选择坐标系', trigger: 'change' },
  ]
})

const baseFormData: any = {
  id: undefined,
  name: '',
  code: '',
  srid: 'WGS84',
  description: '',
  mapping: [],
  categories: [],
}

const addFormRef = ref<any>()

const formData = reactive({...baseFormData})

function addDataset(data?: any) {
  dialogVisible.value = true
  Object.assign(formData, JSON.parse(JSON.stringify(baseFormData)))
  if (data) {
    Object.assign(formData, JSON.parse(JSON.stringify(data)))
    if (!Array.isArray(formData.categories)) {
      formData.categories = []
    }
  }
}

const activeName = ref('')
const list = ref<any[]>([])

function addMapping() {
  formData.mapping.push({
    oldValue: '',
    newValue: '',
  })
}

function deleteMapping(index: number | string) {
  formData.mapping.splice(index, 1)
}

async function deleteDataset(id: number) {
  const res: any = await deleteDatasetApi({ id })
  if (res) {
    ElMessage.success('删除成功')
    getDatasetsFun()
  } else {
    ElMessage.error(res.msg)
  }
}

async function getDatasetsFun() {
  const res: any = await getDatasetsApi({})
  const newData = res
  newData.forEach((item: any) => {
    const mapping: any = []
    Object.keys(item.mapping || {}).forEach((key: string) => {
      mapping.push({
        oldValue: key,
        newValue: item.mapping[key],
      })
    })
    item.mapping = mapping
    if (!Array.isArray(item.categories)) {
      item.categories = []
    }
  })
  list.value = newData
}

getDatasetsFun()

const dialogVisible = ref(false)
function handleClose() {
  Object.assign(formData, JSON.parse(JSON.stringify(baseFormData)))
}

async function save() {
  await addFormRef.value.validate()
  const _formData = JSON.parse(JSON.stringify(formData))
  const mapping: any = {}
  _formData.mapping.map((item: any) => {
    const { oldValue, newValue } = item
    if (oldValue && newValue) {
      mapping[oldValue] = newValue
    }
  })
  _formData.mapping = JSON.stringify(mapping)
  _formData.categories = Array.isArray(_formData.categories) ? _formData.categories : []
  const res: any = await addDatasetApi(_formData)
  if (res) {
    ElMessage.success('添加成功')
    dialogVisible.value = false
    getDatasetsFun()
    Object.assign(formData, baseFormData)
  } else {
    ElMessage.error(res.msg)
  }
}

// 添加数据
function addData(id: number) {
  addDataRef.value.open(id)
}

// 查看数据
async function listFeatures(id: number) {
  const res: any = await listFeaturesApi({
    datasets_id: id,
    is_geojson: true,
  })
  if (res) {
    ElMessage.success('查询成功')
  } else {
    ElMessage.error(res.msg)
  }
}

// 地图查看
function listFeaturesMap(id: number) {
  router.push({
    name: 'postgis-features-map',
    params: { id }
  })
}

// 删除数据
async function deleteFeatures(id: number) {
  const res: any = await deleteFeaturesApi({ datasets_id: id })
  if (res) {
    ElMessage.success('删除成功')
  }
}

const showKeysRef = ref<any>()
// 查看字段
async function getFeaturePropertiesKeys(id: number) {
  showKeysRef.value.open(id)
}

</script>

<style scoped lang="less">
.postgis-container{
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.postgis-header{
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.postgis-content{
  flex: 1;
  overflow-y: auto;
}
</style>
