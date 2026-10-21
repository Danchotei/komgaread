<script setup lang="ts">
import type { SeriesCardItem } from '../seriesState'

withDefaults(defineProps<{ item: SeriesCardItem; failed?: boolean }>(), { failed: false })
defineEmits<{ coverError: [] }>()
</script>

<template>
  <a class="book-link" :href="`#/series/${encodeURIComponent(item.id)}`">
    <div class="series-cover"><img v-if="!failed" :src="item.thumbnailUrl" :alt="item.title" loading="lazy" @error="$emit('coverError')" /><span v-else class="cover-fallback">暂无封面</span></div>
    <h3>{{ item.title }}</h3>
    <p class="result-card-genres" :title="item.genres?.join('、')">{{ item.genres?.join('、') || '暂无分类' }}</p>
    <p class="result-card-meta"><span>{{ item.booksCount }} 章</span><time v-if="item.lastReleaseDate" :datetime="item.lastReleaseDate" title="最后一章发行日期">{{ item.lastReleaseDate }}</time><span v-else>日期未知</span></p>
  </a>
</template>
