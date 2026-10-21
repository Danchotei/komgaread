<script setup lang="ts">
import { searchState } from '../searchState'

const categories = ['全彩', '长篇', '同人', '短篇', '单行本', 'AI', '纯爱', 'SM', 'NTR', '强暴', '后宫', '性转换']

function selectCategory(name: string) {
  searchState.pendingSearch = { keyword: name }
}
</script>

<template>
  <main class="tab-page categories-page">
    <nav class="category-grid category-discovery" aria-label="发现系列">
      <a href="#/browse/latest">最近更新</a>
      <a href="#/browse/random">随机本子</a>
      <a href="#/browse/all">浏览所有</a>
    </nav>
    <nav class="category-grid" aria-label="漫画分类">
      <a v-for="category in categories" :key="category" href="#/search" @click="selectCategory(category)">{{ category }}</a>
    </nav>
  </main>
</template>
