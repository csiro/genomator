import { HttpClient, HttpClientModule } from '@angular/common/http';
import { Component, OnInit } from '@angular/core';
import { HighlightModule } from 'ngx-highlightjs';
import { ToastrService } from 'ngx-toastr';
import { catchError } from 'rxjs';

@Component({
  selector: 'app-calculate-privacy-metric',
  standalone: true,
  templateUrl: './calculate-privacy-metric.component.html',
  styleUrls: ['./calculate-privacy-metric.component.css'],
  imports: [HttpClientModule, HighlightModule],
})
export class CalculatePrivacyMetricComponent implements OnInit {
  code = '';
  deps = '';

  constructor(
    private http: HttpClient,
    private toastr: ToastrService,
  ) {}

  ngOnInit(): void {
    this.http
      .get('/assets/privacy_metric.py', { responseType: 'text' })
      .pipe(
        catchError((error) => {
          this.toastr.error('Error fetching code');
          return 'Error fetching code';
        }),
      )
      .subscribe((data) => {
        this.code = data;
      });

    this.http
      .get('/assets/requirements.txt', { responseType: 'text' })
      .pipe(
        catchError((error) => {
          this.toastr.error('Error fetching dependencies');
          return 'Error fetching dependencies';
        }),
      )
      .subscribe((data) => {
        this.deps = data;
      });
  }
}
