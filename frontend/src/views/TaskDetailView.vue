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
          :loading="reportDownloading"
          @click="downloadReport"
        >
          {{ reportDownloading ? '正在下载' : '下载报告' }}
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
          <span>生成流水线</span>
          <el-tag :type="qaTagType(pipelineStatus)">
            {{ pipelineStatus || '未记录' }}
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

      <section class="qa-panel production-gate section-gap">
        <div class="panel-title">
          <span>生产门禁与审核</span>
          <div class="stage-title-meta">
            <el-tag size="small" :type="qualityGate?.passed ? 'success' : 'danger'">
              {{ qualityGate?.status || '未检查' }}
            </el-tag>
            <el-tag size="small" :type="reviewStatusTagType(reviewState?.status)">
              {{ reviewState?.status_label || '待审核' }}
            </el-tag>
          </div>
        </div>
        <div class="gate-content">
          <div class="gate-metrics">
            <div>
              <span>阻断项</span>
              <strong :class="qualityGate?.blockers ? 'bad-text' : 'ok-text'">
                {{ qualityGate?.blockers ?? '-' }}
              </strong>
            </div>
            <div>
              <span>警告项</span>
              <strong :class="qualityGate?.warnings ? 'warn-text' : ''">
                {{ qualityGate?.warnings ?? '-' }}
              </strong>
            </div>
            <div>
              <span>审核人</span>
              <strong>{{ reviewState?.updated_by || '-' }}</strong>
            </div>
            <div>
              <span>更新时间</span>
              <strong>{{ reviewState?.updated_at ? new Date(reviewState.updated_at).toLocaleString('zh-CN') : '-' }}</strong>
            </div>
          </div>
          <div class="gate-actions">
            <el-button :icon="Refresh" @click="refreshGate">刷新门禁</el-button>
            <el-button
              type="success"
              plain
              :loading="reviewUpdating"
              @click="markReviewState('reviewed')"
            >
              标记已审核
            </el-button>
            <el-button
              type="primary"
              :disabled="!qualityGate?.passed"
              :loading="reviewUpdating"
              @click="markReviewState('delivered')"
            >
              标记已交付
            </el-button>
            <el-button
              :icon="Download"
              :loading="auditDownloading"
              @click="downloadAuditPackage(true)"
            >
              {{ auditDownloading ? '正在下载审计包' : '下载审计包' }}
            </el-button>
          </div>
          <el-alert
            v-if="qualityGate && !qualityGate.passed"
            title="质控门禁存在阻断项，建议不要进入交付。"
            type="error"
            show-icon
            :closable="false"
            class="stage-alert"
          />
          <el-table
            v-if="qualityGateIssueRows.length"
            :data="qualityGateIssueRows"
            size="small"
            border
            class="gate-table"
          >
            <el-table-column label="级别" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.level === 'blocker' ? 'danger' : 'warning'">
                  {{ row.level === 'blocker' ? '阻断' : '警告' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="scope" label="范围" width="110" show-overflow-tooltip />
            <el-table-column prop="code" label="代码" width="190" show-overflow-tooltip />
            <el-table-column prop="message" label="说明" min-width="320" show-overflow-tooltip />
          </el-table>
          <el-empty v-else description="暂无门禁问题" :image-size="70" />
        </div>
      </section>

      <section v-if="isBatchTask" class="qa-panel section-gap">
        <div class="panel-title">
          <span>批量生成进度</span>
          <div class="stage-title-meta">
            <el-tag size="small" :type="statusTagType(task?.status || '')">
              {{ statusLabel(task?.status || '-') }}
            </el-tag>
            <el-tag size="small" type="info">
              {{ task?.completed_files || 0 }}/{{ task?.total_files || 0 }}
            </el-tag>
          </div>
        </div>
        <div class="batch-detail-progress">
          <el-progress
            :percentage="batchProgressPercent"
            :status="task?.status === 'failed' || task?.status === 'partial_failed' ? 'exception' : task?.status === 'completed' ? 'success' : undefined"
          />
          <div class="batch-summary-grid">
            <div v-for="item in batchSummaryCards" :key="item.label">
              <span>{{ item.label }}</span>
              <strong :class="item.className">{{ item.value }}</strong>
            </div>
          </div>
          <div class="batch-detail-actions">
            <el-button
              v-if="task?.completed_files"
              type="primary"
              :icon="Download"
              :loading="batchDownloading"
              @click="downloadBatchZip"
            >
              {{ batchDownloading ? '正在下载 ZIP' : '下载成功报告 ZIP' }}
            </el-button>
            <el-button
              v-if="task?.completed_files"
              plain
              :icon="Download"
              :loading="batchPassDownloading"
              @click="downloadBatchPassZip"
            >
              {{ batchPassDownloading ? '正在下载 QA PASS ZIP' : '下载 QA PASS ZIP' }}
            </el-button>
            <el-popconfirm
              v-if="task?.status === 'running' || task?.status === 'pending'"
              title="确认取消当前批量任务？正在生成的文件会完成本轮后停止。"
              @confirm="cancelBatchTask"
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
            <el-button :icon="Refresh" @click="fetchAll">刷新</el-button>
          </div>
          <div v-if="downloadStatus" class="download-status">
            {{ downloadStatus }}
          </div>
        </div>
        <el-table
          v-if="batchResultDetailRows.length"
          :data="batchResultDetailRows"
          size="small"
          border
          class="batch-detail-table"
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
          <el-table-column prop="project_name" label="项目" min-width="170" show-overflow-tooltip />
          <el-table-column label="患者/样本" min-width="180" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.patient_label }}
            </template>
          </el-table-column>
          <el-table-column label="QA" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.qa_status" size="small" :type="qaTagType(row.qa_status)">
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
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button
                v-if="row.download_url"
                text
                type="primary"
                size="small"
                :loading="Boolean(batchItemDownloading[row.index])"
                @click="downloadBatchItem(row.download_url, row.index)"
              >
                {{ batchItemDownloading[row.index] ? '下载中' : '下载' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无逐文件结果" :image-size="70" />
      </section>

      <section v-if="!isBatchTask" class="qa-panel report-summary section-gap">
        <div class="panel-title">
          <span>报告结果概览</span>
          <div class="stage-title-meta">
            <el-tag size="small" :type="qaTagType(reportSummary?.qa?.status || task?.qa_status)">
              {{ reportSummary?.qa?.status || task?.qa_status || '未生成' }}
            </el-tag>
            <el-tag v-if="reportSummary?.project_name" size="small" type="info">
              {{ reportSummary.project_name }}
            </el-tag>
          </div>
        </div>
        <el-alert
          v-if="summaryLoadError"
          :title="summaryLoadError"
          type="info"
          show-icon
          :closable="false"
          class="stage-alert"
        />
        <template v-else-if="reportSummary">
          <div class="patient-strip">
            <div v-for="item in summaryPatientItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <div class="summary-metrics">
            <div v-for="metric in summaryMetricCards" :key="metric.label" class="metric-box">
              <span>{{ metric.label }}</span>
              <strong :class="metric.className">{{ metric.value }}</strong>
            </div>
          </div>
          <div class="biomarker-grid">
            <div v-for="item in biomarkerCards" :key="item.label" class="biomarker-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <em>{{ item.detail }}</em>
            </div>
          </div>
          <el-alert
            v-if="manualReviewItems.length"
            :title="manualReviewItems.join('；')"
            type="warning"
            show-icon
            :closable="false"
            class="summary-alert"
          />
          <div class="summary-tables">
            <div>
              <div class="table-subtitle">关键变异</div>
              <el-table :data="summaryVariantRows" size="small" border>
                <el-table-column prop="gene" label="基因" width="100" show-overflow-tooltip />
                <el-table-column prop="variant_site" label="变异" min-width="190" show-overflow-tooltip />
                <el-table-column prop="classification" label="等级" width="90" show-overflow-tooltip />
                <el-table-column prop="frequency" label="丰度" width="90" show-overflow-tooltip />
                <el-table-column prop="benefit_drugs" label="获益药物" min-width="150" show-overflow-tooltip />
                <el-table-column prop="caution_drugs" label="耐药/慎用" min-width="150" show-overflow-tooltip />
              </el-table>
            </div>
            <div>
              <div class="table-subtitle">用药提示</div>
              <el-table :data="summaryDrugRows" size="small" border>
                <el-table-column prop="gene" label="基因" width="100" show-overflow-tooltip />
                <el-table-column prop="variant_site" label="变异" min-width="180" show-overflow-tooltip />
                <el-table-column prop="benefit_drugs" label="潜在获益" min-width="160" show-overflow-tooltip />
                <el-table-column prop="caution_drugs" label="耐药/慎用" min-width="160" show-overflow-tooltip />
              </el-table>
            </div>
          </div>
        </template>
        <el-empty v-else description="未找到报告结果摘要" :image-size="70" />
      </section>

      <el-alert
        v-if="qaLoadError && !isBatchTask"
        :title="qaLoadError"
        type="warning"
        show-icon
        :closable="false"
        class="section-gap"
      />

      <section v-if="!isBatchTask" class="qa-grid section-gap">
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
          <span>生成阶段</span>
          <div class="stage-title-meta">
            <el-tag size="small" type="info">{{ task?.generation_id || stageReport?.generation_id || '-' }}</el-tag>
            <el-tag size="small" :type="stageRows.length ? 'success' : 'info'">
              {{ stageRows.length ? `${stageRows.length} 步` : '未记录' }}
            </el-tag>
          </div>
        </div>
        <el-alert
          v-if="stageLoadError"
          :title="stageLoadError"
          type="info"
          show-icon
          :closable="false"
          class="stage-alert"
        />
        <div v-if="stageRows.length" class="stage-summary">
          <div v-for="item in stageStatusCards" :key="item.label" class="stage-summary-item">
            <span>{{ item.label }}</span>
            <strong :class="item.className">{{ item.value }}</strong>
          </div>
        </div>
        <el-table
          v-if="stageRows.length"
          :data="stageRows"
          size="small"
          border
          class="stage-table"
        >
          <el-table-column label="阶段" min-width="190" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="stage-name">
                <strong>{{ row.label }}</strong>
                <span>{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="105">
            <template #default="{ row }">
              <el-tag size="small" :type="qaTagType(row.status)">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="110">
            <template #default="{ row }">
              {{ formatDurationMs(row.duration_ms) }}
            </template>
          </el-table-column>
          <el-table-column label="摘要" min-width="260" show-overflow-tooltip>
            <template #default="{ row }">
              {{ stageSummary(row) }}
            </template>
          </el-table-column>
          <el-table-column label="问题" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">
              {{ stageIssueSummary(row) }}
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="未找到生成阶段记录" :image-size="70" />
        <el-collapse v-if="stageRows.length" class="debug-collapse">
          <el-collapse-item title="生成阶段 JSON" name="stage-json">
            <pre>{{ stageDebugText }}</pre>
          </el-collapse-item>
        </el-collapse>
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
            v-if="!isBatchTask"
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
            v-if="!isBatchTask"
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
          <div v-for="metric in diffMetricCards" :key="metric.label" class="metric-box">
            <span>{{ metric.label }}</span>
            <strong :class="metric.className">{{ metric.value }}</strong>
          </div>
        </div>
        <el-table
          v-if="batchDiffRows.length"
          :data="batchDiffRows"
          size="small"
          border
          class="diff-table"
        >
          <el-table-column prop="index" label="#" width="70" />
          <el-table-column prop="case_id" label="Case" width="140" show-overflow-tooltip />
          <el-table-column prop="panel_id" label="Panel" width="140" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.gate_passed === false ? 'danger' : qaTagType(row.status)">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reference_name" label="基准" min-width="150" show-overflow-tooltip />
          <el-table-column prop="message" label="说明" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">
              {{ stringifyValue(row.message) }}
            </template>
          </el-table-column>
          <el-table-column label="产物" width="130">
            <template #default="{ row }">
              <el-button
                v-if="row.diff_key"
                text
                type="primary"
                size="small"
                @click="downloadBatchItemDiff(row.diff_key, 'report_diff.md')"
              >
                摘要
              </el-button>
              <el-button
                v-if="row.diff_key"
                text
                type="primary"
                size="small"
                @click="downloadBatchItemDiff(row.diff_key, 'report_diff.json')"
              >
                JSON
              </el-button>
            </template>
          </el-table-column>
        </el-table>
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
  type BatchResults,
  type DownloadProgress,
  type QualityGate,
  type ReportDiffResult,
  type ReportSummary,
  type ReviewState,
  type TaskStatus,
  type VisualRenderResult,
} from '@/api/report'

const route = useRoute()
const taskId = String(route.params.id || '')

const loading = ref(false)
const rendering = ref(false)
const diffing = ref(false)
const autoDiffing = ref(false)
const batchRetrying = ref(false)
const batchCancelling = ref(false)
const reviewUpdating = ref(false)
const reportDownloading = ref(false)
const auditDownloading = ref(false)
const batchDownloading = ref(false)
const batchPassDownloading = ref(false)
const batchItemDownloading = ref<Record<number, boolean>>({})
const downloadStatus = ref('')
const task = ref<TaskStatus | null>(null)
const qaReport = ref<Record<string, any> | null>(null)
const reportSummary = ref<ReportSummary | null>(null)
const qualityGate = ref<QualityGate | null>(null)
const reviewState = ref<ReviewState | null>(null)
const provenance = ref<Record<string, any> | null>(null)
const stageReport = ref<Record<string, any> | null>(null)
const batchResults = ref<BatchResults | null>(null)
const visualRender = ref<VisualRenderResult | null>(null)
const reportDiff = ref<ReportDiffResult | null>(null)
const referenceFile = ref<File | null>(null)
const referenceFileList = ref<any[]>([])
const diffFailOn = ref<'fail' | 'warn'>('fail')
const qaLoadError = ref('')
const summaryLoadError = ref('')
const provenanceLoadError = ref('')
const stageLoadError = ref('')

const issueRows = computed(() => qaReport.value?.issues || [])
const processorRows = computed(() => qaReport.value?.post_processors || [])
const stageRows = computed(() => {
  const rows = stageReport.value?.stage_results || task.value?.stage_results || []
  return rows.map((row: Record<string, any>) => ({
    ...row,
    label: stageLabel(row.name),
  }))
})

const pipelineStatus = computed(() => {
  if (stageReport.value?.pipeline?.status) return stageReport.value.pipeline.status
  const failed = stageRows.value.some((row: Record<string, any>) => row.status === 'FAIL')
  const warned = stageRows.value.some((row: Record<string, any>) => row.status === 'WARN')
  if (failed) return 'FAIL'
  if (warned) return 'WARN'
  return stageRows.value.length ? 'PASS' : ''
})

const stageStatusCards = computed(() => {
  const counts = stageRows.value.reduce(
    (acc: Record<string, number>, row: Record<string, any>) => {
      const key = String(row.status || 'UNKNOWN')
      acc[key] = (acc[key] || 0) + 1
      return acc
    },
    {},
  )
  return [
    { label: 'PASS', value: String(counts.PASS || 0), className: 'ok-text' },
    { label: 'WARN', value: String(counts.WARN || 0), className: counts.WARN ? 'warn-text' : '' },
    { label: 'FAIL', value: String(counts.FAIL || 0), className: counts.FAIL ? 'bad-text' : '' },
    { label: 'SKIPPED', value: String(counts.SKIPPED || 0) },
  ]
})

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
const qualityGateIssueRows = computed(() => qualityGate.value?.issues || [])
const batchDiffRows = computed(() => reportDiff.value?.items || [])
const isBatchTask = computed(() => task.value?.task_type === 'batch')
const isBatchDiff = computed(() => Boolean(reportDiff.value?.items?.length))
const batchProgressPercent = computed(() => {
  if (!task.value?.total_files) return 0
  const done = (
    (task.value.completed_files || 0)
    + (task.value.failed_files || 0)
    + (task.value.cancelled_files || 0)
  )
  return Math.min(100, Math.round((done / task.value.total_files) * 100))
})
const canRetryBatch = computed(() => {
  const status = task.value?.status
  return Boolean(
    task.value?.task_type === 'batch'
    && status
    && ['completed', 'failed', 'partial_failed', 'cancelled'].includes(status)
    && (task.value.failed_files || 0) > 0,
  )
})
const batchSummaryCards = computed(() => {
  const t = task.value
  const counts = batchResults.value?.status_counts || t?.status_counts || {}
  return [
    { label: '总文件', value: String(t?.total_files || 0) },
    { label: '运行中', value: String(counts.running || t?.running_files || 0) },
    { label: '已完成', value: String(t?.completed_files || 0), className: 'ok-text' },
    { label: '失败', value: String(t?.failed_files || 0), className: t?.failed_files ? 'bad-text' : '' },
    { label: '已取消', value: String(counts.cancelled || t?.cancelled_files || 0) },
  ]
})
const batchResultDetailRows = computed(() => {
  return (batchResults.value?.items || []).map((row) => {
    const clinical = row.clinical_info || {}
    return {
      ...row,
      patient_label: [
        clinical.patient_name,
        clinical.sample_id,
      ].filter(Boolean).join(' / ') || '-',
    }
  })
})
const summaryPatientItems = computed(() => {
  const patient = reportSummary.value?.patient || {}
  return [
    { label: '姓名', value: stringifyValue(patient.patient_name) },
    { label: '报告编号', value: stringifyValue(patient.report_number || patient.sample_id) },
    { label: '诊断', value: stringifyValue(patient.clinical_diagnosis) },
    { label: '样本类型', value: stringifyValue(patient.sample_type) },
    { label: '报告日期', value: stringifyValue(patient.report_date) },
  ]
})
const summaryMetricCards = computed(() => {
  const variants = reportSummary.value?.variants || {}
  const drugs = reportSummary.value?.drugs || {}
  const qa = reportSummary.value?.qa || {}
  const qaStatus = qa.status || task.value?.qa_status || '未生成'
  return [
    { label: '检出变异', value: stringifyValue(variants.total) },
    { label: '药物相关', value: stringifyValue(variants.drug_related) },
    { label: '小结变异', value: stringifyValue(variants.summary_count) },
    { label: '靶向提示', value: stringifyValue(drugs.targeted_count) },
    { label: 'QA', value: qaStatus, className: qaStatus === 'FAIL' ? 'bad-text' : qaStatus === 'WARN' ? 'warn-text' : 'ok-text' },
  ]
})
const biomarkerCards = computed(() => {
  const biomarkers = reportSummary.value?.biomarkers || {}
  const tmb = biomarkers.tmb || {}
  const msi = biomarkers.msi || {}
  const immune = biomarkers.immune || {}
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
      value: stringifyValue(immune.positive),
      detail: '正相关基因检测结果',
    },
    {
      label: '免疫负相关',
      value: stringifyValue(immune.negative),
      detail: '负相关基因检测结果',
    },
    {
      label: '超进展相关',
      value: stringifyValue(immune.hyperprogression),
      detail: '超进展相关基因检测结果',
    },
  ]
})
const summaryVariantRows = computed(() => {
  const rows = reportSummary.value?.variants?.key_rows
    || reportSummary.value?.variants?.summary_rows
    || []
  return rows.map((row) => normalizeSummaryRow(row))
})
const summaryDrugRows = computed(() => {
  const rows = reportSummary.value?.drugs?.targeted_rows || []
  return rows.map((row) => normalizeSummaryRow(row))
})
const manualReviewItems = computed(() => reportSummary.value?.manual_review || [])

