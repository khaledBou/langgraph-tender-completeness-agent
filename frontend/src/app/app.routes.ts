import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'reviews', pathMatch: 'full' },
  { path: 'reviews', loadComponent: () => import('./pages/reviews-list/reviews-list').then((m) => m.ReviewsList) },
  { path: 'reviews/new', loadComponent: () => import('./pages/review-new/review-new').then((m) => m.ReviewNew) },
  { path: 'reviews/:id', loadComponent: () => import('./pages/review-detail/review-detail').then((m) => m.ReviewDetail) },
  { path: '**', redirectTo: 'reviews' },
];
