<template>
  <div class="upload">
    <div>{{ label }}</div>
    <el-input :value="value" :placeholder="placeholder" />
    <el-button type="primary" @click="handleSelectFile">选择</el-button>
  </div>
</template>

<script lang="ts" setup>
import { selectFile, selectFolder, selectSavePath } from '@/utils/base'

interface Props {
  dataType?: string,
  value: string,
  placeholder?: string,
  label?: string,
  type?: 'file' | 'folder' | 'savePath',
}

const props = withDefaults(defineProps<Props>(), {
  dataType: '',
  value: '',
  placeholder: '请选择文件',
  label: '选择文件',
  type: 'file'
})

const emit = defineEmits<{
  (e: 'update:value', value: string): void
}>()

const typeMap = {
  file: selectFile,
  folder: selectFolder,
  savePath: selectSavePath,
}

async function handleSelectFile() {
  const res = await typeMap[props.type](props.dataType)
  emit('update:value', res as string)
}

</script>

<style scoped lang="less">
.upload{
  width: 460px;
  display: flex;
  align-items: center;
  justify-content: center;
  >div:nth-child(2){
    flex: 1;
    margin: 0 10px;
  }
}
</style>