const diffGateTagType = computed(() => {
  if (task.value?.diff_gate_passed === false || reportDiff.value?.gate?.passed === false) return 'danger'
  return qaTagType(reportDiff.value?.status || task.value?.diff_status)
})

const diffSummaryTitle = computed(() => {
  if (!reportDiff.value) return ''
  const gate = reportDiff.value.gate?.passed ? '门禁通过' : '门禁阻断'
  if (isBatchDiff.value) {
    const s = reportDiff.value.summary || {}
    return `${gate}：${reportDiff.value.status}，命中 ${s.matched_references || 0}/${s.total_reports || 0}，阻断 ${s.blocked || 0}`
  }
  const failures = reportDiff.value.summary?.failures || 0
  const warnings = reportDiff.value.summary?.warnings || 0
  return `${gate}：${reportDiff.value.status}，失败 ${failures}，警告 ${warnings}`
})

const diffMetricCards = computed(() => {
  if (!reportDiff.value) return []
  const s = reportDiff.value.summary || {}
  const gatePassed = reportDiff.value.gate?.passed
  if (isBatchDiff.value) {
    return [
      { label: '门禁', value: gatePassed ? '通过' : '阻断', className: gatePassed ? 'ok-text' : 'bad-text' },
      { label: '命中基准', value: `${s.matched_references || 0}/${s.total_reports || 0}` },
      { label: 'PASS/WARN/FAIL', value: `${s.pass || 0}/${s.warn || 0}/${s.fail || 0}` },
      { label: '未匹配', value: String(s.skip || 0) },
      { label: '阻断', value: String(s.blocked || 0), className: s.blocked ? 'bad-text' : 'ok-text' },
    ]
  }
  return [
    { label: '门禁', value: gatePassed ? '通过' : '阻断', className: gatePassed ? 'ok-text' : 'bad-text' },
    { label: '失败', value: String(s.failures || 0) },
    { label: '警告', value: String(s.warnings || 0) },
    { label: '文本相似度', value: formatSimilarity(s.text_similarity) },
    {
      label: '表格数',
      value: `${s.table_count?.reference ?? '-'} → ${s.table_count?.candidate ?? '-'}`,
    },
  ]
})

