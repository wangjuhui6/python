<template>
  <div class="vector">
    <GeojsonToShp />
    <ShpToGlb />
    <Crop3dTiles />
    <LineDeduplicator />
    <GeojsonMerge />
  </div>
</template>

<script setup lang="ts">
import ShpToGlb from './commponents/vector/shpToGlb.vue'
import Crop3dTiles from './commponents/vector/crop3dTiles.vue'
import LineDeduplicator from './commponents/vector/lineDeduplicator.vue'
import GeojsonToShp from './commponents/vector/geojsonToShp.vue'
import GeojsonMerge from './commponents/vector/geojsonMerge.vue'
</script>

<style scoped lang="less">
.vector{
  display: flex;
  align-items: start;
  gap: 20px;
  flex-wrap: wrap;
}
.upload-container{
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 10px;
}
</style>
