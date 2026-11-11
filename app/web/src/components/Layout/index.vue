<template>
  <div class="layout">
    <div class="layout-header">
      <div class="layout-header-side"></div>
      <div class="layout-header-center">
        <div
          v-for="item in routes"
          :key="item.name"
          :class="{
            'layout-header-center-item': true,
            'layout-header-center-item-active': item.name === currentRouteOneName
          }"
          @click="go(item)"
        >
          {{ item.meta.title }}
        </div>
      </div>
      <div class="layout-header-side layout-header-side-right">
        <el-button type="primary" :loading="opening" @click="openFill">批量写入表格</el-button>
      </div>
    </div>
    <div class="layout-two">
      <div
        v-for="item in twoRoutesObj[currentRouteOneName]"
        :key="item.name"
        :class="{
          'layout-two-item': true,
          'layout-two-item-active': item.name === currentRouteTwoName
        }"
        @click="go(item)"
      >
        {{ item.meta.title }}
      </div>
    </div>
    <div class="layout-content">
      <router-view />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { routes } from '@/router'
import { openExcelFill } from '@/api/excelFill'
const router = useRouter()
const opening = ref(false)

async function openFill() {
  if (opening.value) return
  opening.value = true
  try {
    const data = await openExcelFill()
    if (data?.already) {
      ElMessage.info('填写窗口已经打开')
    }
  } catch (error: unknown) {
    ElMessage.error(typeof error === 'string' ? error : '打不开填写窗口')
  } finally {
    opening.value = false
  }
}

const currentRouteOneName = computed(() => {
  const { name, matched } = router.currentRoute.value
  const index = matched.findIndex(item => item.name === name)
  return matched[index - 1]?.name || ''
})

const currentRouteTwoName = computed(() => {
  const { name } = router.currentRoute.value
  return name || ''
})

const twoRoutesObj = ref<any>({})
routes.forEach((item: any) => {
  twoRoutesObj.value[item.name] = item.children
})

function go(item: any) {
  if (item.meta?.fullPage) {
    router.push(item.redirect || item.children?.[0]?.path || item.path)
    return
  }
  const { path } = item
  router.push(path)
}

</script>

<style scoped lang="less">
.layout {
  width: 100%;
  height: 100%;
  &-header {
    height: 64px;
    box-shadow: 0 1px 0 0 rgba(0, 0, 0, .06);
    background-color: #f7f7f7;
    width: 100%;
    position: fixed;
    top: 0;
    z-index: 10;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  &-two {
    background-color: hsla(0, 0%, 97%, .98);
    padding: 20px 30px;
    position: fixed;
    top: 64px;
    width: 100%;
    z-index: 9;
    min-height: 80px;
    height: auto;
    box-sizing: border-box;
  }
  &-content{
    width: 100%;
    height: 100%;
    overflow-y: auto;
    padding: calc(64px + 80px + 24px) 24px 24px;
    box-sizing: border-box;
  }
}
// 中间
.layout-header-side{
  width: 200px;
  flex: 0 0 200px;
}
.layout-header-side-right{
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding-right: 20px;
  box-sizing: border-box;
}
.layout-header-center{
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
  &-item{
    position: relative;
    padding: 0 16px;
    height: 100%;
    line-height: 64px;
    color: #000;
    font-weight: 500;
    cursor: pointer;
  }
  &-item-active{
    &::after{
      content: '';
      position: absolute;
      bottom: 0;
      left: 50%;
      transform: translateX(-50%);
      width: calc(100% - 32px);
      height: 2px;
      background-color: #000;
    }
  }
}
.layout-two{
  display: flex;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  row-gap: 8px;
  &-item{
    flex: 0 0 auto;
    white-space: nowrap;
    padding: 0 16px;
    background-color: #fff;
    border-radius: 4px;
    height: 40px;
    line-height: 40px;
    cursor: pointer;
    margin: 0 8px;
    color: #222;
    &:hover{
      background-color: #f0f0f0;
    }
  }
  &-item-active{
    background-color: #07c160;
    color: #fff;
    &:hover{
      background-color: #07c160;
    }
  }
}
</style>