const diffSampleText = computed(() => {
  if (!reportDiff.value) return ''
  const sections = reportDiff.value.sections || {}
  if (isBatchDiff.value) {
    return JSON.stringify(reportDiff.value.items || [], null, 2)
  }
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

const stageDebugText = computed(() => {
  return JSON.stringify(
    stageReport.value || {
      generation_id: task.value?.generation_id,
      stage_results: task.value?.stage_results || [],
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

function formatSimilarity(value?: number | null) {
  if (value === null || value === undefined) return '-'
  return `${(value * 100).toFixed(2)}%`
}

function formatDurationMs(value?: number | null) {
  if (value === null || value === undefined) return '-'
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`
  return `${Number(value).toFixed(1)}ms`
}

function stageLabel(name?: string) {
  const map: Record<string, string> = {
    PanelResolutionStage: '识别检测项目',
    PanelPackageValidationStage: '校验 Panel 包',
    ExcelReadStage: '读取 Excel',
    FieldResolutionStage: '解析字段',
    PanelRuleExecutionStage: '执行 Panel 规则',
    InputContractValidationStage: '校验输入契约',
    OutputPathStage: '准备输出文件',
    TemplateContractStage: '校验模板契约',
    TemplateRenderStage: '渲染 Word 报告',
    FieldProvenanceStage: '生成字段来源',
    QAStage: '报告质量检查',
    ReportSummaryStage: '生成结果摘要',
  }
  return map[name || ''] || name || '-'
}

function stageSummary(row: Record<string, any>) {
  const metrics = row.metrics || {}
  const artifacts = row.artifacts || {}
  const parts: string[] = []
  if (metrics.project_type) parts.push(`项目 ${metrics.project_type}`)
  if (metrics.single_values !== undefined) parts.push(`单值 ${metrics.single_values}`)
  if (metrics.tables !== undefined) parts.push(`表 ${metrics.tables}`)
  if (metrics.variants !== undefined) parts.push(`变异 ${metrics.variants}`)
  if (metrics.qa_status) parts.push(`QA ${metrics.qa_status}`)
  if (metrics.issue_count !== undefined) parts.push(`问题 ${metrics.issue_count}`)
  if (metrics.variant_count !== undefined) parts.push(`摘要变异 ${metrics.variant_count}`)
  if (artifacts.output_file) parts.push('已生成报告')
  if (artifacts.qa_report_file) parts.push('已生成 QA')
  if (artifacts.field_provenance_file) parts.push('已生成字段来源')
  if (artifacts.report_summary_file) parts.push('已生成结果摘要')
  return parts.join('；') || '-'
}

function stageIssueSummary(row: Record<string, any>) {
  const issues = row.issues || []
  if (!issues.length) return '-'
  return issues
    .map((item: Record<string, any>) => `${item.code || item.level}: ${item.message || '-'}`)
    .join('；')
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    completed: 'success',
    partial_failed: 'danger',
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
    partial_failed: '部分失败',
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
    SKIPPED: 'info',
  }
  return status ? map[status] || 'info' : 'info'
}

function reviewStatusTagType(status?: string | null) {
  const map: Record<string, string> = {
    draft: 'info',
    reviewed: 'success',
    delivered: 'primary',
    rejected: 'danger',
  }
  return status ? map[status] || 'info' : 'info'
}

async function fetchAll() {
  loading.value = true
  qaLoadError.value = ''
  summaryLoadError.value = ''
  provenanceLoadError.value = ''
  stageLoadError.value = ''
  try {
    task.value = await reportApi.getTaskStatus(taskId)
    stageReport.value = task.value?.stage_results?.length
      ? {
          generation_id: task.value.generation_id,
          stage_results: task.value.stage_results,
        }
      : null
    try {
      reportDiff.value = await reportApi.getReportDiff(taskId)
    } catch {
      reportDiff.value = null
    }
    try {
      qualityGate.value = await reportApi.getQualityGate(taskId)
    } catch {
      qualityGate.value = null
    }
    try {
      reviewState.value = await reportApi.getReviewState(taskId)
    } catch {
      reviewState.value = null
    }
    if (task.value?.task_type === 'batch') {
      try {
        batchResults.value = await reportApi.getBatchResults(taskId)
      } catch {
        batchResults.value = null
      }
    } else {
      batchResults.value = null
    }
    try {
      qaReport.value = await reportApi.getQaReport(taskId)
    } catch (err: any) {
      qaReport.value = null
      qaLoadError.value = err.response?.data?.detail || 'QA 报告尚未生成'
    }
    try {
      reportSummary.value = await reportApi.getReportSummary(taskId)
    } catch (err: any) {
      reportSummary.value = null
      summaryLoadError.value = err.response?.data?.detail || '报告结果摘要尚未生成'
    }
    try {
      provenance.value = await reportApi.getFieldProvenance(taskId)
    } catch (err: any) {
      provenance.value = null
      provenanceLoadError.value = err.response?.data?.detail || '字段来源报告尚未生成'
    }
    try {
      stageReport.value = await reportApi.getStageResults(taskId)
    } catch (err: any) {
      if (!stageRows.value.length) {
        stageReport.value = null
        stageLoadError.value = err.response?.data?.detail || '生成阶段报告尚未生成'
      }
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
    const params = { fail_on: diffFailOn.value, max_samples: 50 }
    reportDiff.value = isBatchTask.value
      ? await reportApi.compareBatchWithRegisteredReferences(taskId, params)
      : await reportApi.compareReportWithRegisteredReference(taskId, params)
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
  if (isBatchTask.value) {
    const batchArtifact = artifact === 'report_diff.json' ? 'batch_report_diff.json' : 'batch_report_diff.md'
    window.open(reportApi.getBatchDiffDownloadUrl(taskId, batchArtifact), '_blank')
    return
  }
  window.open(reportApi.getDiffDownloadUrl(taskId, artifact), '_blank')
}

function downloadBatchItemDiff(itemKey: string, artifact: 'report_diff.json' | 'report_diff.md') {
  window.open(reportApi.getBatchDiffItemDownloadUrl(taskId, itemKey, artifact), '_blank')
}

function formatDownloadProgress(progress: DownloadProgress) {
  const percent = progress.percent == null ? '计算中' : `${progress.percent}%`
  const received = `${(progress.receivedBytes / 1024 / 1024).toFixed(1)} MB`
  const total = progress.expectedBytes
    ? `${(progress.expectedBytes / 1024 / 1024).toFixed(1)} MB`
    : '-'
  const retry = progress.attempt > 1 ? `，第 ${progress.attempt}/${progress.maxAttempts} 次续传` : ''
  return `${percent} · ${received}/${total}${retry}`
}

async function downloadReport() {
  reportDownloading.value = true
  downloadStatus.value = '正在准备报告下载'
  try {
    await reportApi.download(taskId, {
      onProgress: (progress) => {
        downloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        downloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    ElMessage.success('报告下载完成')
  } catch (err: any) {
    ElMessage.error(err.message || '报告下载失败')
  } finally {
    reportDownloading.value = false
    window.setTimeout(() => { downloadStatus.value = '' }, 3000)
  }
}

async function downloadBatchZip() {
  batchDownloading.value = true
  downloadStatus.value = '正在准备 ZIP 下载'
  try {
    const result = await reportApi.downloadBatchZip(taskId, false, {
      onProgress: (progress) => {
        downloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        downloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
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
    window.setTimeout(() => { downloadStatus.value = '' }, 3000)
  }
}

async function downloadBatchPassZip() {
  batchPassDownloading.value = true
  downloadStatus.value = '正在准备 QA PASS ZIP 下载'
  try {
    const result = await reportApi.downloadBatchZip(taskId, true, {
      onProgress: (progress) => {
        downloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        downloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    if (result.attempts > 1) {
      ElMessage.success(`QA PASS ZIP 下载成功，已重试 ${result.attempts - 1} 次`)
    } else {
      ElMessage.success('QA PASS ZIP 下载完成')
    }
  } catch (err: any) {
    ElMessage.error(err.message || 'QA PASS ZIP 下载失败')
  } finally {
    batchPassDownloading.value = false
    window.setTimeout(() => { downloadStatus.value = '' }, 3000)
  }
}

async function downloadBatchItem(url: string, index: number) {
  batchItemDownloading.value[index] = true
  try {
    await reportApi.downloadUrl(url, {
      fallbackFilename: `${taskId}.docx`,
      retries: 3,
      timeoutMs: 300000,
      onRetry: (nextAttempt, maxAttempts) => {
        downloadStatus.value = `单份报告连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    ElMessage.success('报告下载完成')
  } catch (err: any) {
    ElMessage.error(err.message || '报告下载失败')
  } finally {
    batchItemDownloading.value[index] = false
    window.setTimeout(() => { downloadStatus.value = '' }, 3000)
  }
}

async function downloadAuditPackage(includeFailed: boolean) {
  auditDownloading.value = true
  downloadStatus.value = '正在准备审计包下载'
  try {
    await reportApi.downloadAuditPackage(taskId, includeFailed, {
      onProgress: (progress) => {
        downloadStatus.value = formatDownloadProgress(progress)
      },
      onRetry: (nextAttempt, maxAttempts) => {
        downloadStatus.value = `连接无进展，正在第 ${nextAttempt}/${maxAttempts} 次断点续传`
      },
    })
    ElMessage.success('审计包下载完成')
  } catch (err: any) {
    ElMessage.error(err.message || '审计包下载失败')
  } finally {
    auditDownloading.value = false
    window.setTimeout(() => { downloadStatus.value = '' }, 3000)
  }
}

async function refreshGate() {
  try {
    qualityGate.value = await reportApi.getQualityGate(taskId)
    reviewState.value = await reportApi.getReviewState(taskId)
    ElMessage.success('生产门禁已刷新')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '生产门禁读取失败')
  }
}

async function markReviewState(status: 'reviewed' | 'delivered') {
  reviewUpdating.value = true
  try {
    reviewState.value = await reportApi.updateReviewState(taskId, {
      status,
      operator: '报告组',
    })
    qualityGate.value = await reportApi.getQualityGate(taskId)
    ElMessage.success(status === 'delivered' ? '已标记交付' : '已标记审核')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '审核状态更新失败')
  } finally {
    reviewUpdating.value = false
  }
}

async function cancelBatchTask() {
  batchCancelling.value = true
  try {
    await reportApi.cancelTask(taskId)
    ElMessage.success('批量任务已取消')
    await fetchAll()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '取消失败')
  } finally {
    batchCancelling.value = false
  }
}

async function retryFailedBatch() {
  batchRetrying.value = true
  try {
    const accepted = await reportApi.retryBatchFailed(taskId)
    ElMessage.info(`已重试 ${accepted.retry_files || 0} 个失败文件`)
    await fetchAll()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '重试失败')
  } finally {
    batchRetrying.value = false
  }
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

.warn-text {
  color: #b54708;
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
  grid-template-columns: repeat(6, minmax(0, 1fr));
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

.report-summary {
  overflow: hidden;
}

.patient-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.patient-strip div {
  min-height: 58px;
  padding: 10px 14px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
}

.patient-strip div:last-child {
  border-right: 0;
}

.patient-strip span,
.biomarker-card span,
.table-subtitle {
  color: #667085;
  font-size: 12px;
}

.patient-strip strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.summary-metrics .metric-box {
  border-bottom: 0;
}

.biomarker-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.biomarker-card {
  min-height: 92px;
  padding: 12px 14px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.biomarker-card:last-child {
  border-right: 0;
}

.biomarker-card strong {
  font-size: 18px;
}

.biomarker-card em {
  color: #475467;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.summary-alert {
  margin: 14px 14px 0;
}

.summary-tables {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, 0.9fr);
  gap: 14px;
  padding: 14px;
}

.table-subtitle {
  margin-bottom: 8px;
  font-weight: 650;
}

.section-gap {
  margin-top: 18px;
}

.batch-detail-progress {
  padding: 14px;
  border-bottom: 1px solid #e6edf3;
}

.batch-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(90px, 1fr));
  border: 1px solid #e6edf3;
  margin-top: 12px;
}

.batch-summary-grid div {
  min-height: 58px;
  padding: 9px 12px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
}

.batch-summary-grid div:last-child {
  border-right: 0;
}

.batch-summary-grid span {
  color: #667085;
  font-size: 12px;
}

.batch-summary-grid strong {
  font-size: 17px;
}

.batch-detail-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.download-status {
  margin-top: 8px;
  color: #667085;
  font-size: 13px;
}

.batch-detail-table {
  margin-top: 0;
}

.gate-content {
  padding: 14px;
}

.gate-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  border: 1px solid #e6edf3;
}

