<template>
  <el-card class="page">
    <template #header>
      <span>数组转表格</span>
    </template>

    <div class="form">
      <el-alert
        class="hint"
        type="info"
        :closable="false"
        title="粘贴一个二维数组。每一组是一行，第 0 项写入 A 列，第 1 项写入 B 列，第 2 项写入 C 列，以此类推。"
      />

      <el-input
        v-model="text"
        type="textarea"
        :rows="8"
        placeholder='[["姓名1","年龄1","岁数1"],["姓名2","年龄2","岁数2"]]'
      />
      <div v-if="parseError" class="error">{{ parseError }}</div>
      <div v-else-if="rows.length" class="summary">{{ rows.length }} 行，{{ letters.length }} 列</div>

      <el-table v-if="rows.length" :data="rows" border stripe max-height="360">
        <el-table-column label="行" width="64" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column
          v-for="(letter, index) in letters"
          :key="letter"
          :label="`${letter}  [${index}]`"
          min-width="140"
        >
          <template #default="{ row }">{{ display(row[index]) }}</template>
        </el-table-column>
      </el-table>

      <Upload
        v-model:value="savePath"
        type="savePathAndFileName"
        data-type="xlsx"
        label="保存为"
        placeholder="请选择 xlsx 保存位置"
      />

      <div class="actions">
        <el-button @click="fillExample">填入示例</el-button>
        <el-button type="primary" :loading="running" :disabled="running" @click="generate">
          生成表格
        </el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import Upload from '@/components/Upload/index.vue'
import { arrayToTable } from '@/api/excelFill'

const example = `[
  ["姓名1", "年龄1", "岁数1"],
  ["姓名2", "年龄2", "岁数2"]
]`

const text = ref(example)
const savePath = ref('')
const rows = ref<unknown[][]>([])
const parseError = ref('')
const running = ref(false)

const letters = computed(() => {
  const width = rows.value.reduce((max, row) => Math.max(max, row.length), 0)
  return Array.from({ length: width }, (_, index) => columnLetter(index))
})

watch(text, parseText, { immediate: true })

function fillExample() {
  text.value = example
}

function parseText() {
  const source = text.value.trim()
  if (!source) {
    rows.value = []
    parseError.value = ''
    return
  }
  try {
    rows.value = parseRows(source)
    parseError.value = ''
  } catch (error) {
    rows.value = []
    parseError.value = error instanceof Error ? error.message : '无法解析'
  }
}

function parseRows(source: string): unknown[][] {
  const data = JSON.parse(source)
  if (!Array.isArray(data)) {
    throw new Error('最外层必须是数组')
  }
  return data.map((row, index) => {
    if (!Array.isArray(row)) {
      throw new Error(`第 ${index + 1} 组不是数组`)
    }
    return row
  })
}

function columnLetter(index: number) {
  let current = index + 1
  let letters = ''
  while (current > 0) {
    const remainder = (current - 1) % 26
    letters = String.fromCharCode(65 + remainder) + letters
    current = Math.floor((current - 1) / 26)
  }
  return letters
}

function display(value: unknown) {
  if (value == null || value === '') return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

async function generate() {
  parseText()
  if (parseError.value) {
    ElMessage.error(parseError.value)
    return
  }
  if (!rows.value.length) {
    ElMessage.error('请先粘贴二维数组')
    return
  }
  if (!savePath.value) {
    ElMessage.error('请选择保存位置')
    return
  }
  running.value = true
  try {
    const result = await arrayToTable({ rows: rows.value, path: savePath.value })
    ElMessage.success(`已生成 ${result.rows} 行 ${result.columns} 列`)
  } catch (error) {
    ElMessage.error(typeof error === 'string' ? error : '生成失败')
  } finally {
    running.value = false
  }
}
</script>

<style scoped lang="less">
.page {
  max-width: 960px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.error {
  color: #d93026;
}
.summary {
  color: #52606d;
}
.actions {
  display: flex;
  gap: 12px;
}
</style>
