<script setup lang="ts">
defineProps<{ active?: 'home' | 'categories' | 'me' }>()
defineEmits<{ navigate: [target: string] }>()
</script>

<template>
  <nav class="bottom-nav" aria-label="主导航">
    <a href="#/" @click.prevent="$emit('navigate', '#/')" aria-label="主页" title="主页" :aria-current="active === 'home' ? 'page' : undefined">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" /></svg>
    </a>
    <a href="#/categories" @click.prevent="$emit('navigate', '#/categories')" aria-label="分类" title="分类" :aria-current="active === 'categories' ? 'page' : undefined">
      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
    </a>
    <a href="#/me" @click.prevent="$emit('navigate', '#/me')" aria-label="我" title="我" :aria-current="active === 'me' ? 'page' : undefined">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></svg>
    </a>
  </nav>
</template>
