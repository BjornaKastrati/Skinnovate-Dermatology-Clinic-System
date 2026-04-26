import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analysisApi, recordsApi, treatmentsApi } from '../../services/api'
import DashboardLayout from '../../components/common/DashboardLayout'
import { Card, Button, FormField, Input, Textarea, Select, SectionTitle } from '../../components/common/UI'
import Spinner from '../../components/common/Spinner'
import { CheckCircle, Edit3, Plus, Brain } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import styles from './ValidationPage.module.css'

export default function ValidationPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [diag, setDiag] = useState(null)
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState('view')
  const [saving, setSaving] = useState(false)
  const [existingTreatment, setExistingTreatment] = useState(null)

  const [modifyForm, setModifyForm] = useState({ doctor_diagnosis: '' })
  const [noteForm, setNoteForm] = useState({ note_text: '', follow_up_date: '' })
  const [treatForm, setTreatForm] = useState({
    title: '',
    description: '',
    treatment_type: '',
    start_date: new Date().toISOString().slice(0, 10),
  })

  const loadTreatmentForDiagnosis = async (patientId, diagnosisId) => {
    try {
      const res = await treatmentsApi.forPatient(patientId)
      const allTreatments = res.data.data || []
      const linked = allTreatments.find(t => t.diagnosis_id === diagnosisId) || null
      setExistingTreatment(linked)
    } catch {
      setExistingTreatment(null)
    }
  }

  useEffect(() => {
    const loadPage = async () => {
      try {
        const res = await analysisApi.get(id)
        const data = res.data.data
        setDiag(data)
        setModifyForm({ doctor_diagnosis: data.predicted_condition })

        const patientId = data?.skin_image?.patient_id
        if (patientId) {
          await loadTreatmentForDiagnosis(patientId, parseInt(id))
        }
      } catch {
        toast.error('Diagnosis not found')
      } finally {
        setLoading(false)
      }
    }

    loadPage()
  }, [id])

  const handleConfirm = async () => {
    setSaving(true)
    try {
      await analysisApi.validate(id, { confirmed: true, doctor_diagnosis: diag.predicted_condition })
      toast.success('Diagnosis confirmed!')
      navigate('/doctor/queue')
    } catch {
      toast.error('Failed to confirm')
    } finally {
      setSaving(false)
    }
  }

  const handleModify = async e => {
    e.preventDefault()
    if (!modifyForm.doctor_diagnosis) {
      toast.error('Please enter your diagnosis')
      return
    }

    setSaving(true)
    try {
      await analysisApi.validate(id, { confirmed: false, doctor_diagnosis: modifyForm.doctor_diagnosis })
      toast.success('Diagnosis updated!')
      navigate('/doctor/queue')
    } catch {
      toast.error('Failed to update')
    } finally {
      setSaving(false)
    }
  }

  const handleNote = async e => {
    e.preventDefault()
    if (!noteForm.note_text) {
      toast.error('Note cannot be empty')
      return
    }

    setSaving(true)
    try {
      await recordsApi.createNote({
        appointment_id: 1,
        patient_id: diag?.skin_image?.patient_id || 1,
        diagnosis_id: parseInt(id),
        note_text: noteForm.note_text,
        follow_up_date: noteForm.follow_up_date || undefined,
      })
      toast.success('Medical note saved!')
      setMode('view')
    } catch {
      toast.error('Failed to save note')
    } finally {
      setSaving(false)
    }
  }

  const handleTreatment = async e => {
    e.preventDefault()
    if (!treatForm.title) {
      toast.error('Treatment title required')
      return
    }

    setSaving(true)
    try {
      await treatmentsApi.create({
        ...treatForm,
        patient_id: diag?.skin_image?.patient_id || 1,
        diagnosis_id: parseInt(id),
      })

      toast.success('Treatment plan created!')
      setMode('view')

      const patientId = diag?.skin_image?.patient_id
      if (patientId) {
        await loadTreatmentForDiagnosis(patientId, parseInt(id))
      }
    } catch {
      toast.error('Failed to create treatment')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdateTreatmentStatus = async (status) => {
    if (!existingTreatment) return

    setSaving(true)
    try {
      await treatmentsApi.update(existingTreatment.id, { status })
      toast.success(`Treatment marked as ${status}`)

      setExistingTreatment(prev => ({
        ...prev,
        status,
      }))
    } catch {
      toast.error('Failed to update treatment status')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <DashboardLayout title="Validate Diagnosis">
        <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
          <Spinner size={40} />
        </div>
      </DashboardLayout>
    )
  }

  if (!diag) {
    return (
      <DashboardLayout title="Not Found">
        <p style={{ color: 'var(--text-muted)', padding: 40 }}>Diagnosis not found.</p>
      </DashboardLayout>
    )
  }

  const imageUrl = diag.skin_image?.image_url

  return (
    <DashboardLayout title="Review Diagnosis" subtitle="Validate, modify, or create a treatment plan">
      <div className={styles.layout}>

        {/* Left: AI result + patient image */}
        <Card className={styles.diagCard}>
          <SectionTitle sub="AI-generated preliminary result">AI Diagnosis</SectionTitle>

          {imageUrl && (
            <div className={styles.imageWrap}>
              <img
                src={imageUrl}
                alt="Patient skin"
                className={styles.patientImage}
                onError={e => { e.target.parentElement.style.display = 'none' }}
              />
              <div className={styles.imageCaption}>
                {diag.skin_image?.patient_name && (
                  <div style={{ fontWeight: 600, color: 'var(--teal)' }}>
                    Patient: {diag.skin_image.patient_name}
                  </div>
                )}

                {diag.skin_image?.body_area && <span>{diag.skin_image.body_area} · </span>}
                Uploaded {diag.skin_image?.uploaded_at
                  ? format(new Date(diag.skin_image.uploaded_at), 'MMM d, yyyy · h:mm a')
                  : '—'}
              </div>
            </div>
          )}

          <div className={styles.condBlock}>
            <Brain size={26} color="var(--teal)" />
            <div>
              <div className={styles.condName}>
                {diag.doctor_confirmed === false && diag.doctor_diagnosis
                  ? diag.doctor_diagnosis
                  : diag.predicted_condition}
              </div>
              <div className={styles.condConf}>{Math.round(diag.confidence_score * 100)}% confidence</div>
            </div>
            <span className={`badge badge-${diag.severity === 'high' ? 'danger' : diag.severity === 'medium' ? 'gold' : 'teal'}`}>
              {diag.severity}
            </span>
          </div>

          <div className={styles.confWrap}>
            <div className={styles.confBar}>
              <div
                className={styles.confFill}
                style={{
                  width: `${Math.round(diag.confidence_score * 100)}%`,
                  background: diag.confidence_score >= 0.7 ? 'var(--teal)' : diag.confidence_score >= 0.5 ? 'var(--gold)' : 'var(--rose)',
                }}
              />
            </div>
            <div className={styles.confNums}>
              <span>{Math.round(diag.confidence_score * 100)}%</span>
            </div>
          </div>

          {diag.all_predictions?.length > 0 && (
            <div className={styles.allPreds}>
              <div className={styles.predTitle}>All condition scores</div>
              {diag.all_predictions.map((p, i) => (
                <div key={i} className={styles.predRow}>
                  <span className={styles.predLabel}>{p.condition}</span>
                  <div className={styles.predBarWrap}>
                    <div className={styles.predBar} style={{ width: `${Math.round(p.score * 100)}%` }} />
                  </div>
                  <span className={styles.predVal}>{Math.round(p.score * 100)}%</span>
                </div>
              ))}
            </div>
          )}

          <div className={styles.diagMeta}>
            Analysed {diag.diagnosed_at ? format(new Date(diag.diagnosed_at), 'MMM d, yyyy · h:mm a') : '—'}
          </div>

          {diag.doctor_confirmed !== null && (
            <div className={styles.alreadyVal}>
              <CheckCircle size={15} /> Already validated
              {diag.doctor_diagnosis && diag.doctor_diagnosis !== diag.predicted_condition && (
                <span> → {diag.doctor_diagnosis}</span>
              )}
            </div>
          )}
        </Card>

        {/* Right: actions */}
        <div className={styles.actionsPanel}>

          {diag.doctor_confirmed === null && mode === 'view' && (
            <Card className={styles.actionCard}>
              <SectionTitle sub="Choose your action">Validate Diagnosis</SectionTitle>
              <div className={styles.actionBtns}>
                <Button fullWidth icon={<CheckCircle size={16}/>} onClick={handleConfirm} loading={saving}>
                  Confirm AI Diagnosis
                </Button>
                <Button fullWidth variant="secondary" icon={<Edit3 size={16}/>} onClick={() => setMode('modify')}>
                  Modify Diagnosis
                </Button>
              </div>
            </Card>
          )}

          {mode === 'modify' && (
            <Card className={styles.actionCard}>
              <SectionTitle sub="Enter your clinical diagnosis">Your Diagnosis</SectionTitle>
              <form onSubmit={handleModify} className={styles.form}>
                <FormField label="Diagnosis" required>
                  <Select
                    value={modifyForm.doctor_diagnosis}
                    onChange={e => setModifyForm({ doctor_diagnosis: e.target.value })}
                  >
                    <option value="">Select condition</option>
                    {['Acne', 'Eczema', 'Milia', 'Normal', 'Rosacea'].map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </Select>
                </FormField>
                <div className={styles.formActions}>
                  <Button type="button" variant="ghost" onClick={() => setMode('view')}>Cancel</Button>
                  <Button type="submit" loading={saving}>Save Diagnosis</Button>
                </div>
              </form>
            </Card>
          )}

          <Card className={styles.actionCard}>
            <div className={styles.collapsibleHead} onClick={() => setMode(m => m === 'note' ? 'view' : 'note')}>
              <SectionTitle sub="Add consultation notes">Medical Note</SectionTitle>
              <Plus size={18} style={{ color: 'var(--teal)', flexShrink: 0 }} />
            </div>
            {mode === 'note' && (
              <form onSubmit={handleNote} className={styles.form} style={{ marginTop: 16 }}>
                <FormField label="Note" required>
                  <Textarea
                    value={noteForm.note_text}
                    onChange={e => setNoteForm(p => ({ ...p, note_text: e.target.value }))}
                    placeholder="Clinical observations, recommendations..."
                    required
                  />
                </FormField>
                <FormField label="Follow-up Date">
                  <Input
                    type="date"
                    value={noteForm.follow_up_date}
                    onChange={e => setNoteForm(p => ({ ...p, follow_up_date: e.target.value }))}
                  />
                </FormField>
                <Button type="submit" loading={saving} fullWidth>Save Note</Button>
              </form>
            )}
          </Card>

          <Card className={styles.actionCard}>
            <div className={styles.collapsibleHead} onClick={() => setMode(m => m === 'treatment' ? 'view' : 'treatment')}>
              <SectionTitle sub="Create a treatment plan">Treatment Plan</SectionTitle>
              <Plus size={18} style={{ color: 'var(--teal)', flexShrink: 0 }} />
            </div>

            {existingTreatment && (
              <div style={{ marginTop: 12, marginBottom: 12 }}>
                <div style={{ color: 'var(--cream)', fontWeight: 600, marginBottom: 6 }}>
                  Existing treatment: {existingTreatment.title}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: 10 }}>
                  Status: <span className={`badge badge-${existingTreatment.status === 'active' ? 'teal' : existingTreatment.status === 'completed' ? 'success' : 'muted'}`}>
                    {existingTreatment.status}
                  </span>
                </div>

                {existingTreatment.status === 'active' && (
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => handleUpdateTreatmentStatus('completed')}
                      loading={saving}
                    >
                      Mark Completed
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleUpdateTreatmentStatus('cancelled')}
                      loading={saving}
                    >
                      Cancel Treatment
                    </Button>
                  </div>
                )}
              </div>
            )}

            {mode === 'treatment' && !existingTreatment && (
              <form onSubmit={handleTreatment} className={styles.form} style={{ marginTop: 16 }}>
                <FormField label="Title" required>
                  <Input
                    value={treatForm.title}
                    onChange={e => setTreatForm(p => ({ ...p, title: e.target.value }))}
                    placeholder="e.g. Topical Acne Treatment Plan"
                    required
                  />
                </FormField>
                <FormField label="Type">
                  <Select value={treatForm.treatment_type} onChange={e => setTreatForm(p => ({ ...p, treatment_type: e.target.value }))}>
                    <option value="">Select type</option>
                    <option value="topical">Topical</option>
                    <option value="laser">Laser</option>
                    <option value="cosmetic">Cosmetic</option>
                    <option value="surgical">Surgical</option>
                    <option value="systemic">Systemic</option>
                  </Select>
                </FormField>
                <FormField label="Description">
                  <Textarea
                    value={treatForm.description}
                    onChange={e => setTreatForm(p => ({ ...p, description: e.target.value }))}
                    placeholder="Detailed treatment instructions..."
                  />
                </FormField>
                <FormField label="Start Date" required>
                  <Input
                    type="date"
                    value={treatForm.start_date}
                    onChange={e => setTreatForm(p => ({ ...p, start_date: e.target.value }))}
                    required
                  />
                </FormField>
                <Button type="submit" loading={saving} fullWidth>Create Treatment Plan</Button>
              </form>
            )}
          </Card>
        </div>
      </div>
    </DashboardLayout>
  )
}