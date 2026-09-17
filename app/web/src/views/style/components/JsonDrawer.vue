<template>
  <el-drawer v-model="visible" title="样式 JSON" size="50%">
    <el-input v-model="text" type="textarea" :rows="28" />
    <div style="margin-top: 12px; display: flex; gap: 8px">
      <el-button type="primary" @click="apply">应用到编辑器</el-button>
      <el-button @click="reload">从当前样式刷新</el-button>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useStyleEditorStore } from '@/stores/styleEditor'

const visible = defineModel<boolean>({ default: false })
const store = useStyleEditorStore()
const text = ref('')

watch(visible, (v) => {
  if (v) text.value = JSON.stringify(store.exportStyle(), null, 2)
})

function apply() {
  try {
    store.setStyle(JSON.parse(text.value))
    ElMessage.success('已应用 JSON')
  } catch (e: any) {
    ElMessage.error(e?.message || 'JSON 无效')
  }
}

function reload() {
  text.value = JSON.stringify(store.exportStyle(), null, 2)
}
</script>
