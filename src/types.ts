export type Cue = { id: string; cue_index: number; start_ms: number; end_ms: number; source_text: string; translated_text: string | null; confidence: number | null; notes: string | null };
export type Project = { id: string; title: string; series: string | null; youtube_video_id: string | null; transcript_language: 'chinese' | 'english'; created_at: string; cue_count?: number; translated_count?: number; cues?: Cue[] };
export type Rule = { id: string; series: string | null; project_id: string | null; source_variants: string[]; target_term: string; rule_type: 'locked' | 'preferred'; note: string | null };
export type SubtitleBundle = { version: number; project: Project; cues: Cue[] };
