import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { Checklist } from '../../core/models';

@Component({
  selector: 'app-review-new',
  imports: [FormsModule, RouterLink],
  templateUrl: './review-new.html',
  styleUrl: './review-new.scss',
})
export class ReviewNew {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);

  readonly checklists = signal<Checklist[]>([]);
  readonly files = signal<File[]>([]);
  readonly submitting = signal(false);
  readonly error = signal('');

  candidateName = '';
  checklist = '';

  constructor() {
    this.api.getChecklists().subscribe({
      next: (checklists) => {
        this.checklists.set(checklists);
        if (checklists.length > 0) {
          this.checklist = checklists[0].slug;
        }
      },
      error: () => this.error.set('The checklists could not be loaded.'),
    });
  }

  get selectedChecklist(): Checklist | undefined {
    return this.checklists().find((c) => c.slug === this.checklist);
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.files.set(Array.from(input.files ?? []));
  }

  removeFile(index: number): void {
    this.files.update((files) => files.filter((_, i) => i !== index));
  }

  submit(): void {
    if (!this.candidateName.trim() || !this.checklist) {
      this.error.set('Give the candidate name and choose a checklist.');
      return;
    }
    this.submitting.set(true);
    this.error.set('');
    this.api.createReview(this.candidateName.trim(), this.checklist, this.files()).subscribe({
      next: (review) => this.router.navigate(['/reviews', review.id]),
      error: (err) => {
        this.error.set(err?.error?.detail ?? 'The review could not be created.');
        this.submitting.set(false);
      },
    });
  }
}
