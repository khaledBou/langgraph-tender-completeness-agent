export type ReviewStatus = 'pending' | 'running' | 'waiting_for_human' | 'completed' | 'failed';
export type FindingStatus = 'present' | 'missing' | 'doubtful';
export type DecisionStatus = 'present' | 'missing';
export type Verdict = 'complete' | 'incomplete' | '';

export interface RequiredDocument {
  code: string;
  label: string;
  description: string;
  mandatory: boolean;
}

export interface Checklist {
  slug: string;
  name: string;
  items: RequiredDocument[];
}

export interface ReviewFile {
  id: number;
  name: string;
  url: string;
  extraction_error: string;
}

export interface ExtractedDocument {
  file_id: string;
  file_name: string;
  status: 'ok' | 'unreadable';
  error: string;
  document_type: string;
  issuer: string | null;
  issue_date: string | null;
  summary: string;
}

export interface Finding {
  requirement_code: string;
  status: FindingStatus;
  matched_file: string | null;
  evidence: string;
  reasoning: string;
  decided_by: 'rule' | 'model' | 'reviewer';
}

export interface HumanDecision {
  requirement_code: string;
  status: DecisionStatus;
  comment: string;
}

export interface PendingReview {
  reason: string;
  findings: Finding[];
  error?: string;
}

export interface ReviewSummary {
  id: string;
  candidate_name: string;
  checklist: string;
  status: ReviewStatus;
  verdict: Verdict;
  created_at: string;
  completed_at: string | null;
}

export interface Review extends ReviewSummary {
  error: string;
  requirements: RequiredDocument[];
  files: ReviewFile[];
  extracted_documents: ExtractedDocument[];
  findings: Finding[];
  pending_review: PendingReview | null;
  human_decisions: HumanDecision[];
  resolved_findings: Finding[];
  report: string;
  started_at: string | null;
  updated_at: string;
}
