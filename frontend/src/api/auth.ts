import client from './client'

export interface UserInfo {
  id: number
  username: string
  display_name: string
  role: string
  is_active: boolean
}

export const authApi = {
  async login(username: string, password: string): Promise<string> {
    const { data } = await client.post('/auth/login', { username, password })
    return data.data.access_token
  },

  async getMe(): Promise<UserInfo> {
    const { data } = await client.get('/auth/me')
    return data.data
  },
}
