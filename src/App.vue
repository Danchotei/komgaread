<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import HomeView from './components/HomeView.vue'
import SeriesView from './components/SeriesView.vue'
import ReaderView from './components/ReaderView.vue'
import { authRequest, type User } from './api/auth'

const hash = ref(window.location.hash)
function updateRoute() { hash.value = window.location.hash; window.scrollTo(0, 0) }
window.addEventListener('hashchange', updateRoute)
onUnmounted(() => window.removeEventListener('hashchange', updateRoute))
const route = computed(() => {
  const match = hash.value.match(/^#\/(series|books)\/([^/]+)$/)
  try { return match ? { type: match[1], id: decodeURIComponent(match[2]!) } : null }
  catch { return null }
})
const user = ref<User | null>(null)
const checking = ref(true)
const loggingOut = ref(false)
const message = ref('')

onMounted(async () => {
  try {
    user.value = await authRequest<User>('me')
  } catch {
    // 没有有效会话时显示登录表单，提交时再显示具体连接错误。
    user.value = null
  } finally {
    checking.value = false
  }
})

async function logout() {
  loggingOut.value = true
  message.value = ''
  try {
    await authRequest<void>('logout', {})
    user.value = null
  } catch (error) {
    message.value = error instanceof Error ? error.message : '退出失败，请重试'
  } finally {
    loggingOut.value = false
  }
}
</script>

<template>
  <Transition :name="route?.type === 'series' && user && !checking ? 'series-slide' : 'page-static'">
  <main v-if="checking" class="login-page" role="status">正在检查登录状态…</main>
  <SeriesView v-else-if="user && route?.type === 'series'" :key="route.id" :series-id="route.id" />
  <ReaderView v-else-if="user && route?.type === 'books'" :key="route.id" :book-id="route.id" />
  <HomeView v-else-if="user" :logging-out="loggingOut" :logout-message="message" @logout="logout" />
  <LoginView v-else @authenticated="user = $event" />
  </Transition>
</template>
