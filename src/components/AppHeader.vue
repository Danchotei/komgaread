<script setup lang="ts">
import headerMascot from '../assets/header-mascot.png'
</script>

<template>
  <header class="home-header">
    <a class="brand" href="#/" aria-label="KomgaRead 主页">
      <img class="header-mascot" :src="headerMascot" alt="" width="48" height="48" />KomgaRead
    </a>
    <a class="header-search" href="#/search" aria-label="搜索" title="搜索">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>
    </a>
  </header>
</template>
