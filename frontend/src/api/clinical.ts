import client from './client'

export interface FieldUiHints {
  component: string
  placeholder: string | null
  span: number
  options: string[] | null
  accept: string | null
}

export interface FieldSchema {
  key: string
  label: string
  type: string
  required: boolean
  default: any
  description: string | null
  format: string | null
  synonyms: string[]
  computed: boolean
  ui: FieldUiHints
}

export interface FieldGroup {
  id: string
  label: string
  fields: FieldSchema[]
}

export interface ClinicalFormSchema {
  groups: FieldGroup[]
  project_type: string | null
}

export interface PatientInfo {
  sample_id: string
  patient_name?: string | null
  gender?: string | null
  age?: string | null
  pathology_id?: string | null
  hospital?: string | null
  department?: string | null
  collection_date?: string | null
  receive_date?: string | null
}

export interface SignatureUploadResponse {
  stored_path: string
  original_filename: string
  file_size_bytes: number
}

export const clinicalApi = {
  async getSchema(projectType?: string | null): Promise<ClinicalFormSchema> {
    const params = projectType ? { project_type: projectType } : {}
    const { data } = await client.get('/clinical-schema', { params })
    return data.data
  },

  async listPatients(): Promise<PatientInfo[]> {
    const { data } = await client.get('/patients')
    return data.data
  },

  async getPatient(sampleId: string): Promise<PatientInfo> {
    const { data } = await client.get(`/patients/${encodeURIComponent(sampleId)}`)
    return data.data
  },

  async createPatient(patient: PatientInfo): Promise<PatientInfo> {
    const { data } = await client.post('/patients', patient)
    return data.data
  },

  async updatePatient(sampleId: string, patient: PatientInfo): Promise<PatientInfo> {
    const { data } = await client.put(`/patients/${encodeURIComponent(sampleId)}`, patient)
    return data.data
  },

  async deletePatient(sampleId: string): Promise<void> {
    await client.delete(`/patients/${encodeURIComponent(sampleId)}`)
  },

  async uploadSignature(file: File): Promise<SignatureUploadResponse> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await client.post('/signature-images', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.data
  },
}
