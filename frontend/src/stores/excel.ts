import { defineStore } from 'pinia'
import { ref } from 'vue'
import { excelApi, type UploadResult, type SheetInfo } from '@/api/excel'

export const useExcelStore = defineStore('excel', () => {
  const upload = ref<UploadResult | null>(null)
  const sheets = ref<SheetInfo[]>([])
  const singleValues = ref<Record<string, any>>({})
  const loading = ref(false)

  async function uploadFile(file: File) {
    loading.value = true
    try {
      upload.value = await excelApi.upload(file)
      // Load sheets and single values in parallel
      const [s, v] = await Promise.all([
        excelApi.getSheets(upload.value.upload_id),
        excelApi.getSingleValues(upload.value.upload_id),
      ])
      sheets.value = s
      singleValues.value = v
    } finally {
      loading.value = false
    }
  }

  function reset() {
    upload.value = null
    sheets.value = []
    singleValues.value = {}
  }

  return { upload, sheets, singleValues, loading, uploadFile, reset }
})
