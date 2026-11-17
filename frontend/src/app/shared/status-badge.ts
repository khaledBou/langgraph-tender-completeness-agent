import { Component, computed, input } from '@angular/core';

const LABELS: Record<string, string> = {
  pending: 'Pending',
  running: 'Running',
  waiting_for_human: 'Needs a decision',
  completed: 'Completed',
  failed: 'Failed',
  present: 'Present',
  missing: 'Missing',
  doubtful: 'Doubtful',
  complete: 'Complete',
  incomplete: 'Incomplete',
  ok: 'Read',
  unreadable: 'Unreadable',
};

@Component({
  selector: 'app-status-badge',
  template: `<span class="badge" [class]="'badge badge-' + value()">{{ label() }}</span>`,
  styles: `
    .badge {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      line-height: 1.5;
      white-space: nowrap;
      background: var(--neutral-100);
      color: var(--neutral-700);
    }
    .badge-running, .badge-pending { background: var(--info-100); color: var(--info-700); }
    .badge-waiting_for_human, .badge-doubtful { background: var(--warning-100); color: var(--warning-700); }
    .badge-completed, .badge-present, .badge-complete, .badge-ok { background: var(--success-100); color: var(--success-700); }
    .badge-failed, .badge-missing, .badge-incomplete, .badge-unreadable { background: var(--danger-100); color: var(--danger-700); }
  `,
})
export class StatusBadge {
  readonly value = input.required<string>();
  readonly label = computed(() => LABELS[this.value()] ?? this.value());
}
