<template>
  <div>
    <h2>生成报告</h2>

    <el-card shadow="hover" style="margin-bottom: 20px">
      <template #header>
        <div class="batch-head">
          <strong>生产批量生成</strong>
          <el-tag size="small" type="warning">多 Excel</el-tag>
        </div>
      </template>
      <div class="batch-controls">
        <el-upload
          drag
          multiple
          accept=".xlsx"
          :auto-upload="false"
          :file-list="batchFileList"
          :on-change="handleBatchFileChange"
          :on-remove="handleBatchFileRemove"
        >
          <el-icon class="el-icon--upload" :size="34"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽多个 Excel 到此处，或<em>点击选择</em></div>
          <template #tip>
            <div class="el-upload__tip">适合生产批量出报告；临时文件 ._* / ~$ 会被拒绝。</div>
          </template>
        </el-upload>
        <div class="batch-options">
          <el-select v-model="batchProjectType" placeholder="项目类型（可自动识别）" clearable>
            <el-option
              v-for="option in batchGenerationProjectOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-select
            v-if="batchTemplateOptions.length"
            v-model="batchTemplateName"
            placeholder="报告模板"
            clearable
          >
            <el-option
              v-for="option in batchTemplateOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-checkbox
            v-if="canUseGoldenMode"
            v-model="batchReferenceGateRequired"
          >
            金标准验收（未命中基准即阻断）
          </el-checkbox>
          <el-button
            type="primary"
            :loading="batchGenerating"
            :disabled="!batchFiles.length"
            @click="startBatchGenerate"
          >
            批量生成
          </el-button>
        </div>
      </div>
      <div v-if="batchTask" class="batch-progress">
        <div class="batch-progress-title">
          <strong>{{ statusLabel(batchTask.status) }}</strong>
          <span>
            {{ batchTask.completed_files }}/{{ batchTask.total_files }} 完成，{{ batchTask.failed_files }} 失败
            <template v-if="batchTask.cancelled_files">，{{ batchTask.cancelled_files }} 取消</template>
          </span>
        </div>
        <el-progress
          :percentage="batchProgressPercent"
          :status="batchTask.status === 'failed' || batchTask.status === 'partial_failed' ? 'exception' : batchTask.status === 'completed' ? 'success' : undefined"
        />
        <div class="batch-actions">
          <el-button @click="$router.push(`/tasks/${batchTask.id}`)">查看批量详情</el-button>
          <el-popconfirm
            v-if="isActiveTaskStatus(batchTask.status)"
            title="确认取消当前批量任务？正在生成的文件会完成本轮后停止。"
            @confirm="cancelCurrentBatch"
          >
            <template #reference>
              <el-button type="danger" plain :loading="batchCancelling">取消任务</el-button>
            </template>
          </el-popconfirm>
          <el-button
            v-if="canRetryBatch"
            type="warning"
            plain
            :loading="batchRetrying"
            @click="retryFailedBatch"
          >
            重试失败文件
          </el-button>
          <el-button
            v-if="isBatchTerminal && batchTask.completed_files > 0"
            type="primary"
            :loading="batchDownloading"
            @click="downloadBatchZip"
          >
            {{ batchDownloading ? '正在下载 ZIP' : '下载成功报告 ZIP' }}
          </el-button>
        </div>
        <div v-if="batchDownloadStatus" class="download-status">
          {{ batchDownloadStatus }}
        </div>
        <el-table
          v-if="batchResultRows.length"
          :data="batchResultRows"
          size="small"
          border
          class="batch-table"
        >
          <el-table-column prop="index" label="#" width="70" />
          <el-table-column prop="excel_filename" label="Excel" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="statusTagType(row.status)">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="project_name" label="项目" min-width="180" show-overflow-tooltip />
          <el-table-column label="QA" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.qa_status" size="small" :type="row.qa_status === 'FAIL' ? 'danger' : row.qa_status === 'WARN' ? 'warning' : 'success'">
                {{ row.qa_status }}
              </el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="duration_seconds" label="耗时" width="100">
            <template #default="{ row }">
              {{ row.duration_seconds ? `${row.duration_seconds.toFixed(1)}s` : '-' }}
            </template>
          </el-table-column>
          <el-table-column label="说明" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.errors?.[0] || row.warnings?.[0] || '-' }}
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- Step 1: Upload Excel -->
    <el-card shadow="hover" style="margin-bottom: 20px">
      <template #header><strong>1. 上传 Excel 文件</strong></template>
      <el-upload
        drag
        accept=".xlsx"
        v-loading="excelStore.loading"
        element-loading-text="正在上传并解析 Excel，请稍候..."
        :disabled="excelStore.loading"
        :auto-upload="false"
        :show-file-list="false"
        @change="handleFileChange"
      >
        <el-icon class="el-icon--upload" :size="40"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          <template v-if="excelStore.loading">
            正在解析 Excel，请稍候...
          </template>
          <template v-else>
            拖拽文件到此处，或<em>点击上传</em>
          </template>
        </div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx 格式的基因检测 Excel 文件</div>
        </template>
      </el-upload>

      <el-alert
        v-if="uploadStatusMessage"
        :title="uploadStatusMessage"
        :type="uploadStatusType"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />

      <div v-if="excelStore.upload" style="margin-top: 16px">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="文件名">{{ excelStore.upload.original_filename }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ (excelStore.upload.file_size_bytes / 1024).toFixed(1) }} KB</el-descriptions-item>
          <el-descriptions-item label="Sheet 数量">{{ excelStore.upload.sheet_names.length }}</el-descriptions-item>
          <el-descriptions-item label="检测项目类型">
            <el-tag v-if="excelStore.upload.detected_project_type" type="success">
              {{ excelStore.upload.detected_project_name || excelStore.upload.detected_project_type }}
            </el-tag>
            <el-tag v-else type="warning">未识别</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="识别置信度">
            {{ detectionConfidenceLabel }}
          </el-descriptions-item>
          <el-descriptions-item label="报告模板">
            {{ selectedTemplateLabel }}
          </el-descriptions-item>
        </el-descriptions>

        <div class="production-check">
          <div class="check-head">
            <div>
              <strong>生成前核对</strong>
              <span>{{ productionCheckSubtitle }}</span>
            </div>
            <el-tag :type="productionReadiness.type" size="large">
              {{ productionReadiness.label }}
            </el-tag>
          </div>

          <div class="check-grid">
            <div v-for="item in productionCheckCards" :key="item.label" class="check-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <em>{{ item.detail }}</em>
            </div>
          </div>

          <div v-if="deliveryRiskItems.length" class="risk-panel">
            <div class="risk-title">
              <strong>交付风险提示</strong>
              <span>{{ deliveryRiskItems.length }} 项需确认</span>
            </div>
            <div class="risk-list">
              <div v-for="item in deliveryRiskItems" :key="item.key" class="risk-item">
                <el-tag size="small" :type="item.type">{{ item.level }}</el-tag>
                <span>{{ item.message }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Validation warnings -->
        <div v-if="excelStore.upload.validation_warnings?.length" style="margin-top: 12px">
          <el-alert
            v-for="(w, i) in excelStore.upload.validation_warnings"
            :key="i"
            :title="w.message"
            :type="w.level === 'error' ? 'error' : w.level === 'warning' ? 'warning' : 'info'"
            show-icon
            :closable="false"
            style="margin-bottom: 4px"
          />
        </div>

        <div v-if="excelStore.previewSummary" class="upload-preview">
          <div class="preview-title">
            <strong>上传后结果预览</strong>
            <el-tag size="small" type="info">生成前</el-tag>
          </div>
          <div class="preview-metrics">
            <div v-for="metric in previewMetricCards" :key="metric.label" class="preview-metric">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>
          <div class="preview-biomarkers">
            <div v-for="item in previewBiomarkerCards" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <em>{{ item.detail }}</em>
            </div>
          </div>
          <el-alert
            v-if="previewManualReviewItems.length"
            :title="previewManualReviewItems.join('；')"
            type="warning"
            show-icon
            :closable="false"
            class="preview-alert"
          />
          <div class="preview-tables">
            <div>
              <div class="preview-table-title">
                关键变异
                <span v-if="previewVariantTotalText">{{ previewVariantTotalText }}</span>
              </div>
              <el-table :data="previewVariantRows" size="small" border>
                <el-table-column prop="gene" label="基因" width="100" show-overflow-tooltip />
                <el-table-column prop="variant_site" label="变异" min-width="190" show-overflow-tooltip />
                <el-table-column prop="classification" label="等级" width="90" show-overflow-tooltip />
                <el-table-column prop="frequency" label="丰度" width="90" show-overflow-tooltip />
                <el-table-column prop="benefit_drugs" label="获益药物" min-width="150" show-overflow-tooltip />
                <el-table-column prop="caution_drugs" label="耐药/慎用" min-width="150" show-overflow-tooltip />
              </el-table>
            </div>
            <div>
              <div class="preview-table-title">
                用药提示
                <span v-if="previewDrugTotalText">{{ previewDrugTotalText }}</span>
              </div>
              <el-table :data="previewDrugRows" size="small" border>
                <el-table-column prop="gene" label="基因" width="100" show-overflow-tooltip />
                <el-table-column prop="variant_site" label="变异" min-width="180" show-overflow-tooltip />
                <el-table-column prop="benefit_drugs" label="潜在获益" min-width="160" show-overflow-tooltip />
                <el-table-column prop="caution_drugs" label="耐药/慎用" min-width="160" show-overflow-tooltip />
              </el-table>
            </div>
          </div>
        </div>

        <!-- Sheet tabs preview -->
        <el-tabs
          v-if="excelStore.sheets.length > 0 && excelStore.isPersistentUpload"
          style="margin-top: 12px"
        >
          <el-tab-pane
            v-for="sheet in excelStore.sheets"
            :key="sheet.name"
            :label="`${sheet.name} (${sheet.rows}行)`"
            :name="sheet.name"
            lazy
          >
            <SheetPreview :upload-id="excelStore.upload!.upload_id" :sheet-name="sheet.name" />
          </el-tab-pane>
        </el-tabs>
        <el-alert
          v-else-if="excelStore.sheets.length > 0"
          type="info"
          show-icon
          :closable="false"
          style="margin-top: 12px"
          :title="`已识别 ${excelStore.sheets.length} 个 Sheet。当前使用${generationMode === 'async' ? '后台异步' : '无状态'}生成模式。`"
        />
      </div>
    </el-card>

    <!-- Step 2: Clinical Info Form -->
    <el-card v-if="excelStore.upload" shadow="hover" style="margin-bottom: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <strong>2. 临床信息</strong>
          <div style="display: flex; gap: 12px; align-items: center">
            <el-select
              v-model="projectType"
              placeholder="项目类型"
              style="width: 250px"
              clearable
            >
              <el-option
                v-for="option in generationProjectOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
            <el-select
              v-if="templateOptions.length"
              v-model="templateName"
              placeholder="报告模板"
              style="width: 270px"
              clearable
            >
              <el-option
                v-for="option in templateOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
        </div>
      </template>
      <DynamicClinicalForm
        :schema="form.schema.value"
        :form-data="form.formData"
        :errors="form.errors.value"
        :loading="form.loading.value"
        @update-field="form.setValue"
      />
      <el-alert
        v-if="enrichmentMessage"
        :title="enrichmentMessage"
        :type="excelStore.patientEnrichment?.found ? 'success' : 'warning'"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />
      <el-alert
        v-for="(warning, i) in excelStore.patientEnrichment?.warnings || []"
        :key="`enrichment-warning-${i}`"
        :title="warning"
        type="warning"
        show-icon
        :closable="false"
        style="margin-top: 8px"
      />
    </el-card>

    <!-- Step 3: Generate -->
    <el-card v-if="excelStore.upload" shadow="hover">
      <template #header><strong>3. 生成报告</strong></template>
      <el-checkbox
        v-if="canUseGoldenMode"
        v-model="singleReferenceGateRequired"
        style="margin-right: 16px"
      >
        金标准验收（未命中基准即阻断）
      </el-checkbox>
      <el-button
        type="primary"
        size="large"
        :loading="generating"
        :disabled="!canGenerate"
        @click="handleGenerate"
      >
        {{ generating ? '提交中' : '生成报告' }}
      </el-button>

      <div v-if="singleTask && !result" class="single-progress">
        <div class="single-progress-title">
          <strong>{{ statusLabel(singleTask.status) }}</strong>
          <span>
            任务 {{ shortTaskId(singleTask.id) }}
            <template v-if="singleTask.duration_seconds">
              · {{ singleTask.duration_seconds.toFixed(1) }}s
            </template>
          </span>
        </div>
        <el-progress
          :percentage="singleProgressPercent"
          :status="singleTask.status === 'failed' ? 'exception' : singleTask.status === 'completed' ? 'success' : undefined"
        />
        <div class="single-actions">
          <el-button @click="$router.push(`/tasks/${singleTask.id}`)">
            {{ isControlledLungProject ? '查看草稿与审核状态' : '查看任务详情' }}
          </el-button>
          <el-popconfirm
            v-if="singleTask.status === 'running' || singleTask.status === 'pending'"
            title="确认取消当前报告生成任务？"
            @confirm="cancelCurrentSingle"
          >
            <template #reference>
              <el-button type="danger" plain :loading="singleCancelling">取消任务</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>

      <!-- Result -->
      <div v-if="result" style="margin-top: 16px">
        <el-result
          :icon="result.success ? 'success' : 'error'"
          :title="result.success ? '报告生成成功' : '报告生成失败'"
          :sub-title="result.duration_seconds ? `耗时 ${result.duration_seconds.toFixed(1)} 秒` : ''"
        >
          <template #extra>
            <el-button
              v-if="result.success && result.task_id"
              type="primary"
              :loading="singleDownloading"
              @click="downloadGenerated(result)"
            >
              {{ singleDownloading
                ? '正在下载'
                : isControlledLungProject
                  ? '下载报告草稿'
                  : '下载报告' }}
            </el-button>
            <el-button
              v-if="result.task_id"
              @click="$router.push(`/tasks/${result.task_id}`)"
            >
              {{ isControlledLungProject ? '查看质控与审核状态' : '查看质控详情' }}
            </el-button>
          </template>
        </el-result>
        <div v-if="singleDownloadStatus" class="download-status">
          {{ singleDownloadStatus }}
        </div>
        <el-alert
          v-if="result.success && isControlledLungProject"
          title="肺癌待审草稿已生成，可先下载查看 Word；核对完成后可在任务详情记录审核状态。"
          type="info"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-if="result.qa_status"
          :title="`QA 状态：${result.qa_status}`"
          :type="result.qa_status === 'PASS' ? 'success' : result.qa_status === 'FAIL' ? 'error' : 'warning'"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-if="result.diff_auto_ran"
          :title="`自动 Diff：${result.diff_status || '-'}，基准：${result.diff_reference_name || result.diff_reference_id || '-'}`"
          :type="result.diff_gate_passed === false ? 'error' : result.diff_status === 'WARN' ? 'warning' : 'success'"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-for="(err, i) in result.errors"
          :key="i"
          :title="err"
          type="error"
          show-icon
          :closable="false"
          style="margin-bottom: 4px"
        />
        <el-alert
          v-for="(warn, i) in result.warnings"
          :key="'w' + i"
          :title="warn"
          type="warning"
          show-icon
          :closable="false"
          style="margin-bottom: 4px"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useExcelStore } from '@/stores/excel'
