import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Checklist, HumanDecision, Review, ReviewSummary } from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api';

  getChecklists(): Observable<Checklist[]> {
    return this.http.get<Checklist[]>(`${this.base}/checklists/`);
  }

  getReviews(): Observable<ReviewSummary[]> {
    return this.http.get<ReviewSummary[]>(`${this.base}/reviews/`);
  }

  getReview(id: string): Observable<Review> {
    return this.http.get<Review>(`${this.base}/reviews/${id}/`);
  }

  createReview(candidateName: string, checklist: string, files: File[]): Observable<Review> {
    const form = new FormData();
    form.append('candidate_name', candidateName);
    form.append('checklist', checklist);
    for (const file of files) {
      form.append('files', file, file.name);
    }
    return this.http.post<Review>(`${this.base}/reviews/`, form);
  }

  sendDecisions(id: string, decisions: HumanDecision[]): Observable<Review> {
    return this.http.post<Review>(`${this.base}/reviews/${id}/decisions/`, { decisions });
  }
}
