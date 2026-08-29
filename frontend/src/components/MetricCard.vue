<script setup lang="ts">
defineProps<{
  label: string
  value: string | number
  description?: string
}>()
</script>

<template>
  <section class="metric-card">
    <span class="metric-card__label">{{ label }}</span>
    <strong class="metric-card__value">{{ value }}</strong>
    <span v-if="description" class="metric-card__description">{{ description }}</span>
  </section>
</template>
