import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { analysisApi, appointmentsApi } from '../../services/api'
import { useAuth } from '../../context/AuthContext'
import DashboardLayout from '../../components/common/DashboardLayout'
import { Card, Button, SectionTitle, Empty } from '../../components/common/UI'
import Spinner from '../../components/common/Spinner'
import { Upload, Brain, AlertTriangle, CheckCircle, Clock, ChevronDown, ChevronUp, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import styles from './AIAnalysisPage.module.css'

const SEVERITY_BADGE = {
  high: 'badge badge-danger',
  medium: 'badge badge-gold',
  low: 'badge badge-teal',
}

function ConfidenceBar({ score }) {
  const pct = Math.round(score * 100)
  const color = pct >= 70 ? 'var(--teal)' : pct >= 50 ? 'var(--gold)' : 'var(--rose)'

  return (
    <div className={styles.confBarWrap}>
      <div className={styles.confBarLabel}>
        <span>Confidence</span>
        <span style={{ color, fontWeight: 700 }}>{pct}%</span>
      </div>
      <div className={styles.confBarBg}>
        <div className={styles.confBarFill} style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

function DiagnosisResult({ result, previewUrl, onBookConsultation, bookingLoading }) {
  const [showAll, setShowAll] = useState(false)
  const diag = result.diagnosis
  const isLowConf = diag.confidence_score < 0.7

  return (
    <div className={styles.resultWrap}>
      <div className={styles.resultTop}>
        {previewUrl && (
          <img src={previewUrl} alt="Analysed skin" className={styles.resultThumb} />
        )}
        <div className={styles.resultMeta}>
          <div className={styles.resultLabel}>AI Preliminary Diagnosis</div>
          <div className={styles.conditionBig}>{diag.predicted_condition}</div>
          <span className={SEVERITY_BADGE[diag.severity] || 'badge badge-muted'}>
            {diag.severity} severity
          </span>
        </div>
      </div>

      <ConfidenceBar score={diag.confidence_score} />

      {isLowConf && (
        <div className={styles.warnBanner}>
          <AlertTriangle size={15} />
          <div>
            <strong>Low confidence.</strong> The model is not fully certain.
            A dermatologist consultation is recommended.
          </div>
        </div>
      )}

      {diag.all_predictions?.length > 0 && (
        <div className={styles.predictionsBox}>
          <button className={styles.predictToggle} onClick={() => setShowAll(p => !p)}>
            All condition scores {showAll ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {showAll &&
            diag.all_predictions.map((p, i) => (
              <div key={i} className={styles.predRow}>
                <span className={styles.predLabel}>{p.condition}</span>
                <div className={styles.predBarWrap}>
                  <div className={styles.predBar} style={{ width: `${Math.round(p.score * 100)}%` }} />
                </div>
                <span className={styles.predScore}>{Math.round(p.score * 100)}%</span>
              </div>
            ))}
        </div>
      )}

      <div className={styles.validRow}>
        <Clock size={13} />
        <span>Result sent to your dermatologist for review</span>
      </div>

      {(isLowConf || diag.requires_consultation) && (
        <Button
          fullWidth
          variant="gold"
          icon={<Brain size={15} />}
          loading={bookingLoading}
          onClick={onBookConsultation}
        >
          Book Consultation
        </Button>
      )}
    </div>
  )
}

export default function AIAnalysisPage() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [description, setDesc] = useState('')
  const [bodyArea, setBodyArea] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])
  const [histLoading, setHistLoad] = useState(true)
  const [bookingLoading, setBookLoading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const { refreshMe, updateUser } = useAuth()

  useEffect(() => {
    analysisApi.history()
      .then(r => setHistory(r.data.data || []))
      .catch(() => {})
      .finally(() => setHistLoad(false))
  }, [])

  const onDrop = useCallback(accepted => {
    if (!accepted[0]) return
    setFile(accepted[0])
    setPreview(URL.createObjectURL(accepted[0]))
    setResult(null)
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpg', '.jpeg', '.png', '.webp'] },
    maxFiles: 1,
    maxSize: 16 * 1024 * 1024,
    onDropRejected: () => toast.error('File too large or unsupported format'),
  })

  const handleAnalyze = async () => {
    if (!file) {
      toast.error('Please select an image first')
      return
    }

    setAnalyzing(true)
    try {
      const fd = new FormData()
      fd.append('image', file)
      if (description) fd.append('description', description)
      if (bodyArea) fd.append('body_area', bodyArea)

      const res = await analysisApi.upload(fd)
      const data = res.data.data

    setResult(data)
    setHistory(prev => [{ ...data.image, diagnosis: data.diagnosis }, ...prev])

    if (typeof data.loyalty_points === 'number') {
      updateUser(prev => ({
        ...prev,
        profile: {
          ...prev.profile,
          loyalty_points: data.loyalty_points,
        },
      }))
    } else {
      await refreshMe()
    }

    toast.success('Analysis complete!')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Analysis failed. Please try again.')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleReset = () => {
    setFile(null)
    setPreview(null)
    setResult(null)
    setDesc('')
    setBodyArea('')
  }

  const handleDelete = async (skinImageId) => {
    if (deletingId === skinImageId) return

    setDeletingId(skinImageId)
    try {
      await analysisApi.remove(skinImageId)
      setHistory(prev => prev.filter(item => item.id !== skinImageId))
      toast.success('Analysis deleted')
    } catch (err) {
      toast.error(err.response?.data?.error || 'Could not delete analysis')
    } finally {
      setDeletingId(null)
    }
  }

  const handleBookConsultation = async () => {
    setBookLoading(true)
    try {
      await appointmentsApi.book({
        scheduled_at: new Date(Date.now() + 48 * 3600000).toISOString(),
        appointment_type: 'in_person',
        reason: `AI follow-up: ${result?.diagnosis?.predicted_condition}`,
      })
      toast.success('Consultation request sent!')
    } catch {
      toast.error('Could not book. Please use the Appointments page.')
    } finally {
      setBookLoading(false)
    }
  }

  return (
    <DashboardLayout
      title="AI Skin Analysis"
      subtitle="Upload a photo and receive an instant AI-powered diagnosis"
    >
      <div className={styles.layout}>
        <div className={styles.uploadPanel}>
          {!result && (
            <Card>
              <SectionTitle sub="JPG, PNG or WebP · max 16 MB">Upload Image</SectionTitle>

              <div
                {...getRootProps()}
                className={`${styles.dropzone} ${isDragActive ? styles.dropActive : ''} ${preview ? styles.dropHasFile : ''}`}
              >
                <input {...getInputProps()} />
                {preview ? (
                  <img src={preview} alt="preview" className={styles.preview} />
                ) : (
                  <div className={styles.dropPlaceholder}>
                    <Upload size={36} color="var(--teal)" />
                    <p>{isDragActive ? 'Drop it here' : 'Drag & drop or click to select'}</p>
                    <span>Supports JPG, PNG, WebP</span>
                  </div>
                )}
              </div>

              {preview && (
                <div className={styles.metaFields}>
                  <input
                    className={styles.metaInput}
                    placeholder="Description (optional)"
                    value={description}
                    onChange={e => setDesc(e.target.value)}
                  />
                  <input
                    className={styles.metaInput}
                    placeholder="Body area, e.g. left cheek (optional)"
                    value={bodyArea}
                    onChange={e => setBodyArea(e.target.value)}
                  />
                </div>
              )}

              <div className={styles.uploadActions}>
                {preview && (
                  <>
                    <Button onClick={handleAnalyze} loading={analyzing} icon={<Brain size={16} />} fullWidth>
                      {analyzing ? 'Analyzing…' : 'Run AI Analysis'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={handleReset}>
                      Clear
                    </Button>
                  </>
                )}
              </div>
            </Card>
          )}

          {result && (
            <Card className={styles.resultCard}>
              <div className={styles.resultCardHead}>
                <CheckCircle size={20} color="var(--teal)" />
                <span>Analysis Complete</span>
              </div>

              <DiagnosisResult
                result={result}
                previewUrl={preview}
                onBookConsultation={handleBookConsultation}
                bookingLoading={bookingLoading}
              />

              <Button variant="secondary" fullWidth onClick={handleReset} style={{ marginTop: 16 }}>
                Analyse Another Image
              </Button>
            </Card>
          )}
        </div>

        <div className={styles.historyPanel}>
          <SectionTitle sub="All your previous AI analyses">History</SectionTitle>

          {histLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
              <Spinner />
            </div>
          ) : history.length === 0 ? (
            <Empty icon="🔬" title="No analyses yet" description="Upload your first image to get started." />
          ) : (
            <div className={styles.histList}>
              {history.map(item => (
                <Card key={item.id} className={styles.histItem}>
                  <div className={styles.histRow}>
                    {item.image_url && (
                      <img
                        src={item.image_url}
                        alt="skin"
                        className={styles.histThumb}
                        onError={e => {
                          e.target.style.display = 'none'
                        }}
                      />
                    )}

                    <div className={styles.histInfo}>
                      <div className={styles.histTop}>
                        <div className={styles.histCond}>{item.diagnosis?.predicted_condition || '—'}</div>
                        <div className={styles.histDate}>{format(new Date(item.uploaded_at), 'MMM d, yyyy')}</div>
                      </div>

                      <div className={styles.histMeta}>
                        {item.body_area && <span>{item.body_area} · </span>}
                        {item.diagnosis && (
                          <>
                            <span className={SEVERITY_BADGE[item.diagnosis.severity] || 'badge badge-muted'}>
                              {item.diagnosis.severity}
                            </span>
                            <span className={styles.histConf}>
                              {Math.round(item.diagnosis.confidence_score * 100)}%
                            </span>
                          </>
                        )}
                      </div>

                      {item.diagnosis?.doctor_confirmed === true && (
                        <div className={styles.histValidated}>
                          <CheckCircle size={11} /> Doctor validated
                          {item.diagnosis.doctor_diagnosis &&
                            item.diagnosis.doctor_diagnosis !== item.diagnosis.predicted_condition &&
                            ` → ${item.diagnosis.doctor_diagnosis}`}
                        </div>
                      )}

                      {item.diagnosis?.doctor_confirmed === null && (
                        <div className={styles.histPending}>
                          <Clock size={11} /> Awaiting doctor review
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      className={styles.deleteBtn}
                      onClick={() => handleDelete(item.id)}
                      disabled={deletingId === item.id}
                      title="Delete analysis"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  )
}