<template>
  <el-table :data="tableData" style="width: 100%">
    <el-table-column prop="id" label="ID"/>
    <el-table-column prop="start_file" label="开始文件" />
    <el-table-column prop="end_file" label="结束文件" />
    <el-table-column prop="status" label="状态">
      <template #default="scope">
        <el-tag
          :type="statusObject[scope.row.status].type"
        >
          {{ statusObject[scope.row.status].text }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getRecordList } from '@/api/record'
const tableData = ref<any[]>([])

const statusObject: any = {
  0: {
    text: '未完成',
    type: 'primary'
  },
  1: {
    text: '已完成',
    type: 'success'
  },
  2: {
    text: '失败',
    type: 'danger'
  }
}

onMounted(async () => {
  const res = await getRecordList({
    page: 1,
    page_size: 10
  }) as any
  tableData.value = res
})

</script>
