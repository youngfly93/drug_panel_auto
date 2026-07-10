<template>
  <div class="knowledge-page">
    <div class="page-heading">
      <div>
        <h2>知识库</h2>
        <p>同时查看基础 Excel 与 Panel Reviewed Overlay；本页只读，不参与报告生成决策。</p>
      </div>
      <div class="panel-picker">
        <span>Panel</span>
        <el-select
          v-model="selectedPanelId"
          placeholder="选择 Panel"
          filterable
          style="width: 300px"
          :loading="panelsLoading"
          @change="handlePanelChange"
        >
          <el-option
            v-for="panel in catalogPanels"
            :key="panel.panel_id"
            :label="`${panel.display_name} (${panel.panel_id})`"
            :value="panel.panel_id"
          >
            <div class="panel-option">
              <span>{{ panel.display_name }}</span>
              <el-tag size="small" :type="panelStatusType(panel.status)">
                {{ panel.status || '未标记' }}
              </el-tag>
            </div>
          </el-option>
        </el-select>
      </div>
    </div>

    <el-alert
      v-if="selectedPanel?.shared_overlay"
      type="info"
      show-icon
      :closable="false"
      class="context-alert"
      :title="`${selectedPanel.display_name} 当前复用 ${selectedPanel.overlay_origin_panel_id} 的 Reviewed Overlay`"
      description="条目按当前 Panel 上下文展示，但审核知识的来源 Panel 与当前 Panel 不同。"
    />

    <el-alert
      v-if="selectedPanel?.review_status === 'needs_review'"
      type="warning"
      show-icon
      :closable="false"
      class="context-alert"
      title="当前 Overlay 含待审核条目，且未记录与当前文件修订绑定的整体审批"
      description="请以每条知识的审核状态为准；文件在运行时被启用，不等于当前 SHA 已完成医学审批。"
    />

    <el-alert
      v-for="warning in catalogWarnings"
      :key="warning"
      type="warning"
      show-icon
      :closable="false"
      class="context-alert"
      :title="warning"
    />

    <div v-if="coverage" class="coverage-grid" v-loading="coverageLoading">
      <el-card shadow="never" class="metric-card">
        <span>基础基因</span>
        <strong>{{ coverage.base.unique_genes }}</strong>
        <small>
          {{ coverage.base.gene_source_rows }} 个源行；Part3 用药解析 {{ coverage.base.drug_rows }} 条
        </small>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>Reviewed 基因</span>
        <strong>{{ coverage.reviewed_overlay.unique_genes }}</strong>
        <small>
          {{ coverage.reviewed_overlay.gene_rows }} 条基因知识；用药解析 {{ coverage.reviewed_overlay.drug_rows }} 条
        </small>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>Part2 靶向决策候选</span>
        <strong>{{ coverage.base.targeted_drug_rows }}</strong>
        <small>
          {{ coverage.base.targeted_drug_unique_genes }} 个基因；Panel 运行规则 {{ coverage.reviewed_overlay.targeted_drug_rule_rows }} 条
        </small>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>{{ coverage.declared_gene_coverage.label }}</span>
        <strong>
          {{ coverage.declared_gene_coverage.percent === null ? '—' : `${coverage.declared_gene_coverage.percent}%` }}
        </strong>
        <small v-if="coverage.declared_gene_coverage.total > 0">
          {{ coverage.declared_gene_coverage.either_covered }}/{{ coverage.declared_gene_coverage.total }}；分母 {{ coverage.declared_gene_coverage.denominator_name }}
        </small>
        <small v-else>只展示层级规模，不推断全 Panel 覆盖率</small>
      </el-card>
    </div>

    <el-empty
      v-else-if="!panelsLoading && catalogPanels.length === 0"
      description="未找到可浏览的 Panel Package"
    />

    <el-tabs v-model="activeTab" class="knowledge-tabs">
      <el-tab-pane label="基因知识" name="genes">
        <div class="catalog-toolbar">
          <el-input
            v-model="catalogSearch"
            placeholder="按字面搜索基因、HGVS 或正文（不解析正则）"
            clearable
            class="search-input"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button @click="handleSearch">搜索</el-button>
            </template>
          </el-input>
          <el-select v-model="selectedLayer" style="width: 160px" @change="handleFilterChange">
            <el-option label="全部层" value="all" />
            <el-option label="Panel Overlay" value="reviewed_overlay" />
            <el-option label="基础 Excel" value="base" />
          </el-select>
          <el-select v-model="selectedReview" style="width: 170px" @change="handleFilterChange">
            <el-option label="全部审核状态" value="all" />
            <el-option label="生产已启用" value="approved_for_runtime" />
            <el-option label="需审核" value="needs_review" />
            <el-option label="未记录" value="not_recorded" />
          </el-select>
          <el-select v-model="selectedScope" style="width: 150px" @change="handleFilterChange">
            <el-option label="全部匹配范围" value="all" />
            <el-option label="位点级" value="variant" />
            <el-option label="基因级" value="gene" />
            <el-option label="事件级" value="event" />
          </el-select>
        </div>
        <el-table
          :data="catalogRows"
          row-key="entry_id"
          stripe
          border
          v-loading="entriesLoading"
          max-height="580"
          empty-text="当前条件下无基因知识"
        >
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="entry-detail">
                <div class="detail-section">
                  <h4>知识内容</h4>
                  <div v-for="item in contentItems(row)" :key="item.key" class="detail-row">
                    <span>{{ item.label }}</span>
                    <p>{{ item.value }}</p>
                  </div>
                  <el-empty v-if="contentItems(row).length === 0" description="无可展示内容" :image-size="52" />
                </div>
                <div class="detail-section provenance-section">
                  <h4>来源与应用</h4>
                  <dl>
                    <dt>数据源</dt><dd>{{ sourceLabel(row) }}</dd>
                    <dt>位置</dt><dd>{{ provenanceLocation(row) }}</dd>
                    <dt>修订</dt><dd>{{ row.provenance.revision || '—' }}</dd>
                    <dt>更新</dt><dd>{{ formatUpdatedAt(row.provenance.updated_at) }}</dd>
                    <dt>运行口径</dt><dd>{{ runtimeBehaviorLabel(row.runtime_behavior) }}</dd>
                    <dt>审核依据</dt><dd>{{ reviewBasisLabel(row.review.basis) }}</dd>
                    <template v-if="row.provenance.source_ref">
                      <dt>证据索引</dt><dd>{{ row.provenance.source_ref }}</dd>
                    </template>
                  </dl>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="gene" label="基因" width="110" fixed />
          <el-table-column label="HGVS" min-width="170">
            <template #default="{ row }">
              <div class="hgvs-cell">
                <span v-if="row.c_hgvs">{{ row.c_hgvs }}</span>
                <span v-if="row.p_hgvs">{{ row.p_hgvs }}</span>
                <span v-if="!row.c_hgvs && !row.p_hgvs" class="muted">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="层级" width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="layerTagType(row.layer)">
                {{ layerLabel(row.layer) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="匹配范围" width="105">
            <template #default="{ row }">{{ scopeLabel(row.match_scope) }}</template>
          </el-table-column>
          <el-table-column label="审核状态" width="140">
            <template #default="{ row }">
              <el-tooltip :content="`${reviewScopeLabel(row.review.scope)}；${reviewBasisLabel(row.review.basis)}`">
                <el-tag size="small" :type="reviewTagType(row.review.status)">
                  {{ reviewLabel(row.review.status) }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="内容摘要" min-width="300">
            <template #default="{ row }">
              <span class="summary-text">{{ contentSummary(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" min-width="190">
            <template #default="{ row }">
              <div class="source-cell">
                <span>{{ sourceLabel(row) }}</span>
                <small v-if="row.provenance.shared_overlay">
                  来自 {{ row.provenance.origin_panel_id }}
                </small>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="catalogTotal > 0"
          :current-page="catalogPage"
          :page-size="catalogPageSize"
          :page-sizes="[20, 50, 100]"
          :total="catalogTotal"
          layout="total, sizes, prev, pager, next"
          class="catalog-pagination"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </el-tab-pane>

      <el-tab-pane label="药物知识" name="drugs">
        <div class="domain-switch">
          <el-radio-group v-model="drugCatalogKind" @change="handleDrugDomainChange">
            <el-radio-button value="drug">Part3 用药解读</el-radio-button>
            <el-radio-button value="targeted_drug">Part2 靶向药物决策</el-radio-button>
          </el-radio-group>
          <span v-if="drugCatalogKind === 'drug'">
            基础层与 Overlay 均属于 Word 第三部分的用药叙述，命中时 Overlay 优先。
          </span>
          <span v-else>
            基础层是全局候选库；Panel Overlay 是实际运行的 override。候选条目不等于本 Panel 会输出。
          </span>
        </div>
        <div class="catalog-toolbar">
          <el-input
            v-model="catalogSearch"
            placeholder="按字面搜索基因、HGVS、药物或正文（不解析正则）"
            clearable
            class="search-input"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          >
            <template #append>
              <el-button @click="handleSearch">搜索</el-button>
            </template>
          </el-input>
          <el-select v-model="selectedLayer" style="width: 160px" @change="handleFilterChange">
            <el-option label="全部层" value="all" />
            <el-option label="Panel Overlay" value="reviewed_overlay" />
            <el-option label="基础 Excel" value="base" />
          </el-select>
          <el-select v-model="selectedReview" style="width: 170px" @change="handleFilterChange">
            <el-option label="全部审核状态" value="all" />
            <el-option label="生产已启用" value="approved_for_runtime" />
            <el-option label="需审核" value="needs_review" />
            <el-option label="未记录" value="not_recorded" />
          </el-select>
          <el-select v-model="selectedScope" style="width: 150px" @change="handleFilterChange">
            <el-option label="全部匹配范围" value="all" />
            <el-option label="位点级" value="variant" />
            <el-option label="基因级" value="gene" />
            <el-option label="事件级" value="event" />
          </el-select>
        </div>
        <el-table
          :data="catalogRows"
          row-key="entry_id"
          stripe
          border
          v-loading="entriesLoading"
          max-height="580"
          empty-text="当前条件下无药物知识"
        >
          <el-table-column type="expand" width="48">
            <template #default="{ row }">
              <div class="entry-detail">
                <div class="detail-section">
                  <h4>知识内容</h4>
                  <div v-for="item in contentItems(row)" :key="item.key" class="detail-row">
                    <span>{{ item.label }}</span>
                    <p>{{ item.value }}</p>
                  </div>
                  <el-empty v-if="contentItems(row).length === 0" description="无可展示内容" :image-size="52" />
                </div>
                <div class="detail-section provenance-section">
                  <h4>来源与应用</h4>
                  <dl>
                    <dt>数据源</dt><dd>{{ sourceLabel(row) }}</dd>
                    <dt>位置</dt><dd>{{ provenanceLocation(row) }}</dd>
                    <dt>修订</dt><dd>{{ row.provenance.revision || '—' }}</dd>
                    <dt>更新</dt><dd>{{ formatUpdatedAt(row.provenance.updated_at) }}</dd>
                    <dt>运行口径</dt><dd>{{ runtimeBehaviorLabel(row.runtime_behavior) }}</dd>
                    <dt>审核依据</dt><dd>{{ reviewBasisLabel(row.review.basis) }}</dd>
                    <template v-if="row.provenance.source_ref">
                      <dt>证据索引</dt><dd>{{ row.provenance.source_ref }}</dd>
                    </template>
                  </dl>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="gene" label="基因" width="110" fixed />
          <el-table-column label="HGVS / 事件" min-width="190">
            <template #default="{ row }">
              <div class="hgvs-cell">
                <span v-if="row.c_hgvs">{{ row.c_hgvs }}</span>
                <span v-if="row.p_hgvs">{{ row.p_hgvs }}</span>
                <span v-if="!row.c_hgvs && !row.p_hgvs">{{ formatContent(row.content.event) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="层级" width="140">
            <template #default="{ row }">
              <el-tag size="small" :type="layerTagType(row.layer)">
                {{ layerLabel(row.layer) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="匹配范围" width="105">
            <template #default="{ row }">{{ scopeLabel(row.match_scope) }}</template>
          </el-table-column>
          <el-table-column label="审核状态" width="140">
            <template #default="{ row }">
              <el-tooltip :content="`${reviewScopeLabel(row.review.scope)}；${reviewBasisLabel(row.review.basis)}`">
                <el-tag size="small" :type="reviewTagType(row.review.status)">
                  {{ reviewLabel(row.review.status) }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="内容摘要" min-width="300">
            <template #default="{ row }">
              <span class="summary-text">{{ contentSummary(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="来源" min-width="190">
            <template #default="{ row }">
              <div class="source-cell">
                <span>{{ sourceLabel(row) }}</span>
                <small v-if="row.provenance.shared_overlay">
                  来自 {{ row.provenance.origin_panel_id }}
                </small>
              </div>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="catalogTotal > 0"
          :current-page="catalogPage"
          :page-size="catalogPageSize"
          :page-sizes="[20, 50, 100]"
          :total="catalogTotal"
          layout="total, sizes, prev, pager, next"
          class="catalog-pagination"
          @current-change="handlePageChange"
          @size-change="handlePageSizeChange"
        />
      </el-tab-pane>

      <el-tab-pane label="免疫基因" name="immune">
        <el-alert
          type="info"
          show-icon
          :closable="false"
          class="immune-alert"
          title="此页仅展示 immune_gene_list_public.xlsx 基础层"
          description="当前 Part 3 Reviewed Overlay 不包含独立的免疫基因层，因此不将其标记为 Panel Reviewed。"
        />
        <el-table :data="immuneData.rows" stripe border v-loading="immuneLoading" max-height="580">
          <el-table-column
            v-for="col in immuneData.columns"
            :key="col"
            :prop="col"
            :label="col"
            min-width="180"
            show-overflow-tooltip
          />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  knowledgeApi,
  type KnowledgeCoverage,
  type KnowledgeEntry,
  type KnowledgeEntryPage,
  type KnowledgeKind,
  type KnowledgeLayer,
  type KnowledgeLayerFilter,
  type KnowledgeMatchScope,
  type KnowledgeMatchScopeFilter,
  type KnowledgeReviewStatus,
  type KnowledgeReviewStatusFilter,
  type PaginatedTable,
  type PanelKnowledgeSummary,
} from '@/api/knowledge'

const activeTab = ref('genes')
const catalogPanels = ref<PanelKnowledgeSummary[]>([])
const selectedPanelId = ref('')
const panelsLoading = ref(false)

const coverage = ref<KnowledgeCoverage | null>(null)
const coverageLoading = ref(false)
const catalogData = ref<KnowledgeEntryPage | null>(null)
const entriesLoading = ref(false)

const catalogSearch = ref('')
const drugCatalogKind = ref<Extract<KnowledgeKind, 'drug' | 'targeted_drug'>>('drug')
const selectedLayer = ref<KnowledgeLayerFilter>('all')
const selectedReview = ref<KnowledgeReviewStatusFilter>('all')
const selectedScope = ref<KnowledgeMatchScopeFilter>('all')
const catalogPage = ref(1)
const catalogPageSize = ref(20)

const immuneData = ref<PaginatedTable>({ columns: [], rows: [], total: 0, page: 1, page_size: 50 })
const immuneLoading = ref(false)

let entriesRequestId = 0
let coverageRequestId = 0

const selectedPanel = computed(() =>
  catalogPanels.value.find((panel) => panel.panel_id === selectedPanelId.value) || null,
)
const catalogRows = computed(() => catalogData.value?.rows || [])
const catalogTotal = computed(() => catalogData.value?.total || 0)
const activeKind = computed<KnowledgeKind>(() => (
  activeTab.value === 'drugs' ? drugCatalogKind.value : 'gene'
))
const catalogWarnings = computed(() => {
  const values = [
    selectedPanel.value?.warning,
    ...(catalogData.value?.warnings || []),
    ...(coverage.value?.warnings || []),
  ].filter((value): value is string => Boolean(value))
  return [...new Set(values)]
})

const contentLabelMap: Record<string, string> = {
  intro: '基因简介',
  mutation_description: '基因变异说明',
  mutation_analysis: '基因变异解析',
  refinement_note: '策展备注',
  variant_level: '变异等级',
  event: '变异事件',
  benefit_drugs: '潜在获益药物',
  caution_drugs: '耐药或慎用药物',
  cgi_evidence_level: 'CGI 证据等级',
  civic_amp_category: 'CIViC/AMP 分类',
  cancer_context: '癌种上下文',
  drug_type: '药物类型',
  drug_name: '药物名称',
  header: '解析标题',
  relation: '基因变异与药物关联',
  clinical: '药物疗效临床解析',
  applicability: '适用条件',
  clinical_significance: '临床意义限定',
}

function panelStatusType(status: string): 'success' | 'warning' | 'info' {
  if (status === 'active') return 'success'
  if (status === 'pilot') return 'warning'
  return 'info'
}

function layerLabel(layer: KnowledgeLayer): string {
  return layer === 'reviewed_overlay' ? 'Panel Overlay' : '基础 Excel'
}

function layerTagType(layer: KnowledgeLayer): 'success' | 'info' {
  return layer === 'reviewed_overlay' ? 'success' : 'info'
}

function reviewLabel(status: KnowledgeReviewStatus): string {
  return {
    approved_for_runtime: '生产已启用',
    needs_review: '需审核',
    not_recorded: '未记录',
  }[status]
}

function reviewTagType(status: KnowledgeReviewStatus): 'success' | 'warning' | 'info' {
  if (status === 'approved_for_runtime') return 'success'
  if (status === 'needs_review') return 'warning'
  return 'info'
}

function scopeLabel(scope: KnowledgeMatchScope): string {
  return { gene: '基因级', variant: '位点级', event: '事件级' }[scope]
}

function reviewScopeLabel(scope: string): string {
  return {
    overlay_file: '文件级发布状态',
    source_row: '源数据行',
    entry_note: '条目备注',
    panel_rule: 'Panel 运行规则',
  }[scope] || scope || '未记录审核范围'
}

function reviewBasisLabel(basis: string): string {
  return {
    approved_review_policy: '文件声明仅将通过/修改后通过条目纳入生产 Overlay',
    approved_current_revision: '审批记录已绑定当前文件修订',
    current_revision_not_approved: '有历史审核策略，但未记录与当前 SHA 绑定的审批',
    enabled_panel_rule: '当前 Panel 包显式启用的运行规则',
    base_excel_has_no_review_field: '基础 Excel 无逐条审核字段',
    entry_source_note_requires_review: '条目备注明确标记需要审核',
    source_declares_review_needed: 'Overlay 源文件声明需要审核',
    no_explicit_review_record: '未找到明确审核记录',
    overlay_unavailable: 'Overlay 不可用',
  }[basis] || basis || '未记录审核依据'
}

function runtimeBehaviorLabel(value: string): string {
  return {
    override_base_on_match: '命中匹配条件时优先于基础层',
    fallback_when_no_reviewed_match: '无 Reviewed 匹配时作为回退',
    filtered_base_drug_candidate: '基础药物候选，生成时仍需经 Panel 规则过滤',
    base_part3_drug_narrative_fallback: '第三部分用药解读的基础回退文本',
    candidate_filtered_by_panel_policy: '第二部分候选条目，仍需经当前 Panel 政策过滤',
    disabled_by_panel_policy: '当前 Panel 未启用此候选决策库',
    panel_targeted_drug_override: '当前 Panel 运行时靶向药物 override',
  }[value] || value || '—'
}

function formatContent(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.map((item) => String(item)).join('、') || '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function contentItems(entry: KnowledgeEntry): Array<{ key: string; label: string; value: string }> {
  return Object.entries(entry.content)
    .map(([key, value]) => ({
      key,
      label: contentLabelMap[key] || key,
      value: formatContent(value),
    }))
    .filter((item) => item.value !== '—')
}

function contentSummary(entry: KnowledgeEntry): string {
  const keys = entry.kind === 'gene'
    ? ['intro', 'mutation_analysis', 'mutation_description']
    : ['drug_name', 'benefit_drugs', 'caution_drugs', 'relation', 'clinical', 'event']
  for (const key of keys) {
    const value = formatContent(entry.content[key])
    if (value !== '—') return value.length > 150 ? `${value.slice(0, 150)}…` : value
  }
  return '—'
}

function sourceLabel(entry: KnowledgeEntry): string {
  if (entry.provenance.source_db) {
    return `${entry.provenance.source_id} · ${entry.provenance.source_db}`
  }
  return entry.provenance.source_id || entry.provenance.source_type || '—'
}

function provenanceLocation(entry: KnowledgeEntry): string {
  if (entry.provenance.sheet) {
    const row = entry.provenance.row_number ? ` · 第 ${entry.provenance.row_number} 行` : ''
    return `${entry.provenance.sheet}${row}`
  }
  if (entry.provenance.origin_panel_id) {
    return `Panel ${entry.provenance.origin_panel_id}`
  }
  return '—'
}

function formatUpdatedAt(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

function errorMessage(error: any, fallback: string): string {
  return error?.response?.data?.detail || error?.message || fallback
}

async function fetchPanels() {
  panelsLoading.value = true
  try {
    const data = await knowledgeApi.getPanels()
    catalogPanels.value = data.panels || []
    const preferred = catalogPanels.value.find((panel) => panel.panel_id === 'crc_358_msi')
      || catalogPanels.value.find((panel) => panel.panel_id === 'crc_301_msi')
      || catalogPanels.value[0]
    selectedPanelId.value = preferred?.panel_id || ''
  } catch (error: any) {
    ElMessage.error(errorMessage(error, '加载 Panel 知识目录失败'))
  } finally {
    panelsLoading.value = false
  }
}

async function fetchCoverage() {
  if (!selectedPanelId.value) {
    coverage.value = null
    return
  }
  const requestId = ++coverageRequestId
  coverageLoading.value = true
  try {
    const data = await knowledgeApi.getCoverage(selectedPanelId.value)
    if (requestId === coverageRequestId) coverage.value = data
  } catch (error: any) {
    if (requestId === coverageRequestId) {
      coverage.value = null
      ElMessage.error(errorMessage(error, '加载知识库覆盖摘要失败'))
    }
  } finally {
    if (requestId === coverageRequestId) coverageLoading.value = false
  }
}

async function fetchEntries() {
  if (!selectedPanelId.value || activeTab.value === 'immune') return
  const requestId = ++entriesRequestId
  entriesLoading.value = true
  try {
    const data = await knowledgeApi.getEntries({
      panel_id: selectedPanelId.value,
      kind: activeKind.value,
      layer: selectedLayer.value,
      search: catalogSearch.value,
      review_status: selectedReview.value,
      match_scope: selectedScope.value,
      page: catalogPage.value,
      page_size: catalogPageSize.value,
    })
    if (requestId === entriesRequestId) catalogData.value = data
  } catch (error: any) {
    if (requestId === entriesRequestId) {
      catalogData.value = null
      ElMessage.error(errorMessage(error, '加载知识条目失败'))
    }
  } finally {
    if (requestId === entriesRequestId) entriesLoading.value = false
  }
}

async function fetchImmune() {
  immuneLoading.value = true
  try {
    immuneData.value = await knowledgeApi.getImmuneGenes()
  } catch (error: any) {
    ElMessage.error(errorMessage(error, '加载免疫基因基础层失败'))
  } finally {
    immuneLoading.value = false
  }
}

async function handlePanelChange() {
  catalogPage.value = 1
  catalogData.value = null
  coverage.value = null
  const jobs: Promise<void>[] = [fetchCoverage()]
  if (activeTab.value !== 'immune') jobs.push(fetchEntries())
  await Promise.all(jobs)
}

function handleSearch() {
  catalogPage.value = 1
  void fetchEntries()
}

function handleFilterChange() {
  catalogPage.value = 1
  void fetchEntries()
}

function handleDrugDomainChange() {
  catalogPage.value = 1
  catalogData.value = null
  void fetchEntries()
}

function handlePageChange(page: number) {
  catalogPage.value = page
  void fetchEntries()
}

function handlePageSizeChange(pageSize: number) {
  catalogPageSize.value = pageSize
  catalogPage.value = 1
  void fetchEntries()
}

watch(activeTab, (tab, previousTab) => {
  if (tab === 'immune') return
  catalogPage.value = 1
  if (previousTab === 'genes' || previousTab === 'drugs') catalogSearch.value = ''
  void fetchEntries()
})

onMounted(async () => {
  await Promise.all([fetchPanels(), fetchImmune()])
  if (selectedPanelId.value) {
    await Promise.all([fetchCoverage(), fetchEntries()])
  }
})
</script>

<style scoped>
.knowledge-page {
  min-width: 0;
}

.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 18px;
}

.page-heading h2 {
  margin: 0 0 6px;
}

.page-heading p {
  margin: 0;
  color: #667085;
  font-size: 14px;
}

.panel-picker {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #344054;
  font-size: 14px;
  font-weight: 600;
}

.panel-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.context-alert,
.immune-alert {
  margin-bottom: 12px;
}

.coverage-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.metric-card :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  min-height: 98px;
  padding: 16px;
}

.metric-card span {
  color: #667085;
  font-size: 13px;
}

.metric-card strong {
  margin: 7px 0 5px;
  color: #101828;
  font-size: 28px;
  line-height: 1;
}

.metric-card small {
  margin-top: auto;
  color: #98a2b3;
  line-height: 1.4;
}

.knowledge-tabs {
  margin-top: 4px;
}

.catalog-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.domain-switch {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
  color: #667085;
  font-size: 13px;
  line-height: 1.5;
}

.search-input {
  width: min(480px, 100%);
}

.catalog-pagination {
  justify-content: flex-end;
  margin-top: 14px;
}

.hgvs-cell,
.source-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.source-cell small,
.muted {
  color: #98a2b3;
}

.summary-text {
  display: -webkit-box;
  overflow: hidden;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.entry-detail {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
  gap: 28px;
  padding: 12px 28px 18px;
  background: #fafafa;
}

.detail-section h4 {
  margin: 0 0 12px;
  color: #344054;
}

.detail-row {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid #eaecf0;
}

.detail-row span {
  color: #667085;
  font-size: 13px;
  font-weight: 600;
}

.detail-row p {
  margin: 0;
  color: #344054;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.provenance-section dl {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
}

.provenance-section dt {
  color: #667085;
  font-size: 13px;
  font-weight: 600;
}

.provenance-section dd {
  margin: 0;
  color: #344054;
  overflow-wrap: anywhere;
}

@media (max-width: 1100px) {
  .coverage-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .page-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (max-width: 768px) {
  .coverage-grid,
  .entry-detail {
    grid-template-columns: 1fr;
  }

  .panel-picker {
    align-items: flex-start;
    flex-direction: column;
    width: 100%;
  }

  .panel-picker :deep(.el-select),
  .catalog-toolbar :deep(.el-select),
  .search-input {
    width: 100% !important;
  }

  .detail-row {
    grid-template-columns: 1fr;
    gap: 5px;
  }
}
</style>
