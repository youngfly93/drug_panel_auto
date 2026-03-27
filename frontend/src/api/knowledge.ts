import client from './client'

export interface PaginatedTable {
  columns: string[]
  rows: Record<string, any>[]
  total: number
  page: number
  page_size: number
}

export interface GeneDetail {
  gene: string
  sheets: Record<string, Record<string, any>[]>
}

export interface KBStats {
  gene_knowledge: { sheets: number; total_rows: number }
  drug_mappings: { total_rows: number }
  immune_genes: { total_rows: number }
}

export const knowledgeApi = {
  async getGenes(params: { search?: string; page?: number; page_size?: number } = {}): Promise<PaginatedTable> {
    const { data } = await client.get('/knowledge/genes', { params })
    return data.data
  },

  async getGeneDetail(geneName: string): Promise<GeneDetail> {
    const { data } = await client.get(`/knowledge/genes/${encodeURIComponent(geneName)}`)
    return data.data
  },

  async getDrugs(params: { search?: string; page?: number; page_size?: number } = {}): Promise<PaginatedTable> {
    const { data } = await client.get('/knowledge/drugs', { params })
    return data.data
  },

  async getImmuneGenes(): Promise<PaginatedTable> {
    const { data } = await client.get('/knowledge/immune-genes')
    return data.data
  },

  async getStats(): Promise<KBStats> {
    const { data } = await client.get('/knowledge/stats')
    return data.data
  },
}
