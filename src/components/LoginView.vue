<script setup lang="ts">
import { onMounted, ref } from 'vue'
import headerMascot from '../assets/header-mascot.png'
import { authRequest, type User } from '../api/auth'

const emit = defineEmits<{ authenticated: [user: User] }>()
const submitting = ref(false)

// ref 保存会变化的数据；数据变化时，Vue 会更新对应的界面。
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const message = ref('')
const registering = ref(false)
const registrationEnabled = ref(false)
const confirmPassword = ref('')
const inviteCode = ref('')
onMounted(async () => {
  try { registrationEnabled.value = (await authRequest<{ enabled: boolean }>('registration')).enabled }
  catch { registrationEnabled.value = false }
})
function toggleRegistration() {
  registering.value = !registering.value
  password.value = ''
  confirmPassword.value = ''
  inviteCode.value = ''
  showPassword.value = false
  message.value = ''
}

async function handleSubmit() {
  if (submitting.value) return
  submitting.value = true
  message.value = ''
  try {
    if (registering.value) {
      if (password.value !== confirmPassword.value) throw new Error('两次输入的密码不一致')
      const result = await authRequest<{ message: string }>('register', {
        email: username.value, password: password.value, confirm_password: confirmPassword.value, invite_code: inviteCode.value.trim(),
      })
      registering.value = false
      password.value = ''
      confirmPassword.value = ''
      inviteCode.value = ''
      showPassword.value = false
      message.value = result.message
      return
    }
    const user = await authRequest<User>('login', { username: username.value, password: password.value })
    password.value = ''
    emit('authenticated', user)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '请求失败，请重试'
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
        <img class="brand-mascot" :src="headerMascot" alt="" width="64" height="64" />
        KomgaRead
      </a>

      <section class="login-card" aria-labelledby="login-title">
        <p class="eyebrow">神秘收藏库</p>
        <h1 id="login-title">{{ registering ? '创建账号' : '欢迎回来' }}</h1>
        <p class="intro">{{ registering ? '注册后可在线阅读全部漫画库' : '使用你的 Komga 账号登录' }}</p>

        <form @submit.prevent="handleSubmit" @input="clearMessage">
          <div class="field">
            <label for="username">{{ registering ? '邮箱' : '账号' }}</label>
            <input
              id="username"
              v-model.trim="username"
              name="username"
              :type="registering ? 'email' : 'text'"
              autocomplete="username"
              :placeholder="registering ? 'name@example.com' : '输入 Komga 账号'"
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
                :autocomplete="registering ? 'new-password' : 'current-password'"
                :placeholder="registering ? '至少 8 个字符，不超过 72 字节' : '输入密码'"
                :minlength="registering ? 8 : undefined"
                :maxlength="registering ? 72 : undefined"
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

          <div v-if="registering" class="field"><label for="confirm-password">确认密码</label><input id="confirm-password" v-model="confirmPassword" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" required minlength="8" maxlength="72" placeholder="再次输入密码" /></div>
          <div v-if="registering" class="field"><label for="registration-invite">邀请码</label><input id="registration-invite" v-model="inviteCode" type="password" autocomplete="off" required maxlength="256" placeholder="输入管理员提供的邀请码" /></div>
          <button class="submit-button" type="submit" :disabled="submitting">{{ submitting ? '正在提交…' : registering ? '注册' : '登录' }}</button>
          <p v-if="message" class="form-message" role="status">{{ message }}</p>
        </form>

        <div class="account-help"><button v-if="registrationEnabled" class="text-button" type="button" :disabled="submitting" @click="toggleRegistration">{{ registering ? '已有账号，返回登录' : '没有账号？注册' }}</button><p>{{ registrationEnabled ? '忘记密码请联系管理员。' : '账号由管理员创建。如需账号或重置密码，请联系管理员。' }}</p></div>
      </section>

      <p class="preview-note">by B</p>
    </div>
  </main>
</template>
