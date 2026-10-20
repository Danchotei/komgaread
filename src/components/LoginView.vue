<script setup lang="ts">
import { ref } from 'vue'
import { authRequest, type User } from '../api/auth'

const emit = defineEmits<{ authenticated: [user: User] }>()
const submitting = ref(false)

// ref 保存会变化的数据；数据变化时，Vue 会更新对应的界面。
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const message = ref('')

async function handleSubmit() {
  if (submitting.value) return
  submitting.value = true
  message.value = ''
  try {
    const user = await authRequest<User>('login', { username: username.value, password: password.value })
    password.value = ''
    emit('authenticated', user)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '登录失败，请重试'
  } finally {
    submitting.value = false
  }
}
function clearMessage() {
  message.value = ''
}
</script>

<template>
  <main class="login-page">
    <div class="login-container">
      <a class="brand" href="./" aria-label="KomgaRead 首页">
        <span class="brand-icon" aria-hidden="true">K</span>
        KomgaRead
      </a>

      <section class="login-card" aria-labelledby="login-title">
        <p class="eyebrow">BJB的收藏库</p>
        <h1 id="login-title">欢迎回来</h1>
        <p class="intro">使用你的 Komga 账号登录</p>

        <form @submit.prevent="handleSubmit" @input="clearMessage">
          <div class="field">
            <label for="username">账号</label>
            <input
              id="username"
              v-model.trim="username"
              name="username"
              type="text"
              autocomplete="username"
              placeholder="输入 Komga 账号"
              required
              maxlength="254"
              pattern="^\S+$"
              title="请输入账号，不能含有空格"
            />
          </div>

          <div class="field">
            <label for="password">密码</label>
            <div class="password-field">
              <input
                id="password"
                v-model="password"
                name="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="输入密码"
                required
              />
              <button
                class="password-toggle"
                type="button"
                :aria-pressed="showPassword"
                aria-controls="password"
                @click="showPassword = !showPassword"
              >{{ showPassword ? '隐藏' : '显示' }}密码</button>
            </div>
          </div>

          <button class="submit-button" type="submit" :disabled="submitting">{{ submitting ? '正在登录…' : '登录' }}</button>
          <p v-if="message" class="form-message" role="status">{{ message }}</p>
        </form>

        <p class="account-help">账号由管理员创建。如需账号或重置密码，请联系管理员。</p>
      </section>

      <p class="preview-note">连接你的私人漫画库</p>
    </div>
  </main>
</template>