import { useAuthStore } from '@/stores/auth'
import { projectDisplayName, useDynamicForm } from '@/composables/useDynamicForm'
import {
  reportApi,
  type BatchResultItem,
  type DownloadProgress,
  type GenerateRequest,
  type GenerateResult,
  type TaskStatus,
} from '@/api/report'
import DynamicClinicalForm from '@/components/clinical/DynamicClinicalForm.vue'
import SheetPreview from '@/components/excel/SheetPreview.vue'

const excelStore = useExcelStore()
const authStore = useAuthStore()

const projectType = ref<string | null>(null)
const templateName = ref<string | null>(null)
const generating = ref(false)
const result = ref<GenerateResult | null>(null)
const singleTask = ref<TaskStatus | null>(null)
const singleCancelling = ref(false)
const uploadError = ref('')
const selectedFileName = ref('')
const generationMode = import.meta.env.VITE_REPORT_GENERATION_MODE || 'async'
const batchFiles = ref<File[]>([])
const batchFileList = ref<any[]>([])
const batchProjectType = ref<string | null>(null)
const batchTemplateName = ref<string | null>(null)
const batchGenerating = ref(false)
const batchRetrying = ref(false)
const batchCancelling = ref(false)
const batchDownloading = ref(false)
const batchDownloadStatus = ref('')
const singleDownloading = ref(false)
const singleDownloadStatus = ref('')
const batchTask = ref<TaskStatus | null>(null)
const batchResultRows = ref<BatchResultItem[]>([])
const batchIdempotencyKey = ref<string | null>(null)
const singleReferenceGateRequired = ref(false)
const batchReferenceGateRequired = ref(false)
const canUseGoldenMode = computed(
  () => authStore.user?.role === 'admin' || authStore.user?.role === 'reviewer',
)
const isControlledLungProject = computed(() =>
  ['lung_329_pdl1', 'lung_588_pdl1'].includes(projectType.value || ''),
)
const disabledProjectTypes = new Set(
  String(import.meta.env.VITE_DISABLED_PROJECT_TYPES || '')
    .split(/[,;\s]+/)
    .map((value) => value.trim().toLowerCase())
    .filter(Boolean),
)
const generationProjectOptions = [
  { label: '结直肠癌301基因+MSI', value: 'crc_301_msi' },
  { label: '结直肠癌358基因+MSI', value: 'crc_358_msi' },
  { label: '肺癌329基因+PD-L1（单份受控试运行）', value: 'lung_329_pdl1' },
  { label: '肺癌588基因+PD-L1（单份验证）', value: 'lung_588_pdl1' },
  { label: 'MLF基因检测', value: 'mlf_result' },
  { label: '肺癌甲基化', value: 'lung_methylation' },
].filter((option) => !disabledProjectTypes.has(option.value))
const batchGenerationProjectOptions = generationProjectOptions.filter(
  (option) => !['lung_329_pdl1', 'lung_588_pdl1'].includes(option.value),
)
let batchPollTimer: number | null = null
let singlePollTimer: number | null = null

