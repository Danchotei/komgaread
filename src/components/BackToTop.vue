<script setup lang="ts">
defineProps<{ target: HTMLElement | null }>()
</script>

<template>
  <button class="back-to-top" type="button" aria-label="返回顶部" title="返回顶部" @click="target?.scrollTo({ top: 0, behavior: 'smooth' })">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14M12 20V9m-5 5 5-5 5 5" /></svg>
  </button>
</template>
