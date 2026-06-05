<template>
  <div>栅格数据，测试路由使用，不一定会做这个功能</div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'

onMounted(() => {
  axios.get('/api/data').then(res => {
    console.log(res)
  })
})
</script>
