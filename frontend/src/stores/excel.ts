import { defineStore } from 'pinia'
import { ref } from 'vue'
import { excelApi, type UploadResult, type SheetInfo, type PatientEnrichment } from '@/api/excel'
import type { ReportSummary } from '@/api/report'

export const useExcelStore = defineStore('excel', () => {
  const upload = ref<UploadResult | null>(null)
  const sheets = ref<SheetInfo[]>([])
  const singleValues = ref<Record<string, any>>({})
  const patientEnrichment = ref<PatientEnrichment | null>(null)
  const previewSummary = ref<ReportSummary | null>(null)
  const sourceFile = ref<File | null>(null)
  const isPersistentUpload = ref(false)
  const loading = ref(false)

  async function uploadFile(file: File) {
    loading.value = true
    try {
      sourceFile.value = file
      const inspected = await excelApi.inspect(file)
      upload.value = inspected.upload
      sheets.value = inspected.sheets
      singleValues.value = inspected.single_values
      patientEnrichment.value = inspected.patient_enrichment || null
      previewSummary.value = inspected.preview_summary || null
      isPersistentUpload.value = false
    } finally {
      loading.value = false
    }
  }

  function reset() {
    upload.value = null
    sheets.value = []
    singleValues.value = {}
    patientEnrichment.value = null
    previewSummary.value = null
    sourceFile.value = null
    isPersistentUpload.value = false
  }

  return {
    upload,
    sheets,
    singleValues,
    patientEnrichment,
    previewSummary,
    sourceFile,
    isPersistentUpload,
    loading,
    uploadFile,
    reset,
  }
})
