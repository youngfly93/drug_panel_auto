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

export type KnowledgeKind = 'gene' | 'drug' | 'targeted_drug'
export type KnowledgeLayer = 'base' | 'reviewed_overlay'
export type KnowledgeLayerFilter = 'all' | KnowledgeLayer
export type KnowledgeMatchScope = 'gene' | 'variant' | 'event'
export type KnowledgeMatchScopeFilter = 'all' | KnowledgeMatchScope
export type KnowledgeReviewStatus =
  | 'approved_for_runtime'
  | 'provisional_runtime'
  | 'legacy_runtime'
  | 'needs_review'
  | 'rejected'
  | 'superseded'
  | 'not_recorded'
export type KnowledgeReviewStatusFilter = 'all' | KnowledgeReviewStatus

export interface KnowledgeReview {
  status: KnowledgeReviewStatus
  scope: string
  basis: string
  runtime_eligible: boolean
  reviewer: string
  reviewer_type: string
  reviewed_at: string
  evidence_as_of: string
  secondary_review_status: string
  risk_level: string
}

export interface KnowledgeProvenance {
  source_id: string
  source_type: string
  source_db?: string | null
  source_ref?: string | null
  source_refs: Array<{ type: string; id: string; url?: string }>
  sheet?: string | null
  row_number?: number | null
  origin_panel_id?: string | null
  shared_overlay: boolean
  revision: string
  updated_at: string
}

export interface KnowledgeEntry {
  entry_id: string
  kind: KnowledgeKind
  layer: KnowledgeLayer
  panel_id: string
  gene: string
  c_hgvs: string
  p_hgvs: string
  match_scope: KnowledgeMatchScope
  runtime_behavior: string
  review: KnowledgeReview
  provenance: KnowledgeProvenance
  content: Record<string, unknown>
}

export interface PanelKnowledgeSummary {
  panel_id: string
  display_name: string
  status: string
  overlay_available: boolean
  overlay_origin_panel_id?: string | null
  shared_overlay: boolean
  review_status: KnowledgeReviewStatus
  warning?: string | null
}

export interface PanelKnowledgeList {
  panels: PanelKnowledgeSummary[]
  total: number
}

export interface KnowledgeEntryFacets {
  layers: Record<string, number>
  review_statuses: Record<string, number>
  match_scopes: Record<string, number>
}

export interface KnowledgeEntryPage {
  panel: PanelKnowledgeSummary
  kind: KnowledgeKind
  rows: KnowledgeEntry[]
  total: number
  page: number
  page_size: number
  facets: KnowledgeEntryFacets
  warnings: string[]
}

export interface KnowledgeEntryParams {
  panel_id: string
  kind: KnowledgeKind
  layer?: KnowledgeLayerFilter
  search?: string
  gene?: string
  review_status?: KnowledgeReviewStatusFilter
  match_scope?: KnowledgeMatchScopeFilter
  page?: number
  page_size?: number
}

export interface KnowledgeCoverage {
  panel: PanelKnowledgeSummary
  base: {
    gene_source_rows: number
    gene_entries: number
    unique_genes: number
    drug_rows: number
    drug_unique_genes: number
    targeted_drug_rows: number
    targeted_drug_unique_genes: number
  }
  reviewed_overlay: {
    available: boolean
    gene_rows: number
    unique_genes: number
    gene_level_rows: number
    variant_level_rows: number
    drug_rows: number
    drug_unique_genes: number
    targeted_drug_rule_rows: number
    targeted_drug_rule_unique_genes: number
    targeted_drug_applicability_rule_rows: number
    extra_reference_rows: number
    review_status_counts: Record<string, number>
  }
  overlap: {
    genes_in_both: number
    overlay_only_genes: number
  }
  declared_gene_coverage: {
    denominator_name: string
    total: number
    base_covered: number
    overlay_covered: number
    either_covered: number
    percent: number | null
    label: string
  }
  knowledge_coverage_contract: {
    denominator_name: string
    total_genes: number
    gene_explanation_complete: boolean
    gene_explanation_missing_count: number
    gene_explanation_missing_genes: string[]
    runtime_drug_genes: number
    explicitly_approved_drug_genes: number
    explicit_panel_rule_genes: number
    panel_rule_status_counts: Record<string, number>
    runtime_content_quality: {
      total_genes: number
      complete_genes: number
      complete_percent: number
      missing_intro_genes: string[]
      missing_analysis_genes: string[]
      generic_fallback_count: number
      generic_fallback_percent: number
      specific_explanation_genes: number
      specific_explanation_percent: number
      citation_integrity: {
        cited_pmids: number
        unresolved_pmids: string[]
        cited_trials: number
        unresolved_trials: string[]
      }
    } | null
    clinical_release_readiness: {
      status: 'READY' | 'BLOCKED'
      secondary_review: {
        owner: string
        status: string
        pending_runtime_rows: number
      }
      uat: {
        status: string
        reviewed_reports: number
        passed_reports: number
        pass_rate_percent: number | null
        required_pass_rate_percent: number
        minimum_reviewed_reports: number
      }
      blocking_reasons: string[]
      content_depth?: {
        generic_fallback_count: number
        specific_explanation_percent: number
      }
    }
    multidimensional_coverage: {
      gene_explanation: {
        total: number
        covered: number
        percent: number | null
      }
      review_governance: {
        total_overlay_rows: number
        status_counts: Record<string, number>
        standardized_rows: number
        standardized_percent: number
        secondary_review_complete_rows: number
        secondary_review_complete_percent: number
        pending_secondary_review_genes: string[]
      }
      source_provenance: {
        structured_source_rows: number
        structured_source_percent: number
        evidence_level_rows: number
        evidence_level_percent: number
        cancer_scope_rows: number
        cancer_scope_percent: number
      }
      specificity: {
        gene_level_rows: number
        variant_level_rows: number
        event_scoped_drug_rows: number
      }
      drug_actionability: {
        runtime_drug_genes: number
        panel_rule_genes: number
        runtime_database_genes: number
        filtered_database_genes: number
      }
    }
    drug_candidate_disposition: {
      database_candidate_genes: number
      runtime_eligible_database_genes: number
      runtime_eligible_database_gene_list: string[]
      database_only_filtered_genes: number
      database_only_filtered_gene_list: string[]
      filter_reason_row_counts: Record<string, number>
      historical_review: Record<string, string | number>
      pending_medical_review_rows: number
      pending_medical_review_genes: string[]
    }
    status_definitions: Record<string, string>
  }
  warnings: string[]
}

export const knowledgeApi = {
  async getPanels(): Promise<PanelKnowledgeList> {
    const { data } = await client.get('/knowledge/panels')
    return data.data
  },

  async getEntries(params: KnowledgeEntryParams): Promise<KnowledgeEntryPage> {
    const { data } = await client.get('/knowledge/entries', { params })
    return data.data
  },

  async getCoverage(panelId: string): Promise<KnowledgeCoverage> {
    const { data } = await client.get('/knowledge/coverage', {
      params: { panel_id: panelId },
    })
    return data.data
  },

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