function panelTemplateOptions(type?: string | null) {
  if (type === 'crc_358_msi') {
    return [
      {
        label: '结直肠癌358+MSI Golden 模板（内测）',
        value: 'crc_358_msi_golden_template_v0',
      },
      {
        label: '结直肠癌358+MSI Legacy 模板',
        value: 'crc_358_msi_standard_v1',
      },
    ]
  }
  return []
}

const templateOptions = computed(() => panelTemplateOptions(projectType.value))
const batchTemplateOptions = computed(() => panelTemplateOptions(batchProjectType.value))

const selectedTemplateLabel = computed(() => {
  if (!templateName.value) return templateOptions.value.length ? '未选择' : '默认模板'
  return templateOptions.value.find((option) => option.value === templateName.value)?.label || templateName.value
})

const detectionConfidenceLabel = computed(() => {
  const value = excelStore.upload?.detection_confidence
  if (typeof value !== 'number') return '-'
  return `${Math.round(value * 100)}%`
})

const enrichmentMessage = computed(() => {
  const enrichment = excelStore.patientEnrichment
  const sampleId = excelStore.singleValues?.sample_id
  if (!sampleId) return ''
  if (enrichment?.found) {
    const source = enrichment.source || '患者信息源'
    const keys = Object.keys(enrichment.fields || {})
    return `已根据样本号 ${sampleId} 从 ${source} 补全 ${keys.length} 个临床字段`
  }
  if (excelStore.upload && !form.formData.patient_name) {
    return `Excel 未提供患者姓名，且未在患者信息库/运营系统中查到样本号 ${sampleId}。请手动填写或接入运营系统。`
  }
  return ''
})

