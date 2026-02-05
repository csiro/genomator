import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

const routes: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./pages/home/home.component').then((m) => m.HomeComponent),
  },
  // {
  //   path: 'tabular',
  //   loadComponent: () => import('./pages/tabular/tabular.component').then(m => m.TabularComponent)
  // },
  {
    path: 'genomic',
    loadComponent: () =>
      import('./pages/genomic/genomic.component').then(
        (m) => m.GenomicComponent,
      ),
  },
  {
    path: 'calculate',
    loadComponent: () =>
      import('./pages/calculate-privacy-metric/calculate-privacy-metric.component').then(
        (m) => m.CalculatePrivacyMetricComponent,
      ),
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule],
})
export class AppRoutingModule {}
