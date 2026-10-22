<script setup lang="ts">
import { computed } from 'vue'
import HomeView from './HomeView.vue'
import SearchView from './SearchView.vue'
import JmSearchView from './JmSearchView.vue'
import SeriesView from './SeriesView.vue'
import ReaderView from './ReaderView.vue'
import CategoriesView from './CategoriesView.vue'
import ProfileView from './ProfileView.vue'
import BrowseView from './BrowseView.vue'
import type { User } from '../api/auth'
const props = defineProps<{ pageHash: string; user: User; loggingOut: boolean; message: string; canBack: boolean }>()
const emit = defineEmits<{ back: []; logout: [] }>()
const browseKind = computed(() => {
  const kind = props.pageHash.replace('#/browse/', '')
  return kind === 'latest' || kind === 'random' || kind === 'all' ? kind : null
})
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
    <JmSearchView v-else-if="pageHash === '#/jm-search'" @back="emit('back')" />
    <BrowseView v-else-if="browseKind" :kind="browseKind" @back="emit('back')" />
    <CategoriesView v-else-if="pageHash === '#/categories'" />
    <ProfileView v-else-if="pageHash === '#/me'" :user="user" :logging-out="loggingOut" :message="message" @logout="emit('logout')" />
    <HomeView v-else :user-id="user.id" />
  </div>
</template>
