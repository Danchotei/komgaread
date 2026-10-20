<script setup lang="ts">
import { computed, onMounted, onActivated, onDeactivated } from 'vue'
import { traceNavigation } from '../navigationDebug'
import HomeView from './HomeView.vue'
import SearchView from './SearchView.vue'
import SeriesView from './SeriesView.vue'
import ReaderView from './ReaderView.vue'
import CategoriesView from './CategoriesView.vue'
import AppHeader from './AppHeader.vue'
import type { User } from '../api/auth'
const props = defineProps<{ pageHash: string; user: User; loggingOut: boolean; message: string; canBack: boolean }>()
const emit = defineEmits<{ back: []; logout: [] }>()
const tracePage = () => ({ page: props.pageHash.split('/')[1] || 'home' })
onMounted(() => traceNavigation('page-mounted', tracePage()))
onActivated(() => traceNavigation('page-activated', tracePage()))
onDeactivated(() => traceNavigation('page-deactivated', tracePage()))
const route = computed(() => {
  const match = props.pageHash.match(/^#\/(series|books)\/([^/]+)$/)
  try { return match ? { type: match[1], id: decodeURIComponent(match[2]!) } : null } catch { return null }
})
</script>
<template>
  <div class="cached-page">
    <SeriesView v-if="route?.type === 'series'" :series-id="route.id" @back="emit('back')" />
    <ReaderView v-else-if="route?.type === 'books'" :book-id="route.id" />
    <SearchView v-else-if="pageHash === '#/search'" :can-back="canBack" @back="emit('back')" />
    <CategoriesView v-else-if="pageHash === '#/categories'" />
    <main v-else-if="pageHash === '#/me'" class="tab-page"><AppHeader title="个人" /><h1 class="tab-title">我</h1><p class="account-email">{{ user.email }}</p><button class="text-button" :disabled="loggingOut" @click="emit('logout')">{{ loggingOut ? '正在退出…' : '退出登录' }}</button><p v-if="message" role="alert">{{ message }}</p></main>
    <HomeView v-else />
  </div>
</template>
