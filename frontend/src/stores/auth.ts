import { defineStore } from 'pinia'
import { ref } from 'vue'
import { authApi, type UserInfo } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserInfo | null>(null)

  async function login(username: string, password: string) {
    const t = await authApi.login(username, password)
    token.value = t
    localStorage.setItem('token', t)
    await fetchUser()
  }

  async function fetchUser() {
    if (!token.value) return
    try {
      user.value = await authApi.getMe()
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  return { token, user, login, fetchUser, logout }
})
