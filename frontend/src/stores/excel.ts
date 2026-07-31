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
  let uploadRequestId = 0

  async function uploadFile(file: File): Promise<boolean> {
    const requestId = ++uploadRequestId
    loading.value = true
    try {
      const inspected = await excelApi.inspect(file)
      if (requestId !== uploadRequestId) return false
      sourceFile.value = file
      upload.value = inspected.upload
      sheets.value = inspected.sheets
      singleValues.value = inspected.single_values
      patientEnrichment.value = inspected.patient_enrichment || null
      previewSummary.value = inspected.preview_summary || null
      isPersistentUpload.value = false
      return true
    } catch (error) {
      if (requestId !== uploadRequestId) return false
      throw error
    } finally {
      if (requestId === uploadRequestId) loading.value = false
    }
  }

  function reset() {
    uploadRequestId += 1
    upload.value = null
    sheets.value = []
    singleValues.value = {}
    patientEnrichment.value = null
    previewSummary.value = null
    sourceFile.value = null
    isPersistentUpload.value = false
    loading.value = false
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
