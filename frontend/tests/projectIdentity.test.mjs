import assert from 'node:assert/strict'
import test from 'node:test'
import { pdl1VariantForForm } from '../src/utils/projectIdentity.ts'

test('NGS-only form does not imply an IHC order', () => {
  for (const type of ['lung_62', 'lung_588']) {
    assert.equal(pdl1VariantForForm(type, {}), null)
    assert.equal(pdl1VariantForForm(type, { pdl1_tps: null, pdl1_cps: '', pdl1_result: '  ' }), null)
    assert.equal(pdl1VariantForForm(type, { pdl1_assay_profile_id: 'legacy_unspecified_ihc_transcription_v1' }), null)
  }
})

test('a supplied PD-L1 zero or case source selects only the matching sibling', () => {
  for (const type of ['lung_62', 'lung_588']) {
    for (const values of [{ pdl1_tps: 0 }, { pdl1_cps: 0 }, { pdl1_result: '阴性' }, { pdl1_source_record_id: 'synthetic-source' }]) {
      assert.equal(pdl1VariantForForm(type, values), type + '_pdl1')
    }
  }
})

test('does not switch unrelated products or silently downgrade an explicit IHC selection', () => {
  for (const type of [null, 'lung_13', 'crc_358_msi', 'lung_62_pdl1', 'lung_588_pdl1']) {
    assert.equal(pdl1VariantForForm(type, { pdl1_tps: 5 }), null)
    assert.equal(pdl1VariantForForm(type, {}), null)
  }
})
