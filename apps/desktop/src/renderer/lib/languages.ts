import type { LanguageShare, TranscriptSegment } from '../../shared/types'

const LABELS: Record<string, string> = {
  te: 'Telugu',
  en: 'English',
  hi: 'Hindi',
  ta: 'Tamil',
  kn: 'Kannada',
  ml: 'Malayalam',
  mr: 'Marathi',
  bn: 'Bengali',
  gu: 'Gujarati',
  pa: 'Punjabi',
  ur: 'Urdu',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
  pt: 'Portuguese',
  ar: 'Arabic',
  zh: 'Chinese',
  ja: 'Japanese',
  ko: 'Korean',
  other: 'Other'
}

export function languageLabel(code: string | null | undefined): string {
  if (!code) return 'Other'
  return LABELS[code] ?? code.toUpperCase()
}

/** Script-based reclassify for older reports that stored Hindi as "other". */
export function detectLanguageFromText(text: string, fallback = 'other'): string {
  const counts: Record<string, number> = {
    te: 0,
    hi: 0,
    ta: 0,
    kn: 0,
    ml: 0,
    bn: 0,
    gu: 0,
    pa: 0,
    ar: 0,
    en: 0
  }
  for (const ch of text) {
    const o = ch.codePointAt(0) ?? 0
    if (o >= 0x0c00 && o <= 0x0c7f) counts.te++
    else if (o >= 0x0900 && o <= 0x097f) counts.hi++
    else if (o >= 0x0b80 && o <= 0x0bff) counts.ta++
    else if (o >= 0x0c80 && o <= 0x0cff) counts.kn++
    else if (o >= 0x0d00 && o <= 0x0d7f) counts.ml++
    else if (o >= 0x0980 && o <= 0x09ff) counts.bn++
    else if (o >= 0x0a80 && o <= 0x0aff) counts.gu++
    else if (o >= 0x0a00 && o <= 0x0a7f) counts.pa++
    else if (o >= 0x0600 && o <= 0x06ff) counts.ar++
    else if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z')) counts.en++
  }
  const ranked = Object.entries(counts).sort((a, b) => b[1] - a[1])
  const [top, n] = ranked[0]
  const second = ranked[1]?.[1] ?? 0
  if (n > 0 && n >= Math.max(2, second)) return top
  if (fallback && fallback !== 'other') return fallback
  return 'other'
}

export function resolveSegmentLanguage(seg: TranscriptSegment): string {
  const code = seg.language || 'other'
  if (code !== 'other') {
    // Still override when script clearly disagrees (Hindi marked other/en)
    const fromText = detectLanguageFromText(seg.text, code)
    if (fromText !== 'en' || code === 'en') {
      if (fromText === 'hi' || fromText === 'te' || fromText === 'ta') return fromText
    }
    return code
  }
  return detectLanguageFromText(seg.text, 'other')
}

export function buildLanguageBreakdown(
  transcript: TranscriptSegment[],
  existing?: LanguageShare[] | null
): LanguageShare[] {
  if (existing && existing.length > 0) {
    // Refresh labels; keep percents
    return existing.map((b) => ({ ...b, label: languageLabel(b.code) }))
  }
  const byLang: Record<string, number> = {}
  let total = 0
  for (const seg of transcript) {
    const dur = Math.max(0.01, seg.end - seg.start)
    const code = resolveSegmentLanguage(seg)
    byLang[code] = (byLang[code] ?? 0) + dur
    total += dur
  }
  if (total <= 0) return []
  return Object.entries(byLang)
    .map(([code, dur]) => ({
      code,
      label: languageLabel(code),
      percent: Math.round((1000 * dur) / total) / 10
    }))
    .sort((a, b) => b.percent - a.percent)
}
