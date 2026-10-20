<script setup lang="ts">
import { onMounted, ref } from 'vue'
import LoginView from './components/LoginView.vue'
import { authRequest, type User } from './api/auth'

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
  <main v-if="checking" class="login-page" role="status">正在检查登录状态…</main>
  <main v-else-if="user" class="login-page">
    <section class="login-container login-card">
      <p class="eyebrow">KOMGAREAD</p>
      <h1>登录成功</h1>
      <p class="account-email">{{ user.email }}</p>
      <p class="intro">已连接 Komga。下一步将在这里展示你的漫画书架。</p>
      <button class="submit-button" :disabled="loggingOut" @click="logout">{{ loggingOut ? '正在退出…' : '退出登录' }}</button>
      <p v-if="message" role="alert">{{ message }}</p>
    </section>
  </main>
  <LoginView v-else @authenticated="user = $event" />
</template>
