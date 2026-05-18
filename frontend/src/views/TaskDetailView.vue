<template>
  <div class="task-detail">
    <div class="page-head">
      <div>
        <el-button text :icon="ArrowLeft" @click="$router.push('/tasks')">返回任务队列</el-button>
        <h2>任务质控详情</h2>
        <p>{{ taskId }}</p>
      </div>
      <div class="head-actions">
        <el-button :icon="Refresh" @click="fetchAll">刷新</el-button>
        <el-button
          v-if="task?.status === 'completed' && task.task_type === 'single'"
          type="primary"
          :icon="Download"
          @click="downloadReport"
        >
          下载报告
        </el-button>
      </div>
    </div>

    <el-skeleton v-if="loading" :rows="8" animated />

    <template v-else>
      <section class="summary-band">
        <div class="summary-item">
          <span>任务状态</span>
          <el-tag :type="statusTagType(task?.status || '')">{{ statusLabel(task?.status || '-') }}</el-tag>
        </div>
        <div class="summary-item">
          <span>QA 状态</span>
          <el-tag :type="qaTagType(task?.qa_status || qaReport?.status)">
            {{ task?.qa_status || qaReport?.status || '未生成' }}
          </el-tag>
        </div>
        <div class="summary-item">
          <span>Diff 门禁</span>
          <el-tag :type="diffGateTagType">
            {{ task?.diff_status || reportDiff?.status || '未运行' }}
          </el-tag>
        </div>
        <div class="summary-item">
          <span>项目类型</span>
          <strong>{{ task?.project_type || '-' }}</strong>
        </div>
        <div class="summary-item">
          <span>耗时</span>
          <strong>{{ task?.duration_seconds ? `${task.duration_seconds.toFixed(1)}s` : '-' }}</strong>
        </div>
      </section>

      <el-alert
        v-if="qaLoadError"
        :title="qaLoadError"
        type="warning"
        show-icon
        :closable="false"
        class="section-gap"
      />

      <section class="qa-grid section-gap">
        <div class="qa-panel issues-panel">
          <div class="panel-title">
            <span>问题列表</span>
            <el-tag size="small" :type="issueRows.length ? 'danger' : 'success'">
              {{ issueRows.length ? `${issueRows.length} 条` : '无问题' }}
            </el-tag>
          </div>
          <el-empty v-if="!issueRows.length" description="当前 QA 未记录错误或警告" :image-size="70" />
          <el-table v-else :data="issueRows" size="small" border>
            <el-table-column label="级别" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.level === 'error' ? 'danger' : 'warning'">
                  {{ row.level }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="code" label="代码" width="190" show-overflow-tooltip />
            <el-table-column prop="message" label="说明" min-width="280" show-overflow-tooltip />
          </el-table>
        </div>

        <div class="qa-panel render-panel">
          <div class="panel-title">
            <span>视觉渲染</span>
            <el-tag size="small" :type="qaTagType(visualRender?.status)">
              {{ visualRender?.status || '未运行' }}
            </el-tag>
          </div>
          <div class="render-actions">
            <el-button :loading="rendering" type="primary" plain @click="renderFirstPage">
              渲染首页
            </el-button>
            <span>按需生成 PNG，用于检查页眉、表格边框、空白页和版式。</span>
          </div>
          <el-alert
            v-if="visualRender?.message"
            :title="visualRender.message"
            :type="visualRender.status === 'PASS' ? 'success' : 'warning'"
            show-icon
            :closable="false"
          />
          <img
            v-if="firstRenderedPage"
            class="render-preview"
            :src="firstRenderedPage.url"
            alt="Rendered report page"
          />
          <el-collapse v-if="visualRender?.stderr_tail || visualRender?.command" class="debug-collapse">
            <el-collapse-item title="渲染错误细节" name="render-debug">
              <pre>{{ renderDebugText }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
      </section>

      <section class="qa-panel section-gap">
        <div class="panel-title">
          <span>报告对比</span>
          <el-tag size="small" :type="diffGateTagType">
            {{ reportDiff?.status || task?.diff_status || '未运行' }}
          </el-tag>
        </div>
        <div class="diff-toolbar">
          <el-button
            type="primary"
            plain
            :loading="autoDiffing"
            :disabled="!task?.output_path"
            @click="compareRegisteredReference"
          >
            使用基准库对比
          </el-button>
          <el-upload
            v-model:file-list="referenceFileList"
            accept=".docx"
            :auto-upload="false"
            :limit="1"
            :on-change="handleReferenceFileChange"
            :on-remove="clearReferenceFile"
          >
            <el-button :icon="UploadFilled">选择正确报告 DOCX</el-button>
          </el-upload>
          <el-select v-model="diffFailOn" style="width: 150px">
            <el-option label="仅 FAIL 阻断" value="fail" />
            <el-option label="WARN 也阻断" value="warn" />
          </el-select>
          <el-button
            type="primary"
            :loading="diffing"
            :disabled="!referenceFile || !task?.output_path"
            @click="compareReport"
          >
            对比当前报告
          </el-button>
          <el-button
            v-if="reportDiff"
            :icon="Download"
            @click="downloadDiff('report_diff.md')"
          >
            下载摘要
          </el-button>
          <el-button
            v-if="reportDiff"
            @click="downloadDiff('report_diff.json')"
          >
            JSON
          </el-button>
        </div>
        <div v-if="reportDiff?.reference_report" class="reference-strip">
          <span>基准</span>
          <strong>{{ reportDiff.reference_report.name || reportDiff.reference_report.id || '手动上传' }}</strong>
          <em v-if="reportDiff.reference_report.panel_id">
            {{ reportDiff.reference_report.panel_id }} / {{ reportDiff.reference_report.case_id }}
          </em>
        </div>
        <el-alert
          v-if="reportDiff"
          :title="diffSummaryTitle"
          :type="reportDiff.status === 'PASS' ? 'success' : reportDiff.status === 'FAIL' ? 'error' : 'warning'"
          show-icon
          :closable="false"
          class="diff-alert"
        />
        <div v-if="reportDiff" class="diff-metrics">
          <div class="metric-box">
            <span>门禁</span>
            <strong :class="reportDiff.gate?.passed ? 'ok-text' : 'bad-text'">
              {{ reportDiff.gate?.passed ? '通过' : '阻断' }}
            </strong>
          </div>
          <div class="metric-box">
            <span>失败</span>
            <strong>{{ reportDiff.summary?.failures || 0 }}</strong>
          </div>
          <div class="metric-box">
            <span>警告</span>
            <strong>{{ reportDiff.summary?.warnings || 0 }}</strong>
          </div>
          <div class="metric-box">
            <span>文本相似度</span>
            <strong>{{ formatSimilarity(reportDiff.summary?.text_similarity) }}</strong>
          </div>
          <div class="metric-box">
            <span>表格数</span>
            <strong>
              {{ reportDiff.summary?.table_count?.reference ?? '-' }}
              →
              {{ reportDiff.summary?.table_count?.candidate ?? '-' }}
            </strong>
          </div>
        </div>
        <el-table
          v-if="diffIssueRows.length"
          :data="diffIssueRows"
          size="small"
          border
          class="diff-table"
        >
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.level === 'error' ? 'danger' : 'warning'">
                {{ row.level }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="section" label="区域" width="100" />
          <el-table-column prop="code" label="代码" width="190" show-overflow-tooltip />
          <el-table-column prop="message" label="说明" min-width="360" show-overflow-tooltip />
        </el-table>
        <el-collapse v-if="reportDiff" class="debug-collapse">
          <el-collapse-item title="差异样本" name="diff-samples">
            <pre>{{ diffSampleText }}</pre>
          </el-collapse-item>
        </el-collapse>
      </section>

      <section class="qa-panel section-gap">
        <div class="panel-title">
          <span>QA 检查项</span>
          <el-tag size="small">{{ checkRows.length }} 项</el-tag>
        </div>
        <el-table :data="checkRows" size="small" border>
          <el-table-column prop="name" label="检查项" width="250" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="qaTagType(row.status)">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="摘要" min-width="320" show-overflow-tooltip />
        </el-table>
      </section>

      <section class="qa-panel section-gap">
        <div class="panel-title">
          <span>字段来源</span>
          <el-tag size="small">{{ provenanceRows.length }} 个字段</el-tag>
        </div>
        <el-alert
          v-if="provenanceLoadError"
          :title="provenanceLoadError"
          type="info"
          show-icon
          :closable="false"
        />
        <el-table v-else :data="provenanceRows" size="small" border>
          <el-table-column prop="field" label="字段" width="170" />
          <el-table-column prop="source" label="来源" width="120" />
          <el-table-column prop="value" label="最终值" min-width="160" show-overflow-tooltip />
          <el-table-column prop="source_key" label="来源键" min-width="160" show-overflow-tooltip />
          <el-table-column prop="source_detail" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="隐私" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.sensitive" size="small" type="warning">已脱敏</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="qa-panel section-gap">
        <div class="panel-title">
          <span>后处理器</span>
          <el-tag size="small">{{ processorRows.length }} 个步骤</el-tag>
        </div>
        <el-table :data="processorRows" size="small" border>
          <el-table-column prop="name" label="步骤" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'ERROR' ? 'danger' : 'success'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_ms" label="耗时(ms)" width="110" />
          <el-table-column prop="error" label="错误" min-width="260" show-overflow-tooltip />
        </el-table>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowLeft, Download, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  reportApi,
  type ReportDiffResult,
  type TaskStatus,
  type VisualRenderResult,
} from '@/api/report'

const route = useRoute()
const taskId = String(route.params.id || '')

const loading = ref(false)
const rendering = ref(false)
const diffing = ref(false)
const autoDiffing = ref(false)
const task = ref<TaskStatus | null>(null)
const qaReport = ref<Record<string, any> | null>(null)
const provenance = ref<Record<string, any> | null>(null)
const visualRender = ref<VisualRenderResult | null>(null)
const reportDiff = ref<ReportDiffResult | null>(null)
const referenceFile = ref<File | null>(null)
const referenceFileList = ref<any[]>([])
const diffFailOn = ref<'fail' | 'warn'>('fail')
const qaLoadError = ref('')
const provenanceLoadError = ref('')

const issueRows = computed(() => qaReport.value?.issues || [])
const processorRows = computed(() => qaReport.value?.post_processors || [])

const checkRows = computed(() => {
  const checks = qaReport.value?.checks || {}
  return Object.entries(checks).map(([name, value]) => {
    const item = (value || {}) as Record<string, any>
    return {
      name,
      status: item.status || '-',
      summary: item.message || summarizeCheck(item),
    }
  })
})

const provenanceRows = computed(() => {
  const fields = provenance.value?.fields || {}
  return Object.entries(fields).map(([field, value]) => {
    const item = (value || {}) as Record<string, any>
    return {
      field,
      value: stringifyValue(item.value),
      source: item.source || '-',
      source_key: item.source_key || '-',
      source_detail: item.source_detail || '-',
      sensitive: Boolean(item.sensitive),
    }
  })
})

const firstRenderedPage = computed(() => visualRender.value?.rendered_pages?.[0] || null)
const diffIssueRows = computed(() => reportDiff.value?.issues || [])

const diffGateTagType = computed(() => {
  if (task.value?.diff_gate_passed === false || reportDiff.value?.gate?.passed === false) return 'danger'
  return qaTagType(reportDiff.value?.status || task.value?.diff_status)
})

const diffSummaryTitle = computed(() => {
  if (!reportDiff.value) return ''
  const gate = reportDiff.value.gate?.passed ? '门禁通过' : '门禁阻断'
  const failures = reportDiff.value.summary?.failures || 0
  const warnings = reportDiff.value.summary?.warnings || 0
  return `${gate}：${reportDiff.value.status}，失败 ${failures}，警告 ${warnings}`
})

const diffSampleText = computed(() => {
  if (!reportDiff.value) return ''
  const sections = reportDiff.value.sections || {}
  return JSON.stringify(
    {
      text: sections.text?.samples || [],
      tables: sections.tables?.samples || [],
      styles: sections.styles?.samples || [],
      qa: sections.qa?.samples || [],
    },
    null,
    2,
  )
})

const renderDebugText = computed(() => {
  if (!visualRender.value) return ''
  return JSON.stringify(
    {
      stage: visualRender.value.stage,
      error: visualRender.value.error,
      command: visualRender.value.command,
      stderr_tail: visualRender.value.stderr_tail,
      stdout_tail: visualRender.value.stdout_tail,
    },
    null,
    2,
  )
})

function summarizeCheck(item: Record<string, any>) {
  const entries = Object.entries(item)
    .filter(([key]) => key !== 'status')
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${stringifyValue(value)}`)
  return entries.join('；') || '-'
}

function stringifyValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function formatSimilarity(value?: number | null) {
  if (value === null || value === undefined) return '-'
  return `${(value * 100).toFixed(2)}%`
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    completed: 'success',
    failed: 'danger',
    running: 'warning',
    pending: 'info',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    running: '运行中',
    pending: '待执行',
    cancelled: '已取消',
  }
  return map[status] || status
}

function qaTagType(status?: string | null) {
  const map: Record<string, string> = {
    PASS: 'success',
    WARN: 'warning',
    FAIL: 'danger',
    SKIP: 'info',
  }
  return status ? map[status] || 'info' : 'info'
}

async function fetchAll() {
  loading.value = true
  qaLoadError.value = ''
  provenanceLoadError.value = ''
  try {
    task.value = await reportApi.getTaskStatus(taskId)
    try {
      reportDiff.value = await reportApi.getReportDiff(taskId)
    } catch {
      reportDiff.value = null
    }
    try {
      qaReport.value = await reportApi.getQaReport(taskId)
    } catch (err: any) {
      qaReport.value = null
      qaLoadError.value = err.response?.data?.detail || 'QA 报告尚未生成'
    }
    try {
      provenance.value = await reportApi.getFieldProvenance(taskId)
    } catch (err: any) {
      provenance.value = null
      provenanceLoadError.value = err.response?.data?.detail || '字段来源报告尚未生成'
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '任务详情加载失败')
  } finally {
    loading.value = false
  }
}

async function renderFirstPage() {
  rendering.value = true
  try {
    visualRender.value = await reportApi.renderVisual(taskId, {
      mode: 'first',
      dpi: 120,
      timeout_seconds: 60,
    })
    if (visualRender.value.status === 'PASS') {
      ElMessage.success('首页渲染完成')
    } else {
      ElMessage.warning(visualRender.value.message || '视觉渲染未通过')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || '视觉渲染请求失败')
  } finally {
    rendering.value = false
  }
}

function handleReferenceFileChange(file: any) {
  referenceFile.value = file.raw || null
  referenceFileList.value = [file]
  reportDiff.value = null
}

function clearReferenceFile() {
  referenceFile.value = null
  referenceFileList.value = []
}

async function compareReport() {
  if (!referenceFile.value) {
    ElMessage.warning('请先选择正确报告 DOCX')
    return
  }
  diffing.value = true
  try {
    reportDiff.value = await reportApi.compareReport(taskId, referenceFile.value, {
      fail_on: diffFailOn.value,
      max_samples: 50,
    })
    task.value = await reportApi.getTaskStatus(taskId)
    if (reportDiff.value.gate?.passed) {
      ElMessage.success('报告对比通过')
    } else {
      ElMessage.warning('报告对比存在阻断项')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || err.response?.data?.error || '报告对比失败')
  } finally {
    diffing.value = false
  }
}

async function compareRegisteredReference() {
  autoDiffing.value = true
  try {
    reportDiff.value = await reportApi.compareReportWithRegisteredReference(taskId, {
      fail_on: diffFailOn.value,
      max_samples: 50,
    })
    task.value = await reportApi.getTaskStatus(taskId)
    if (reportDiff.value.gate?.passed) {
      ElMessage.success('基准库对比通过')
    } else {
      ElMessage.warning('基准库对比存在阻断项')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '未找到匹配基准报告')
  } finally {
    autoDiffing.value = false
  }
}

function downloadDiff(artifact: 'report_diff.json' | 'report_diff.md') {
  window.open(reportApi.getDiffDownloadUrl(taskId, artifact), '_blank')
}

function downloadReport() {
  window.open(reportApi.getDownloadUrl(taskId), '_blank')
}

onMounted(fetchAll)
</script>

<style scoped>
.task-detail {
  color: #1f2933;
}

.page-head,
.head-actions,
.panel-title,
.render-actions {
  display: flex;
  align-items: center;
}

.diff-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 14px;
}

.diff-alert {
  margin: 0 14px 14px;
}

.reference-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px 12px;
  color: #667085;
  font-size: 13px;
}

.reference-strip strong {
  color: #1f2933;
}

.reference-strip em {
  font-style: normal;
  color: #475467;
}

.diff-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 0;
  margin: 0 14px 14px;
  border: 1px solid #d9e2ec;
}

.metric-box {
  min-height: 64px;
  padding: 10px 12px;
  border-right: 1px solid #d9e2ec;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.metric-box:last-child {
  border-right: 0;
}

.metric-box span {
  color: #667085;
  font-size: 12px;
}

.metric-box strong {
  font-size: 16px;
}

.ok-text {
  color: #16803c;
}

.bad-text {
  color: #b42318;
}

.diff-table {
  margin-top: 0;
}

.page-head {
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.page-head h2 {
  margin: 6px 0 4px;
  font-size: 24px;
  font-weight: 650;
}

.page-head p {
  margin: 0;
  color: #667085;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
}

.head-actions {
  gap: 8px;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border: 1px solid #d9e2ec;
  background: #f8fafc;
}

.summary-item {
  min-height: 76px;
  padding: 14px 16px;
  border-right: 1px solid #d9e2ec;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.summary-item:last-child {
  border-right: 0;
}

.summary-item span {
  color: #667085;
  font-size: 13px;
}

.summary-item strong {
  font-size: 16px;
}

.section-gap {
  margin-top: 18px;
}

.qa-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
  gap: 18px;
}

.qa-panel {
  border: 1px solid #d9e2ec;
  background: #fff;
}

.panel-title {
  justify-content: space-between;
  min-height: 48px;
  padding: 0 14px;
  border-bottom: 1px solid #e6edf3;
  font-weight: 650;
}

.issues-panel,
.render-panel {
  min-height: 240px;
}

.render-actions {
  gap: 10px;
  padding: 14px;
  color: #667085;
  font-size: 13px;
}

.render-panel :deep(.el-alert) {
  margin: 0 14px 14px;
}

.render-preview {
  display: block;
  width: calc(100% - 28px);
  max-height: 680px;
  object-fit: contain;
  margin: 0 14px 14px;
  border: 1px solid #d9e2ec;
  background: #f8fafc;
}

.debug-collapse {
  margin: 0 14px 14px;
}

pre {
  max-height: 300px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #344054;
}

@media (max-width: 980px) {
  .summary-band,
  .qa-grid,
  .diff-metrics {
    grid-template-columns: 1fr;
  }

  .summary-item {
    border-right: 0;
    border-bottom: 1px solid #d9e2ec;
  }

  .summary-item:last-child {
    border-bottom: 0;
  }

  .metric-box {
    border-right: 0;
    border-bottom: 1px solid #d9e2ec;
  }

  .metric-box:last-child {
    border-bottom: 0;
  }

  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