const uploadStatusMessage = computed(() => {
  if (excelStore.loading && selectedFileName.value) {
    return `正在解析 ${selectedFileName.value}，请不要重复点击上传`
  }
  if (uploadError.value) {
    return uploadError.value
  }
  if (excelStore.upload?.original_filename) {
    return `已完成上传解析：${excelStore.upload.original_filename}`
  }
  return ''
})

const uploadStatusType = computed(() => {
  if (uploadError.value) return 'error'
  if (excelStore.upload) return 'success'
  return 'info'
})

const batchProgressPercent = computed(() => {
  const task = batchTask.value
  if (!task?.total_files) return 0
  const done = (task.completed_files || 0) + (task.failed_files || 0) + (task.cancelled_files || 0)
  return Math.min(100, Math.round((done / task.total_files) * 100))
})

const isBatchTerminal = computed(() => {
  const status = batchTask.value?.status
  return Boolean(status && ['completed', 'failed', 'partial_failed', 'cancelled'].includes(status))
})

const canRetryBatch = computed(() => {
  const task = batchTask.value
  return Boolean(task?.id && isBatchTerminal.value && (task.failed_files || 0) > 0)
})

const singleProgressPercent = computed(() => {
  const status = singleTask.value?.status
  if (status === 'completed') return 100
  if (status === 'failed' || status === 'cancelled') return 100
  if (status === 'running') return 55
  if (status === 'pending') return 12
  return 0
})

const requiredClinicalFields = computed(() => {
  const schema = form.schema.value
  if (!schema) return []
  return schema.groups.flatMap((group) => group.fields.filter((field) => field.required))
})

const missingRequiredClinicalFields = computed(() => {
  const uncertainRequiredValues: Record<string, string[]> = {
    lung_histology: ['未明确'],
    disease_extent: ['未明确'],
    prior_systemic_therapy: ['未明确'],
    companion_diagnostic_status: ['待确认'],
  }
  return requiredClinicalFields.value.filter((field) => {
    const value = form.formData[field.key]
    return value === null
      || value === undefined
      || value === ''
      || (uncertainRequiredValues[field.key] || []).includes(String(value))
  })
})

const productionCheckSubtitle = computed(() => {
  const project = excelStore.upload?.detected_project_name || excelStore.upload?.detected_project_type || '项目未识别'
  const patient = form.formData.patient_name || excelStore.singleValues?.patient_name || '患者未填写'
  return `${project} · ${patient}`
})

const productionCheckCards = computed(() => {
  const variants = excelStore.previewSummary?.variants || {}
  const drugs = excelStore.previewSummary?.drugs || {}
  const biomarkers = excelStore.previewSummary?.biomarkers || {}
  const msi = biomarkers.msi || {}
  const tmb = biomarkers.tmb || {}
  return [
    {
      label: '患者信息',
      value: stringifyValue(form.formData.patient_name || excelStore.singleValues?.patient_name),
      detail: [
        stringifyValue(form.formData.sample_id || excelStore.singleValues?.sample_id),
        stringifyValue(form.formData.age || excelStore.singleValues?.age),
      ].filter((item) => item !== '-').join(' / ') || '样本号、年龄待核对',
    },
    {
      label: '项目与模板',
      value: stringifyValue(excelStore.upload?.detected_project_name || projectType.value),
      detail: selectedTemplateLabel.value,
    },
    {
      label: '关键结果',
      value: `${stringifyValue(variants.total)} 个变异`,
      detail: `MSI ${stringifyValue(msi.status)} · TMB ${stringifyValue(tmb.status || tmb.value)}`,
    },
    {
      label: '用药提示',
      value: drugs.targeted_status && drugs.targeted_status !== '已启用'
        ? stringifyValue(drugs.targeted_status)
        : `${stringifyValue(drugs.targeted_count)} 条靶向`,
      detail: drugs.targeted_status && String(drugs.targeted_status).includes('精确用药候选')
        ? stringifyValue(drugs.targeted_status)
        : drugs.chemotherapy_status && drugs.chemotherapy_status !== '已启用'
        ? `化疗：${stringifyValue(drugs.chemotherapy_status)}`
        : `${stringifyValue(drugs.chemotherapy_count)} 条化疗；${stringifyValue(variants.drug_related)} 个药物相关变异`,
    },
    {
      label: '临床字段',
      value: missingRequiredClinicalFields.value.length ? `缺 ${missingRequiredClinicalFields.value.length} 项` : '已补齐',
      detail: missingRequiredClinicalFields.value.slice(0, 3).map((field) => field.label).join('、') || '必填字段已就绪',
    },
  ]
})

