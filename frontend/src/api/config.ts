import client from './client'

export interface ConfigFile {
  filename: string
  size_bytes: number
  modified_at: string
}

export interface ConfigHistory {
  filename: string
  size_bytes: number
  created_at: string
}

export const configApi = {
  async listFiles(): Promise<ConfigFile[]> {
    const { data } = await client.get('/config/files')
    return data.data
  },

  async getConfig(filename: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/config/${encodeURIComponent(filename)}`)
    return data.data
  },

  async getRaw(filename: string): Promise<string> {
    const { data } = await client.get(`/config/${encodeURIComponent(filename)}/raw`)
    return data.data.content
  },

  async updateConfig(filename: string, content: Record<string, any>): Promise<any> {
    const { data } = await client.put(`/config/${encodeURIComponent(filename)}`, content)
    return data.data
  },

  async updateRaw(filename: string, rawYaml: string): Promise<any> {
    const { data } = await client.put(
      `/config/${encodeURIComponent(filename)}/raw`,
      rawYaml,
      { headers: { 'Content-Type': 'text/plain' } },
    )
    return data
  },

  async validateConfig(filename: string, content: Record<string, any>): Promise<{ valid: boolean; errors: string[] }> {
    const { data } = await client.post(`/config/${encodeURIComponent(filename)}/validate`, content)
    return data.data
  },

  async getHistory(filename: string): Promise<ConfigHistory[]> {
    const { data } = await client.get(`/config/${encodeURIComponent(filename)}/history`)
    return data.data
  },
}
