<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <el-empty :description="title" class="empty-state">
    <template #image>
      <div class="empty-state__icon">○</div>
    </template>
    <p>{{ description }}</p>
  </el-empty>
</template>