const deliveryRiskItems = computed(() => {
  const risks: Array<{ key: string; level: string; type: 'danger' | 'warning' | 'info'; message: string }> = []
  const upload = excelStore.upload
  const panel = excelStore.previewSummary?.panel || {}
  const qa = excelStore.previewSummary?.qa || {}
  const confidence = upload?.detection_confidence
  if (!upload?.detected_project_type) {
    risks.push({
      key: 'project_missing',
      level: '阻断',
      type: 'danger',
      message: '检测项目未识别，请先手动确认项目类型和模板。',
    })
  } else if (typeof confidence === 'number' && confidence < 0.8) {
    risks.push({
      key: 'project_low_confidence',
      level: '警告',
      type: 'warning',
      message: `项目识别置信度 ${Math.round(confidence * 100)}%，建议人工确认。`,
    })
  }
  if (panel.status && panel.status !== 'active') {
    risks.push({
      key: 'panel_status',
      level: '警告',
      type: 'warning',
      message: `Panel 状态为 ${panel.status}，生成结果需人工复核。`,
    })
  }
  if (panel.template_status && panel.template_status !== 'active') {
    risks.push({
      key: 'template_status',
      level: '警告',
      type: 'warning',
      message: `模板状态为 ${panel.template_status}，不可跳过 Word 复核。`,
    })
  }
  if (missingRequiredClinicalFields.value.length) {
    risks.push({
      key: 'clinical_missing',
      level: '阻断',
      type: 'danger',
      message: `临床信息缺少：${missingRequiredClinicalFields.value.map((field) => field.label).join('、')}`,
    })
  }
  for (const warning of upload?.validation_warnings || []) {
    if (warning.level === 'error') {
      risks.push({
        key: `validation_${warning.field}_${warning.message}`,
        level: '阻断',
        type: 'danger',
        message: warning.message,
      })
    }
  }
  if (qa.status && qa.status !== 'PASS') {
    risks.push({
      key: 'preview_qa',
      level: qa.status === 'FAIL' ? '阻断' : '警告',
      type: qa.status === 'FAIL' ? 'danger' : 'warning',
      message: `预览 QA 状态为 ${qa.status}，需查看报告质控详情。`,
    })
  }
  for (const [index, item] of previewManualReviewItems.value.entries()) {
    risks.push({
      key: `manual_${index}`,
      level: '复核',
      type: 'warning',
      message: item,
    })
  }
  return risks
})

const productionReadiness = computed(() => {
  if (!excelStore.upload) return { label: '待上传', type: 'info' as const }
  if (deliveryRiskItems.value.some((item) => item.type === 'danger')) {
    return { label: '需补齐后生成', type: 'danger' as const }
  }
  if (deliveryRiskItems.value.length) {
    return { label: '可生成，需复核', type: 'warning' as const }
  }
  return { label: '可进入生成', type: 'success' as const }
})

const previewMetricCards = computed(() => {
  const summary = excelStore.previewSummary
  const variants = summary?.variants || {}
  const drugs = summary?.drugs || {}
  return [
    { label: '检出变异', value: stringifyValue(variants.total) },
    {
      label: '药物相关',
      value: drugs.targeted_status && String(drugs.targeted_status).includes('精确用药候选')
        ? stringifyValue(drugs.targeted_status)
        : stringifyValue(variants.drug_related),
    },
    { label: '小结变异', value: stringifyValue(variants.summary_count) },
    {
      label: '靶向提示',
      value: drugs.targeted_status && drugs.targeted_status !== '已启用'
        ? stringifyValue(drugs.targeted_status)
        : stringifyValue(drugs.targeted_count),
    },
    {
      label: '化疗提示',
      value: drugs.chemotherapy_status && drugs.chemotherapy_status !== '已启用'
        ? stringifyValue(drugs.chemotherapy_status)
        : stringifyValue(drugs.chemotherapy_count),
    },
  ]
})

const previewBiomarkerCards = computed(() => {
  const biomarkers = excelStore.previewSummary?.biomarkers || {}
  const tmb = biomarkers.tmb || {}
  const msi = biomarkers.msi || {}
  const immune = biomarkers.immune || {}
  const immuneUnavailable = immune.status && immune.status !== '已启用'
  return [
    {
      label: 'TMB',
      value: stringifyValue(tmb.status || tmb.value),
      detail: stringifyValue(tmb.summary),
    },
    {
      label: 'MSI',
      value: stringifyValue(msi.status),
      detail: stringifyValue(msi.summary),
    },
    {
      label: '免疫正相关',
      value: stringifyValue(immuneUnavailable ? immune.status : immune.positive),
      detail: '正相关基因检测结果',
    },
    {
      label: '免疫负相关',
      value: stringifyValue(immuneUnavailable ? immune.status : immune.negative),
      detail: '负相关基因检测结果',
    },
    {
      label: '超进展相关',
      value: stringifyValue(immuneUnavailable ? immune.status : immune.hyperprogression),
      detail: '超进展相关基因检测结果',
    },
  ]
})

const previewVariantRows = computed(() => {
  const rows = excelStore.previewSummary?.variants?.key_rows
    || excelStore.previewSummary?.variants?.summary_rows
    || []
  return rows.map((row) => normalizeSummaryRow(row))
})

const previewDrugRows = computed(() => {
  const rows = excelStore.previewSummary?.drugs?.targeted_rows || []
  return rows.map((row) => normalizeSummaryRow(row))
})

const previewManualReviewItems = computed(() => excelStore.previewSummary?.manual_review || [])

const previewVariantTotalText = computed(() => {
  const total = excelStore.previewSummary?.variants?.total
  if (!total || previewVariantRows.value.length >= total) return ''
  return `显示 ${previewVariantRows.value.length}/${total}`
})

const previewDrugTotalText = computed(() => {
  const total = excelStore.previewSummary?.drugs?.targeted_count
  if (!total || previewDrugRows.value.length >= total) return ''
  return `显示 ${previewDrugRows.value.length}/${total}`
})

function stringifyValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'string') return value || '-'
  return JSON.stringify(value)
}

