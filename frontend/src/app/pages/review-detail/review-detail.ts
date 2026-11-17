import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { marked } from 'marked';
import { Subscription, catchError, interval, of, switchMap } from 'rxjs';

import { ApiService } from '../../core/api.service';
import { DecisionStatus, Finding, HumanDecision, RequiredDocument, Review } from '../../core/models';
import { StatusBadge } from '../../shared/status-badge';

const POLL_MS = 3000;

@Component({
  selector: 'app-review-detail',
  imports: [RouterLink, DatePipe, FormsModule, StatusBadge],
  templateUrl: './review-detail.html',
  styleUrl: './review-detail.scss',
})
export class ReviewDetail {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  private polling: Subscription | null = null;

  readonly id = input.required<string>();
  readonly review = signal<Review | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly sending = signal(false);
  readonly decisionError = signal('');
  /** True when the last refresh failed. Polling goes on and clears it on success. */
  readonly connectionLost = signal(false);

  /** Decisions typed by the reviewer, keyed by requirement code. */
  readonly decisions = signal<Record<string, { status: DecisionStatus | ''; comment: string }>>({});

  readonly isActive = computed(() => {
    const status = this.review()?.status;
    return status === 'pending' || status === 'running';
  });

  readonly findings = computed<Finding[]>(() => {
    const review = this.review();
    if (!review) return [];
    return review.resolved_findings.length > 0 ? review.resolved_findings : review.findings;
  });

  /** Markdown turned into HTML. Angular sanitises it when bound to [innerHTML]. */
  readonly reportHtml = computed<string>(() => {
    const report = this.review()?.report ?? '';
    return marked.parse(report, { async: false }) as string;
  });

  readonly allDecided = computed(() => {
    const pending = this.review()?.pending_review?.findings ?? [];
    const decisions = this.decisions();
    return pending.length > 0 && pending.every((f) => decisions[f.requirement_code]?.status);
  });

  constructor() {
    this.destroyRef.onDestroy(() => this.polling?.unsubscribe());
  }

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.getReview(this.id()).subscribe({
      next: (review) => this.apply(review),
      error: () => {
        this.error.set('This review could not be loaded.');
        this.loading.set(false);
      },
    });
  }

  requirement(code: string): RequiredDocument | undefined {
    return this.review()?.requirements.find((r) => r.code === code);
  }

  setDecision(code: string, status: DecisionStatus): void {
    this.decisions.update((d) => ({ ...d, [code]: { status, comment: d[code]?.comment ?? '' } }));
  }

  setComment(code: string, comment: string): void {
    this.decisions.update((d) => ({ ...d, [code]: { status: d[code]?.status ?? '', comment } }));
  }

  sendDecisions(): void {
    const review = this.review();
    if (!review?.pending_review) return;
    const payload: HumanDecision[] = review.pending_review.findings.map((f) => ({
      requirement_code: f.requirement_code,
      status: this.decisions()[f.requirement_code].status as DecisionStatus,
      comment: this.decisions()[f.requirement_code].comment,
    }));
    this.sending.set(true);
    this.decisionError.set('');
    this.api.sendDecisions(review.id, payload).subscribe({
      next: (updated) => {
        this.sending.set(false);
        this.apply(updated);
      },
      error: (err) => {
        this.sending.set(false);
        this.decisionError.set(err?.error?.detail ?? 'The decisions could not be sent.');
      },
    });
  }

  private apply(review: Review): void {
    this.review.set(review);
    this.loading.set(false);
    const active = review.status === 'pending' || review.status === 'running';
    if (active && !this.polling) {
      this.polling = interval(POLL_MS)
        .pipe(
          switchMap(() =>
            this.api.getReview(review.id).pipe(
              catchError(() => {
                this.connectionLost.set(true);
                return of(null);
              }),
            ),
          ),
          takeUntilDestroyed(this.destroyRef),
        )
        .subscribe((updated) => {
          if (updated) {
            this.connectionLost.set(false);
            this.apply(updated);
          }
        });
    } else if (!active && this.polling) {
      this.polling.unsubscribe();
      this.polling = null;
    }
  }
}
