<script setup lang="ts">
import AppHeader from './AppHeader.vue'
import { searchState } from '../searchState'

const categories = ['全彩', '长篇', '同人', '短篇', '单行本', 'AI', '纯爱', 'SM', 'NTR', '强暴', '后宫', '性转换']

function selectCategory(name: string) {
  searchState.pendingSearch = { keyword: name }
}
</script>

<template>
  <main class="tab-page categories-page">
    <AppHeader title="分类" />
    <nav class="category-grid" aria-label="漫画分类">
      <a v-for="category in categories" :key="category" href="#/search" @click="selectCategory(category)">{{ category }}</a>
    </nav>
  </main>
</template>