function normalizeSummaryRow(row: Record<string, any>) {
  return {
    gene: stringifyValue(row.gene),
    variant_site: stringifyValue(row.variant_site),
    classification: stringifyValue(row.classification),
    frequency: stringifyValue(row.frequency),
    benefit_drugs: stringifyValue(row.benefit_drugs),
    caution_drugs: stringifyValue(row.caution_drugs),
  }
}

// Initialize projectType from detection
watch(
  () => excelStore.upload?.detected_project_type,
  (type) => {
    if (type && !disabledProjectTypes.has(type.toLowerCase())) {
      projectType.value = type
    } else if (type) {
      projectType.value = null
      ElMessage.warning('当前生产版本暂未开放该项目类型，请完成病例级 UAT 后再使用。')
    } else {
      projectType.value = null
    }
  },
)

watch(
  templateOptions,
  (options) => {
    if (!options.length) {
      templateName.value = null
      return
    }
    const current = templateName.value
    if (!current || !options.some((option) => option.value === current)) {
      templateName.value = options[0].value
    }
  },
  { immediate: true },
)

watch(
  batchTemplateOptions,
  (options) => {
    if (!options.length) {
      batchTemplateName.value = null
      return
    }
    const current = batchTemplateName.value
    if (!current || !options.some((option) => option.value === current)) {
      batchTemplateName.value = options[0].value
    }
  },
  { immediate: true },
)

watch(
  [batchProjectType, batchTemplateName, batchReferenceGateRequired],
  () => {
    batchIdempotencyKey.value = null
  },
)

// Dynamic form driven by project type
const form = useDynamicForm(projectType)
const canGenerate = computed(
  () => Boolean(
    excelStore.upload
    && excelStore.sourceFile
    && projectType.value
    && form.ready.value
    && !generating.value,
  ),
)

// Auto-merge Excel values when upload completes
watch(
  () => excelStore.singleValues,
  (vals) => {
    if (vals && Object.keys(vals).length > 0) {
      form.mergeExcelValues(vals)
    }
  },
)

watch(
  () => excelStore.patientEnrichment,
  (enrichment) => {
    if (enrichment?.found) {
      form.mergePatientInfo(enrichment.fields)
    }
  },
)

onUnmounted(() => {
  stopBatchPolling()
  stopSinglePolling()
})

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  projectType.value = null
  templateName.value = null
  form.reset()
  excelStore.reset()
  result.value = null
  singleTask.value = null
  stopSinglePolling()
  uploadError.value = ''
  selectedFileName.value = file.name || ''
  try {
    const applied = await excelStore.uploadFile(file)
    if (!applied) return
    ElMessage.success('Excel 上传成功')
  } catch (err: any) {
    uploadError.value = err.response?.data?.detail || err.message || 'Excel 上传失败'
    ElMessage.error(uploadError.value)
  }
}

function handleBatchFileChange(_uploadFile: any, uploadFiles: any[]) {
  batchFileList.value = uploadFiles
  batchFiles.value = uploadFiles
    .map((item) => item.raw)
    .filter((file): file is File => Boolean(file))
  batchTask.value = null
  batchResultRows.value = []
  batchIdempotencyKey.value = null
  stopBatchPolling()
}

function handleBatchFileRemove(_uploadFile: any, uploadFiles: any[]) {
  handleBatchFileChange(null, uploadFiles)
}

async function startBatchGenerate() {
  if (!batchFiles.value.length) {
    ElMessage.warning('请先选择 Excel 文件')
    return
  }
  const bad = batchFiles.value.find(
    (file) => file.name.startsWith('._') || file.name.startsWith('~$') || !file.name.endsWith('.xlsx'),
  )
  if (bad) {
    ElMessage.warning(`请移除临时或非 xlsx 文件：${bad.name}`)
    return
  }

  batchGenerating.value = true
  batchTask.value = null
  batchResultRows.value = []
  stopBatchPolling()
  try {
    batchIdempotencyKey.value ||= createIdempotencyKey()
    const accepted = await reportApi.generateBatchFromFiles(
      batchFiles.value,
      {
        clinical_info: {},
        project_type: batchProjectType.value,
        project_name: null,
        template_name: batchTemplateName.value,
        template_contract_mode: 'warn',
        reference_gate_mode: batchReferenceGateRequired.value ? 'required' : 'available',
      },
      batchIdempotencyKey.value,
    )
    ElMessage.info(
      accepted.idempotent_replay
        ? '已识别为重试，继续查看原批量任务'
        : '批量任务已进入后台生成',
    )
    batchTask.value = {
      id: accepted.task_id,
      task_type: 'batch',
      status: accepted.status,
      project_type: batchProjectType.value,
      total_files: accepted.total_files,
      completed_files: 0,
      failed_files: 0,
      cancelled_files: 0,
      pending_files: accepted.total_files,
      running_files: 0,
      status_counts: { queued: accepted.total_files },
      output_path: null,
      created_at: null,
      started_at: null,
      completed_at: null,
      duration_seconds: null,
      errors: [],
      warnings: [],
    }
    startBatchPolling(accepted.task_id)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || err.message || '批量任务提交失败')
    batchGenerating.value = false
  }
}

function startBatchPolling(taskId: string) {
  const poll = async () => {
    try {
      batchTask.value = await reportApi.getTaskStatus(taskId)
      try {
        const detail = await reportApi.getBatchResults(taskId)
        batchResultRows.value = detail.items
      } catch {
        batchResultRows.value = []
      }
      if (
        batchTask.value.status === 'completed'
        || batchTask.value.status === 'failed'
        || batchTask.value.status === 'partial_failed'
        || batchTask.value.status === 'cancelled'
      ) {
        batchGenerating.value = false
        stopBatchPolling()
        if (batchTask.value.status === 'completed') {
          ElMessage.success('批量生成完成')
        } else if (batchTask.value.status === 'partial_failed') {
          ElMessage.warning('批量生成完成，但有文件失败')
        } else if (batchTask.value.status === 'failed') {
          ElMessage.error('批量生成失败')
        }
      }
    } catch (err: any) {
      batchGenerating.value = false
      stopBatchPolling()
      ElMessage.error(err.response?.data?.detail || '批量进度读取失败')
    }
  }
  poll()
  batchPollTimer = window.setInterval(poll, 2000)
}

function stopBatchPolling() {
  if (batchPollTimer !== null) {
    window.clearInterval(batchPollTimer)
    batchPollTimer = null
  }
}