.gate-metrics div {
  min-height: 62px;
  padding: 10px 12px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
}

.gate-metrics div:last-child {
  border-right: 0;
}

.gate-metrics span {
  color: #667085;
  font-size: 12px;
}

.gate-metrics strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.gate-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.gate-table {
  margin-top: 12px;
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

.stage-title-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.stage-alert {
  margin: 14px;
}

.stage-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(90px, 1fr));
  border-bottom: 1px solid #e6edf3;
}

.stage-summary-item {
  min-height: 58px;
  padding: 10px 14px;
  border-right: 1px solid #e6edf3;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
}

.stage-summary-item:last-child {
  border-right: 0;
}

.stage-summary-item span {
  color: #667085;
  font-size: 12px;
}

.stage-summary-item strong {
  font-size: 18px;
}

.stage-table {
  margin-top: 0;
}

.stage-name {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.stage-name strong {
  font-weight: 650;
}

.stage-name span {
  color: #667085;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
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
  .patient-strip,
  .summary-metrics,
  .biomarker-grid,
  .summary-tables,
  .qa-grid,
  .diff-metrics,
  .gate-metrics,
  .batch-summary-grid {
    grid-template-columns: 1fr;
  }

  .stage-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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

  .patient-strip div,
  .biomarker-card {
    border-right: 0;
    border-bottom: 1px solid #e6edf3;
  }

  .patient-strip div:last-child,
  .biomarker-card:last-child {
    border-bottom: 0;
  }

  .stage-summary-item {
    border-bottom: 1px solid #e6edf3;
  }

  .page-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