function formatDownloadProgress(progress: DownloadProgress) {
  const percent = progress.percent == null ? '计算中' : `${progress.percent}%`
  const received = `${(progress.receivedBytes / 1024 / 1024).toFixed(1)} MB`
  const total = progress.expectedBytes
    ? `${(progress.expectedBytes / 1024 / 1024).toFixed(1)} MB`
    : '-'
  const resume = progress.attempt > 1 ? `，第 ${progress.attempt} 次续传` : ''
  return `${percent} · ${received}/${total}${resume}`
}

async function downloadBatchZip() {
  if (!batchTask.value?.id) return
  batchDownloading.value = true
  batchDownloadStatus.value = '正在准备 ZIP 下载'
  try {
    const result = await reportApi.downloadBatchZip(batchTask.value.id, false, {
      onProgress: (progress) => {
        batchDownloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        batchDownloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    if (result.attempts > 1) {
      ElMessage.success(`ZIP 下载成功，已重试 ${result.attempts - 1} 次`)
    } else {
      ElMessage.success('ZIP 下载完成')
    }
  } catch (err: any) {
    ElMessage.error(err.message || 'ZIP 下载失败')
  } finally {
    batchDownloading.value = false
    window.setTimeout(() => { batchDownloadStatus.value = '' }, 3000)
  }
}

async function cancelCurrentBatch() {
  if (!batchTask.value?.id) return
  batchCancelling.value = true
  try {
    await reportApi.cancelTask(batchTask.value.id)
    ElMessage.success('批量任务已取消')
    batchTask.value = await reportApi.getTaskStatus(batchTask.value.id)
    try {
      const detail = await reportApi.getBatchResults(batchTask.value.id)
      batchResultRows.value = detail.items
    } catch {
      batchResultRows.value = []
    }
    batchGenerating.value = false
    stopBatchPolling()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '取消失败')
  } finally {
    batchCancelling.value = false
  }
}

async function retryFailedBatch() {
  if (!batchTask.value?.id) return
  batchRetrying.value = true
  try {
    const accepted = await reportApi.retryBatchFailed(batchTask.value.id)
    ElMessage.info(`已重试 ${accepted.retry_files || 0} 个失败文件`)
    batchGenerating.value = true
    batchTask.value = await reportApi.getTaskStatus(batchTask.value.id)
    startBatchPolling(batchTask.value.id)
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '重试失败')
  } finally {
    batchRetrying.value = false
  }
}

async function handleGenerate() {
  if (!excelStore.upload) return
  if (!form.ready.value) {
    ElMessage.warning('请先选择项目类型，并等待临床信息表单加载完成')
    return
  }
  if (!form.validate()) {
    ElMessage.warning('请填写必填字段')
    return
  }

  generating.value = true
  result.value = null
  singleTask.value = null
  stopSinglePolling()
  try {
    const payload: Omit<GenerateRequest, 'upload_id'> = {
      clinical_info: form.getCleanValues(),
      project_type: projectType.value,
      project_name: projectDisplayName(projectType.value),
      template_name: templateName.value,
      reference_gate_mode: singleReferenceGateRequired.value ? 'required' : 'available',
    }
    if (excelStore.sourceFile && generationMode === 'async') {
      const accepted = await reportApi.generateFromFileAsync(excelStore.sourceFile, payload)
      ElMessage.info('报告已进入后台队列，可在任务详情中查看进度')
      singleTask.value = {
        id: accepted.task_id,
        task_type: 'single',
        status: 'pending',
        project_type: projectType.value,
        total_files: 1,
        completed_files: 0,
        failed_files: 0,
        cancelled_files: 0,
        pending_files: 1,
        running_files: 0,
        status_counts: {},
        output_path: null,
        created_at: null,
        started_at: null,
        completed_at: null,
        duration_seconds: null,
        errors: [],
        warnings: accepted.warnings || [],
      }
      generating.value = false
      startSinglePolling(accepted.task_id)
      return
    } else {
      result.value = excelStore.sourceFile
        ? await reportApi.generateFromFile(excelStore.sourceFile, payload)
        : await reportApi.generate({
            upload_id: excelStore.upload.upload_id,
            ...payload,
          })
    }
    if (result.value.success) {
      ElMessage.success('报告生成成功')
    } else {
      ElMessage.error('报告生成失败')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || err.response?.data?.detail || err.message || '报告生成异常')
  } finally {
    generating.value = false
  }
}

function taskStatusToResult(task: Awaited<ReturnType<typeof reportApi.getTaskStatus>>): GenerateResult {
  return {
    task_id: task.id,
    success: task.status === 'completed',
    output_file: task.output_path,
    field_provenance_file: task.field_provenance_file,
    qa_report_file: task.qa_report_file,
    report_summary_file: task.report_summary_file,
    qa_status: task.qa_status,
    generation_id: task.generation_id,
    stage_results: task.stage_results,
    stage_results_file: task.stage_results_file,
    diff_status: task.diff_status,
    diff_gate_passed: task.diff_gate_passed,
    diff_reference_id: task.diff_reference_id,
    diff_reference_name: task.diff_reference_name,
    diff_auto_ran: Boolean(task.diff_status),
    duration_seconds: task.duration_seconds,
    errors: task.errors,
    warnings: task.warnings,
  }
}

function startSinglePolling(taskId: string) {
  const poll = async () => {
    try {
      const task = await reportApi.getTaskStatus(taskId)
      singleTask.value = task
      if (['completed', 'failed', 'cancelled'].includes(task.status)) {
        stopSinglePolling()
        result.value = taskStatusToResult(task)
        if (task.status === 'completed') {
          ElMessage.success('报告生成成功')
        } else if (task.status === 'cancelled') {
          ElMessage.info('报告生成已取消')
        } else {
          ElMessage.error('报告生成失败')
        }
      }
    } catch (err: any) {
      stopSinglePolling()
      ElMessage.error(err.response?.data?.detail || '任务进度读取失败')
    }
  }
  poll()
  singlePollTimer = window.setInterval(poll, 2000)
}

function stopSinglePolling() {
  if (singlePollTimer !== null) {
    window.clearInterval(singlePollTimer)
    singlePollTimer = null
  }
}

async function cancelCurrentSingle() {
  if (!singleTask.value?.id) return
  singleCancelling.value = true
  try {
    await reportApi.cancelTask(singleTask.value.id)
    singleTask.value = await reportApi.getTaskStatus(singleTask.value.id)
    result.value = taskStatusToResult(singleTask.value)
    generating.value = false
    stopSinglePolling()
    ElMessage.success('报告生成任务已取消')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '取消失败')
  } finally {
    singleCancelling.value = false
  }
}

function shortTaskId(value: string) {
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function createIdempotencyKey() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `batch-${Date.now()}-${Math.random().toString(36).slice(2, 14)}`
}

function isActiveTaskStatus(status?: string | null) {
  return Boolean(
    status
    && ['queued', 'preflight', 'generating', 'qa', 'pending', 'running'].includes(status),
  )
}

async function downloadReport(taskId: string) {
  singleDownloading.value = true
  singleDownloadStatus.value = '正在准备报告下载'
  try {
    const task = await reportApi.getTaskStatus(taskId)
    if (task.status !== 'completed') {
      ElMessage.warning('报告仍在生成中，请稍后再下载')
      return
    }
    if (!task.output_path) {
      ElMessage.error('报告文件不存在，请重新生成后下载')
      return
    }
    await reportApi.download(taskId, {
      onProgress: (progress) => {
        singleDownloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        singleDownloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    ElMessage.success('报告下载完成')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || err.message || '报告下载失败')
  } finally {
    singleDownloading.value = false
    window.setTimeout(() => { singleDownloadStatus.value = '' }, 3000)
  }
}

async function downloadGenerated(generated: GenerateResult) {
  // 优先走 /download 流式接口（快、不占内存、不经 base64 膨胀）；
  // 只有缺 task_id 时才 fallback 到 base64 内联。
  try {
    if (generated.task_id) {
      await downloadReport(generated.task_id)
      return
    }
    if (generated.output_file_base64) {
      reportApi.downloadInline(generated)
      return
    }
    throw new Error('报告没有可下载的内容')
  } catch (err: any) {
    ElMessage.error(err.message || '下载失败')
  }
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    completed: 'success',
    partial_failed: 'danger',
    failed: 'danger',
    queued: 'info',
    preflight: 'warning',
    generating: 'warning',
    qa: 'warning',
    running: 'warning',
    pending: 'info',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    partial_failed: '部分失败',
    failed: '失败',
    queued: '已排队',
    preflight: '预检中',
    generating: '生成中',
    qa: '质控中',
    running: '运行中',
    pending: '待执行',
    cancelled: '已取消',
  }
  return map[status] || status
}
</script>

<style scoped>
.batch-head,
.batch-progress-title,
.batch-actions,
.single-progress-title,
.single-actions {
  display: flex;
  align-items: center;
}

.batch-head {
  justify-content: space-between;
}

.batch-controls {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) 320px;
  gap: 16px;
}

.batch-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.batch-progress {
  margin-top: 14px;
  border: 1px solid #d9e2ec;
  padding: 14px;
}

.single-progress {
  margin-top: 16px;
  padding: 14px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
}

.single-progress-title {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.single-progress-title span {
  color: #667085;
  font-size: 13px;
}

.single-actions {
  gap: 8px;
  margin-top: 12px;
}

.batch-progress-title {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.batch-progress-title span {
  color: #667085;
  font-size: 13px;
}

.batch-actions {
  gap: 8px;
  margin-top: 12px;
}

.download-status {
  margin-top: 8px;
  color: #667085;
  font-size: 13px;
}

.batch-table {
  margin-top: 12px;
}

.upload-preview {
  margin-top: 14px;
  border: 1px solid #d9e2ec;
  background: #fff;
}

.production-check {
  margin-top: 14px;
  border: 1px solid #cfd9e5;
  background: #fbfcfe;
}

.check-head {
  min-height: 50px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #e6edf3;
}

.check-head div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.check-head strong {
  font-size: 15px;
}

.check-head span {
  color: #667085;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.check-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
}

.check-card {
  min-height: 86px;
  padding: 12px 14px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 7px;
}

.check-card:last-child {
  border-right: 0;
}

.check-card span,
.risk-title span {
  color: #667085;
  font-size: 12px;
}

.check-card strong {
  font-size: 18px;
  line-height: 1.2;
}

.check-card em {
  color: #475467;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.risk-panel {
  border-top: 1px solid #e6edf3;
  background: #fff;
}

.risk-title {
  min-height: 38px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.risk-list {
  padding: 0 14px 12px;
  display: grid;
  gap: 8px;
}

.risk-item {
  min-height: 30px;
  display: grid;
  grid-template-columns: 54px minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: #344054;
  font-size: 13px;
}

.preview-title {
  min-height: 44px;
  padding: 0 14px;
  border-bottom: 1px solid #e6edf3;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.preview-metric {
  min-height: 64px;
  padding: 10px 12px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.preview-metric:last-child {
  border-right: 0;
}

.preview-metric span,
.preview-biomarkers span,
.preview-table-title {
  color: #667085;
  font-size: 12px;
}

.preview-metric strong {
  font-size: 17px;
}

.preview-biomarkers {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.preview-biomarkers div {
  min-height: 88px;
  padding: 12px 14px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.preview-biomarkers div:last-child {
  border-right: 0;
}

.preview-biomarkers strong {
  font-size: 18px;
}

.preview-biomarkers em {
  color: #475467;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.preview-alert {
  margin: 14px 14px 0;
}

.preview-tables {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
  gap: 14px;
  padding: 14px;
}

.preview-table-title {
  margin-bottom: 8px;
  font-weight: 650;
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.preview-table-title span {
  color: #98a2b3;
  font-weight: 500;
}

@media (max-width: 980px) {
  .batch-controls,
  .check-grid,
  .preview-metrics,
  .preview-biomarkers,
  .preview-tables {
    grid-template-columns: 1fr;
  }

  .check-card,
  .preview-metric,
  .preview-biomarkers div {
    border-right: 0;
    border-bottom: 1px solid #e6edf3;
  }

  .check-card:last-child,
  .preview-metric:last-child,
  .preview-biomarkers div:last-child {
    border-bottom: 0;
  }
}
</style>
